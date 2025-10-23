#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
bp_setup_wizard.py — Wizard thu thập tham số cho module đo huyết áp (HX710B)
Tác vụ:
  1) Kiểm tra rò khí (leak-test)
  2) Đặt offset 0 mmHg (offset_counts)
  3) Kiểm tra chiều ADC (invert-check)
  4) Hiệu chuẩn slope (2-điểm & nhiều-điểm)
  5) Tạo LUT xả (deflate-tune) đạt 3.0 mmHg/s
  6) Ước lượng SPS thực tế của HX710B
  7) Quick capture deflate (để kiểm dp/dt & envelope sơ bộ)
Kết quả:
  - Xuất JSON log theo từng bước (tùy chọn)
  - Cập nhật config/app_config.yaml (offset, slope, adc_inverted, sps_mode, LUT, tham số control/signal/estimate)
Lưu ý:
  - Không đổi schema MQTT/REST/DB
  - Không đụng BaseSensor/GUI hiện có
  - Chạy trên Raspberry Pi (Bookworm 64-bit); yêu cầu RPi.GPIO

Copyright:
  Do An – IoT Health Monitor (Raspberry Pi 4B)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, List, Dict, Any, Tuple

# ------------------------- LOGGING SETUP -------------------------
LOG = logging.getLogger("bp_setup_wizard")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

# ------------------------- DEFAULT PATHS -------------------------
REPO_ROOT = Path(__file__).resolve().parents[1] if len(Path(__file__).parents) >= 2 else Path.cwd()
DEFAULT_CONFIG = REPO_ROOT / "config" / "app_config.yaml"

# ------------------------- YAML UTILS ---------------------------
try:
    import yaml  # type: ignore
except Exception as e:  # pragma: no cover
    LOG.error("Thiếu PyYAML. Cài: pip install pyyaml")
    raise

# ------------------------- GPIO / PI CHECK ----------------------
try:
    import RPi.GPIO as GPIO  # type: ignore
    ON_PI = True
except Exception:
    LOG.warning("Không tìm thấy RPi.GPIO — đang chạy ở môi trường không phải Raspberry Pi.")
    ON_PI = False

# ========================= HARDWARE MAPPING =====================
# Giữ đúng mapping đã chốt trong dự án:
GPIO_PUMP = 26     # Output -> LED 4N35 (bơm)
GPIO_VALVE = 16    # Output -> LED 4N35 (van xả NO)
GPIO_HX_SCK = 5    # Output -> HX710B SCK
GPIO_HX_OUT = 6    # Input  -> HX710B DOUT/OUT

# ========================= SAFETY DEFAULTS ======================
SOFT_LIMIT_MMHG = 200.0
TARGET_INFLATE_MMHG = 165.0
INFLATE_TIMEOUT_S = 25.0
INFLATE_GRACE_S = 1.5

TARGET_DPDT = 3.0
PWM_PERIOD_S = 0.5
DEFLATE_TIMEOUT_S = 90.0
EMERGENCY_SENSOR_TIMEOUT_S = 2.0
NO_OSC_TIMEOUT_S = 10.0

# ========================= HELPERS ==============================

def monotonic() -> float:
    """Return monotonic time (seconds)."""
    return time.monotonic()


def sleep_s(sec: float) -> None:
    """Sleep helper với giới hạn giá trị âm."""
    if sec > 0:
        time.sleep(sec)


# ========================= CONFIG IO ============================

def load_yaml(path: Path) -> dict:
    """Load YAML config; trả dict (rỗng nếu chưa có)."""
    if not path.exists():
        LOG.warning("Chưa có %s — sẽ tạo mới khi ghi.", path)
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data: dict) -> None:
    """Ghi YAML, tạo thư mục nếu cần."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    LOG.info("Đã cập nhật %s", path)


def deep_get(d: dict, keys: List[str], default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def deep_set(d: dict, keys: List[str], value) -> None:
    cur = d
    for k in keys[:-1]:
        if k not in cur or not isinstance(cur[k], dict):
            cur[k] = {}
        cur = cur[k]
    cur[keys[-1]] = value


# ========================= HARDWARE ABSTRACTIONS =================

class GpioController:
    """Đóng gói thao tác GPIO cơ bản cho bơm/van/HX710B."""

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger
        self._initialized = False

    def setup(self) -> None:
        if not ON_PI:
            self.logger.warning("GPIO setup bỏ qua (không chạy trên Pi).")
            return
        if self._initialized:
            return
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        # Outputs
        GPIO.setup(GPIO_PUMP, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(GPIO_VALVE, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(GPIO_HX_SCK, GPIO.OUT, initial=GPIO.LOW)
        # Inputs
        GPIO.setup(GPIO_HX_OUT, GPIO.IN)
        self._initialized = True
        self.logger.info("GPIO initialized.")

    def cleanup(self) -> None:
        if ON_PI and self._initialized:
            GPIO.cleanup()
            self._initialized = False
            self.logger.info("GPIO cleanup done.")

    # Pump/Valve control
    def pump_on(self) -> None:
        if ON_PI:
            GPIO.output(GPIO_PUMP, GPIO.HIGH)

    def pump_off(self) -> None:
        if ON_PI:
            GPIO.output(GPIO_PUMP, GPIO.LOW)

    def valve_open(self) -> None:
        """Van NO: HIGH = mở (xả)."""
        if ON_PI:
            GPIO.output(GPIO_VALVE, GPIO.HIGH)

    def valve_close(self) -> None:
        if ON_PI:
            GPIO.output(GPIO_VALVE, GPIO.LOW)

    # HX710B primitives
    def hx_out_ready(self) -> bool:
        """OUT (DOUT) xuống LOW khi data-ready (tùy biến board)."""
        if not ON_PI:
            # Giả lập: luôn sẵn sàng (chỉ để tránh crash khi dev trên PC).
            return True
        return GPIO.input(GPIO_HX_OUT) == GPIO.LOW

    def hx_clock_pulse(self) -> None:
        if ON_PI:
            GPIO.output(GPIO_HX_SCK, GPIO.HIGH)
            # Tinh chỉnh xung SCK nếu cần (sleep rất ngắn)
            GPIO.output(GPIO_HX_SCK, GPIO.LOW)


class HX710BReader:
    """
    Đọc HX710B bằng bit-bang đơn giản (blocking ngắn); dùng cho wizard.
    - Trả về raw_counts (int)
    - Không đổi API/sensor của app chính; chỉ là công cụ thu thập tham số.
    """

    def __init__(self, gpio: GpioController, logger: logging.Logger,
                 adc_inverted: bool = False) -> None:
        self.gpio = gpio
        self.logger = logger
        self.adc_inverted = adc_inverted

    def read_raw(self, timeout_s: float = 0.3) -> Optional[int]:
        """
        Chờ data-ready (OUT=LOW) trong timeout; đọc 24-bit theo datasheet.
        Trả về số nguyên có dấu (signed) hoặc None nếu timeout.
        """
        t0 = monotonic()
        while (monotonic() - t0) < timeout_s:
            if self.gpio.hx_out_ready():
                # Đọc 24 bit
                val = 0
                for _ in range(24):
                    self.gpio.hx_clock_pulse()
                    # Lấy mẫu nhanh OUT (trên rising hoặc ngay sau)
                    if ON_PI:
                        bit = 1 if GPIO.input(GPIO_HX_OUT) else 0
                    else:
                        bit = 0
                    val = (val << 1) | bit
                # Kênh & gain: 1–3 xung SCK thêm; ở đây chọn CH A default -> 1 xung
                self.gpio.hx_clock_pulse()

                # Chuyển sang signed 24-bit
                if val & 0x800000:
                    val -= 1 << 24

                # Tùy chọn đảo dấu ngay tại đây
                if self.adc_inverted:
                    val = -val
                return val
            sleep_s(0.001)
        return None

    def sample_median(self, n: int = 50, timeout_s: float = 0.3) -> Optional[int]:
        vals: List[int] = []
        for _ in range(n):
            v = self.read_raw(timeout_s=timeout_s)
            if v is None:
                continue
            vals.append(v)
        if not vals:
            return None
        return int(statistics.median(vals))


# ========================= CALIBRATION COLLECTORS =================

@dataclass
class CalibrationState:
    offset_counts: Optional[int] = None
    slope_mmhg_per_count: Optional[float] = None
    adc_inverted: bool = False
    sps_mode: Optional[str] = None  # "10" | "80"

    # Control
    inflate_target_mmhg: float = TARGET_INFLATE_MMHG
    inflate_soft_limit_mmhg: float = SOFT_LIMIT_MMHG
    inflate_timeout_s: float = INFLATE_TIMEOUT_S
    inflate_grace_s: float = INFLATE_GRACE_S

    deflate_target_dpdt_mmhg_s: float = TARGET_DPDT
    deflate_pwm_period_s: float = PWM_PERIOD_S
    deflate_lut: List[Dict[str, int]] = None  # [{"bin": 160, "duty": 60}, ...]

    deflate_timeout_s: float = DEFLATE_TIMEOUT_S

    # Safety
    emergency_overpressure_mmhg: float = SOFT_LIMIT_MMHG
    emergency_no_oscillation_s: float = NO_OSC_TIMEOUT_S
    emergency_sensor_timeout_s: float = EMERGENCY_SENSOR_TIMEOUT_S
    emergency_dpdt_too_fast_mmhg_s: float = 8.0
    leak_max_drop_mmhg_per_min: float = 5.0

    # Signal
    bpf_low_hz: float = 0.5
    bpf_high_hz: float = 5.0
    detrend_poly_order: int = 1
    envelope_method: str = "hilbert"
    map_search_window: Tuple[float, float] = (0.3, 0.8)
    min_valid_peaks_around_map: int = 5
    snr_min_db: float = 6.0
    hampel_window_s: float = 1.2
    hampel_k: float = 3.0
    min_samples_per_bin: int = 20

    # Estimate
    sys_frac: float = 0.55
    dia_frac: float = 0.80
    map_weighted_centering: bool = True
    quality_rules: Dict[str, bool] = None

    def __post_init__(self):
        if self.deflate_lut is None:
            self.deflate_lut = [
                {"bin": 160, "duty": 60},
                {"bin": 140, "duty": 55},
                {"bin": 120, "duty": 52},
                {"bin": 100, "duty": 48},
                {"bin": 80,  "duty": 45},
                {"bin": 60,  "duty": 42},
                {"bin": 40,  "duty": 40},
            ]
        if self.quality_rules is None:
            self.quality_rules = {"reject_if_low_snr": True, "reject_if_few_peaks": True}


class PumpValveController:
    """Điều khiển bơm/van (cách ly 4N35) với thao tác cơ bản và PWM mềm."""

    def __init__(self, gpio: GpioController, logger: logging.Logger) -> None:
        self.gpio = gpio
        self.logger = logger

    def pump_on(self) -> None:
        self.gpio.pump_on()

    def pump_off(self) -> None:
        self.gpio.pump_off()

    def valve_open(self) -> None:
        self.gpio.valve_open()

    def valve_close(self) -> None:
        self.gpio.valve_close()

    def valve_pwm(self, duty_percent: int, period_s: float, duration_s: float) -> None:
        """
        PWM mềm mở/đóng van theo duty% trong khoảng duration_s.
        (Blocking ngắn để wizard đo dP/dt; không dùng trong UI chính)
        """
        duty = max(0, min(100, int(duty_percent)))
        t_end = monotonic() + max(0.0, duration_s)
        on_t = period_s * duty / 100.0
        off_t = period_s - on_t
        while monotonic() < t_end:
            self.valve_open()
            sleep_s(on_t)
            self.valve_close()
            sleep_s(off_t)


class PressureMath:
    """Chuyển đổi counts -> mmHg theo offset & slope."""

    def __init__(self, offset_counts: int, slope_mmhg_per_count: float):
        self.offset = offset_counts
        self.slope = slope_mmhg_per_count

    def counts_to_mmhg(self, counts: int) -> float:
        return (counts - self.offset) * self.slope


# ========================= WIZARD STEPS ==========================

class BPSetupWizard:
    """
    Wizard thu thập tham số và cập nhật config/app_config.yaml.
    Lưu ý: đây là tool vận hành bench; không dùng trong đường đo runtime.
    """

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.cfg = load_yaml(config_path)
        self.gpio = GpioController(LOG)
        self.hx: Optional[HX710BReader] = None
        self.act: Optional[PumpValveController] = None
        self.state = CalibrationState()

    # ------------ infra ------------
    def _get_calib_from_cfg(self) -> Tuple[Optional[int], Optional[float], bool]:
        off = deep_get(self.cfg, ["sensors", "hx710b", "calibration", "offset_counts"])
        slope = deep_get(self.cfg, ["sensors", "hx710b", "calibration", "slope_mmhg_per_count"])
        inv = bool(deep_get(self.cfg, ["sensors", "hx710b", "calibration", "adc_inverted"], False))
        return off, slope, inv

    def _apply_state_to_cfg(self) -> None:
        # Calibration
        deep_set(self.cfg, ["sensors", "hx710b", "calibration", "offset_counts"], self.state.offset_counts)
        deep_set(self.cfg, ["sensors", "hx710b", "calibration", "slope_mmhg_per_count"], self.state.slope_mmhg_per_count)
        deep_set(self.cfg, ["sensors", "hx710b", "calibration", "adc_inverted"], self.state.adc_inverted)
        if self.state.sps_mode:
            deep_set(self.cfg, ["sensors", "hx710b", "calibration", "sps_mode"], self.state.sps_mode)

        # Control
        deep_set(self.cfg, ["bp", "control", "inflate_target_mmhg"], self.state.inflate_target_mmhg)
        deep_set(self.cfg, ["bp", "control", "inflate_soft_limit_mmhg"], self.state.inflate_soft_limit_mmhg)
        deep_set(self.cfg, ["bp", "control", "inflate_timeout_s"], self.state.inflate_timeout_s)
        deep_set(self.cfg, ["bp", "control", "inflate_grace_s"], self.state.inflate_grace_s)
        deep_set(self.cfg, ["bp", "control", "deflate_target_dpdt_mmhg_s"], self.state.deflate_target_dpdt_mmhg_s)
        deep_set(self.cfg, ["bp", "control", "deflate_pwm_period_s"], self.state.deflate_pwm_period_s)
        deep_set(self.cfg, ["bp", "control", "deflate_lut"], self.state.deflate_lut)
        deep_set(self.cfg, ["bp", "control", "deflate_timeout_s"], self.state.deflate_timeout_s)
        deep_set(self.cfg, ["bp", "control", "emergency_overpressure_mmhg"], self.state.emergency_overpressure_mmhg)
        deep_set(self.cfg, ["bp", "control", "emergency_no_oscillation_s"], self.state.emergency_no_oscillation_s)
        deep_set(self.cfg, ["bp", "control", "emergency_sensor_timeout_s"], self.state.emergency_sensor_timeout_s)
        deep_set(self.cfg, ["bp", "control", "emergency_dpdt_too_fast_mmhg_s"], self.state.emergency_dpdt_too_fast_mmhg_s)
        deep_set(self.cfg, ["bp", "control", "leak_max_drop_mmhg_per_min"], self.state.leak_max_drop_mmhg_per_min)

        # Signal
        deep_set(self.cfg, ["bp", "signal", "bpf_low_hz"], self.state.bpf_low_hz)
        deep_set(self.cfg, ["bp", "signal", "bpf_high_hz"], self.state.bpf_high_hz)
        deep_set(self.cfg, ["bp", "signal", "detrend_poly_order"], self.state.detrend_poly_order)
        deep_set(self.cfg, ["bp", "signal", "envelope_method"], self.state.envelope_method)
        deep_set(self.cfg, ["bp", "signal", "map_search_window"], list(self.state.map_search_window))
        deep_set(self.cfg, ["bp", "signal", "min_valid_peaks_around_map"], self.state.min_valid_peaks_around_map)
        deep_set(self.cfg, ["bp", "signal", "snr_min_db"], self.state.snr_min_db)
        deep_set(self.cfg, ["bp", "signal", "hampel_window_s"], self.state.hampel_window_s)
        deep_set(self.cfg, ["bp", "signal", "hampel_k"], self.state.hampel_k)
        deep_set(self.cfg, ["bp", "signal", "min_samples_per_bin"], self.state.min_samples_per_bin)

        # Estimate
        deep_set(self.cfg, ["bp", "estimate", "sys_frac"], self.state.sys_frac)
        deep_set(self.cfg, ["bp", "estimate", "dia_frac"], self.state.dia_frac)
        deep_set(self.cfg, ["bp", "estimate", "map_weighted_centering"], self.state.map_weighted_centering)
        deep_set(self.cfg, ["bp", "estimate", "quality_rules"], self.state.quality_rules)

    def _init_hw(self) -> None:
        self.gpio.setup()
        off, slope, inv = self._get_calib_from_cfg()
        if off is not None:
            self.state.offset_counts = int(off)
        if slope is not None:
            self.state.slope_mmhg_per_count = float(slope)
        self.state.adc_inverted = bool(inv)
        self.hx = HX710BReader(self.gpio, LOG, adc_inverted=self.state.adc_inverted)
        self.act = PumpValveController(self.gpio, LOG)

    def _safe_cleanup(self) -> None:
        try:
            if self.act:
                self.act.pump_off()
                self.act.valve_open()
        finally:
            self.gpio.cleanup()

    # ------------ steps ------------
    def step_leak_test(self, target: float = 150.0, hold_s: int = 60, out: Optional[Path] = None) -> None:
        """
        Inflate ~target, đóng van & giữ áp, đo tụt áp -> mmHg/min.
        Pass nếu <= leak_max_drop_mmhg_per_min (mặc định 5.0).
        """
        assert self.hx and self.act
        LOG.info("[LEAK] Inflate đến %.1f mmHg, hold %ds...", target, hold_s)
        self.act.valve_close()
        t0 = monotonic()
        last_p = -1e9
        # Inflate ngắt quãng để đỡ overshoot
        while True:
            c = self.hx.sample_median(5)
            if c is None or self.state.offset_counts is None or self.state.slope_mmhg_per_count is None:
                LOG.error("Chưa có offset/slope để chuyển đổi mmHg.")
                return
            p = (c - self.state.offset_counts) * self.state.slope_mmhg_per_count
            if p >= self.state.inflate_soft_limit_mmhg:
                self.act.pump_off()
                self.act.valve_open()
                raise RuntimeError("Quá áp an toàn khi inflate!")
            if p < target - 2.0:
                self.act.pump_on(); sleep_s(0.25); self.act.pump_off(); sleep_s(0.1)
            else:
                break
            if int(p) != int(last_p):
                print(f"  Inflate: {p:.1f} mmHg", end="\r")
                last_p = p
            if (monotonic() - t0) > self.state.inflate_timeout_s:
                raise RuntimeError("Inflate quá thời gian cho phép.")

        print("\n  Ổn định 2s...")
        sleep_s(2.0)

        series: List[Dict[str, float]] = []
        tstart = monotonic()
        for _ in range(hold_s * 5):
            c = self.hx.read_raw()
            if c is None:
                continue
            p = (c - self.state.offset_counts) * self.state.slope_mmhg_per_count
            series.append({"t": monotonic() - tstart, "p": float(p)})
            sleep_s(0.2)

        # Xả
        self.act.valve_open()

        if not series:
            LOG.error("Không có dữ liệu giữ áp.")
            return
        drop = max(0.0, series[0]["p"] - series[-1]["p"])
        dur = series[-1]["t"]
        drop_per_min = drop / max(1e-3, dur / 60.0)
        result = {
            "target": target,
            "hold_s": hold_s,
            "drop_mmHg": round(drop, 2),
            "drop_per_min_mmHg": round(drop_per_min, 2),
            "pass": drop_per_min <= self.state.leak_max_drop_mmhg_per_min,
        }
        print("\nKẾT QUẢ LEAK:", json.dumps(result, ensure_ascii=False, indent=2))
        if out:
            out.write_text(json.dumps({"result": result, "series": series}, ensure_ascii=False, indent=2), encoding="utf-8")
            LOG.info("Đã lưu %s", out)

    def step_offset(self, samples: int = 200) -> None:
        """Đo offset ở 0 mmHg (van mở, cuff thông khí)."""
        assert self.hx and self.act
        self.act.valve_open()
        LOG.info("Đang đo offset ở 0 mmHg ...")
        vals: List[int] = []
        t0 = monotonic()
        while len(vals) < samples and (monotonic() - t0) < 10.0:
            v = self.hx.read_raw()
            if v is not None:
                vals.append(v)
            sleep_s(0.01)
        if not vals:
            raise RuntimeError("Không đọc được ADC để lấy offset.")
        off = int(statistics.median(vals))
        self.state.offset_counts = off
        print(f"offset_counts = {off} (median {len(vals)} mẫu)")
        self._apply_state_to_cfg()
        save_yaml(self.config_path, self.cfg)

    def step_invert_check(self) -> None:
        """Bơm ngắn 2s từ 0 mmHg để xem áp↑ → counts↑ hay counts↓."""
        assert self.hx and self.act and self.state.offset_counts is not None and self.state.slope_mmhg_per_count is not None
        self.act.valve_open(); sleep_s(0.5)
        base = [self.hx.read_raw() for _ in range(30)]
        base = [int(x) for x in base if x is not None]
        if not base:
            raise RuntimeError("Không đọc được base ADC.")
        c0 = int(statistics.median(base))
        self.act.valve_close()
        self.act.pump_on(); sleep_s(2.0); self.act.pump_off()
        sleep_s(0.3)
        top = [self.hx.read_raw() for _ in range(30)]
        top = [int(x) for x in top if x is not None]
        c1 = int(statistics.median(top)) if top else c0
        delta = c1 - c0
        inverted = delta < 0
        print(f"c0={c0}, c1={c1}, delta={delta}, adc_inverted_recommend={inverted}")
        # Không tự động đổi flag, để người dùng xác nhận
        self.act.valve_open()

    def step_sps_estimate(self, dur_s: float = 3.0) -> None:
        """Ước lượng SPS của HX710B bằng cách đếm mẫu trong dur_s ở 0 mmHg."""
        assert self.hx
        self.act.valve_open()
        cnt = 0
        t0 = monotonic()
        while (monotonic() - t0) < dur_s:
            v = self.hx.read_raw()
            if v is not None:
                cnt += 1
        sps = cnt / dur_s
        mode = "80" if sps > 40 else "10"
        self.state.sps_mode = mode
        print(f"SPS≈{sps:.1f} → sps_mode='{mode}'")
        self._apply_state_to_cfg()
        save_yaml(self.config_path, self.cfg)

    def step_slope_two_point(self, pref_mmhg: float) -> None:
        """
        Hiệu chuẩn slope bằng 2 điểm: 0 mmHg & P_ref (nhập hoặc theo máy tham chiếu).
        Yêu cầu đã có offset_counts.
        """
        assert self.hx and self.act and self.state.offset_counts is not None
        # Lấy counts ở P_ref: bơm lên ~P_ref, đóng van, đo median 5–10s
        target = pref_mmhg
        self.act.valve_close()
        LOG.info("Inflate đến %.1f mmHg để lấy điểm tham chiếu ...", target)
        t0 = monotonic()
        last_p = -1e9
        while True:
            c = self.hx.sample_median(5)
            if c is None or self.state.slope_mmhg_per_count is None:
                # tạm dùng slope gần đúng 0.002 để hiển thị (không ảnh hưởng tính toán cuối)
                slope_hint = 0.002
            else:
                slope_hint = self.state.slope_mmhg_per_count
            p = (c - self.state.offset_counts) * slope_hint if c is not None else -1e9
            if p >= SOFT_LIMIT_MMHG:
                self.act.pump_off(); self.act.valve_open()
                raise RuntimeError("Quá áp an toàn khi inflate (slope hint)!")
            if p < target - 3.0:
                self.act.pump_on(); sleep_s(0.3); self.act.pump_off(); sleep_s(0.1)
            else:
                break
            if int(p) != int(last_p):
                print(f"  Inflate (ước lượng): {p:.1f} mmHg", end="\r")
                last_p = p
            if (monotonic() - t0) > INFLATE_TIMEOUT_S:
                raise RuntimeError("Inflate quá thời gian cho phép.")

        sleep_s(2.0)  # ổn định
        vals: List[int] = []
        t1 = monotonic()
        while (monotonic() - t1) < 5.0:
            v = self.hx.read_raw()
            if v is not None:
                vals.append(v)
            sleep_s(0.02)
        if not vals:
            raise RuntimeError("Không đọc được ADC tại P_ref.")
        c_ref = int(statistics.median(vals))
        c0 = self.state.offset_counts
        slope = (pref_mmhg - 0.0) / max(1, (c_ref - c0))
        # Nếu invert đang bật thì val đã đảo, slope sẽ mang dấu hợp lý
        self.state.slope_mmhg_per_count = float(slope)
        print(f"slope_mmhg_per_count = {self.state.slope_mmhg_per_count:.6f}  (C_ref={c_ref}, C0={c0}, P_ref={pref_mmhg})")
        self._apply_state_to_cfg()
        save_yaml(self.config_path, self.cfg)
        self.act.valve_open()

    def step_slope_multi_point(self, points: List[float]) -> None:
        """
        Hiệu chuẩn slope bằng nhiều điểm áp tĩnh (mmHg): ví dụ [30, 60, 90, 120, 150].
        Với mỗi điểm: bơm đến ±2 mmHg, đóng van, ghi median 5–10s.
        Fit tuyến tính: P ≈ a*C + b => slope=a; offset≈ -b/a (đối chiếu C0).
        """
        assert self.hx and self.act and self.state.offset_counts is not None
        c_list: List[int] = []
        p_list: List[float] = []
        slope_hint = self.state.slope_mmhg_per_count or 0.002
        for pref in points:
            target = pref
            self.act.valve_close()
            LOG.info("Inflate đến %.1f mmHg (điểm calib)...", target)
            t0 = monotonic()
            while True:
                c = self.hx.sample_median(5)
                if c is None:
                    continue
                pest = (c - self.state.offset_counts) * slope_hint
                if pest >= SOFT_LIMIT_MMHG:
                    self.act.pump_off(); self.act.valve_open()
                    raise RuntimeError("Quá áp an toàn khi inflate (hint)!")
                if pest < target - 2.0:
                    self.act.pump_on(); sleep_s(0.25); self.act.pump_off(); sleep_s(0.1)
                else:
                    break
                if (monotonic() - t0) > INFLATE_TIMEOUT_S:
                    raise RuntimeError("Inflate quá thời gian cho phép (multi-point).")

            sleep_s(2.0)
            vals: List[int] = []
            t1 = monotonic()
            while (monotonic() - t1) < 5.0:
                v = self.hx.read_raw()
                if v is not None:
                    vals.append(v)
                sleep_s(0.02)
            if not vals:
                raise RuntimeError("Không đọc được ADC tại điểm calib.")
            c_ref = int(statistics.median(vals))
            c_list.append(c_ref)
            p_list.append(pref)
            LOG.info("  Điểm %.1f mmHg -> counts=%d", pref, c_ref)
            # Nhả chút áp để tránh dính biên
            self.act.valve_open(); sleep_s(1.0)

        # Fit tuyến tính đơn giản (least squares) cho P = a*C + b
        # a = cov(C,P)/var(C), b = mean(P) - a*mean(C)
        c_mean = statistics.mean(c_list)
        p_mean = statistics.mean(p_list)
        cov = sum((ci - c_mean) * (pi - p_mean) for ci, pi in zip(c_list, p_list))
        var = sum((ci - c_mean) ** 2 for ci in c_list) or 1.0
        a = cov / var
        b = p_mean - a * c_mean
        self.state.slope_mmhg_per_count = float(a)
        est_c0 = -b / a if a != 0 else self.state.offset_counts
        print("Kết quả fit: slope (a) = {:.6f}, b = {:.2f}, ước lượng offset_counts ≈ {:.0f} (C0 thực={})".format(
            self.state.slope_mmhg_per_count, b, est_c0, self.state.offset_counts))
        self._apply_state_to_cfg()
        save_yaml(self.config_path, self.cfg)

    def step_deflate_tune(self,
                          bins: List[int] = [160, 140, 120, 100, 80, 60, 40],
                          try_duties: List[int] = [20, 30, 40, 50, 60, 70, 80],
                          target_dpdt: float = TARGET_DPDT,
                          period_s: float = PWM_PERIOD_S,
                          out: Optional[Path] = None) -> None:
        """
        Tạo LUT duty(%) cho từng bin áp để đạt dP/dt mục tiêu (~3.0 mmHg/s).
        """
        assert self.hx and self.act and self.state.offset_counts is not None and self.state.slope_mmhg_per_count is not None
        self.act.valve_close()
        # Inflate lên trên bin cao nhất một chút
        top = bins[0] + 2
        LOG.info("Inflate đến %.1f mmHg để bắt đầu tune xả ...", top)
        t0 = monotonic()
        while True:
            c = self.hx.sample_median(5)
            if c is None:
                continue
            p = (c - self.state.offset_counts) * self.state.slope_mmhg_per_count
            if p >= self.state.inflate_soft_limit_mmhg:
                self.act.pump_off(); self.act.valve_open()
                raise RuntimeError("Quá áp an toàn khi inflate!")
            if p < top:
                self.act.pump_on(); sleep_s(0.25); self.act.pump_off(); sleep_s(0.1)
            else:
                break
            if (monotonic() - t0) > INFLATE_TIMEOUT_S:
                raise RuntimeError("Inflate quá thời gian cho phép (tune).")

        lut: List[Dict[str, Any]] = []
        for b in bins:
            LOG.info("Tune bin %d mmHg ...", b)
            # Hạ nhanh gần bin b
            while True:
                c = self.hx.read_raw()
                if c is None:
                    continue
                p = (c - self.state.offset_counts) * self.state.slope_mmhg_per_count
                if p <= b + 3:
                    self.act.valve_close()
                    break
                self.act.valve_open(); sleep_s(0.25); self.act.valve_close(); sleep_s(0.1)

            best = None
            for duty in try_duties:
                # 4 chu kỳ PWM để đo dP/dt trung bình
                samples: List[float] = []
                for _ in range(4):
                    # open phase
                    self.act.valve_open()
                    t_open0 = monotonic()
                    c1 = self.hx.read_raw()
                    sleep_s(period_s * duty / 100.0)
                    c2 = self.hx.read_raw()
                    self.act.valve_close()
                    t_open1 = monotonic()
                    # close phase
                    sleep_s(period_s * (1.0 - duty / 100.0))
                    # dP/dt
                    if c1 is not None and c2 is not None:
                        p1 = (c1 - self.state.offset_counts) * self.state.slope_mmhg_per_count
                        p2 = (c2 - self.state.offset_counts) * self.state.slope_mmhg_per_count
                        dp = max(0.0, p1 - p2)
                        dt = max(1e-3, t_open1 - t_open0)
                        samples.append(dp / dt)
                if not samples:
                    continue
                dpdt_avg = sum(samples) / len(samples)
                err = abs(dpdt_avg - target_dpdt)
                cand = {"bin": b, "duty": duty, "dpdt_avg": round(dpdt_avg, 3), "err": round(err, 3)}
                if (best is None) or (err < best["err"]):
                    best = cand
                LOG.info("  duty %2d%% → dP/dt≈ %.2f mmHg/s", duty, dpdt_avg)
            if best is None:
                raise RuntimeError("Không tìm được duty phù hợp cho bin %d." % b)
            lut.append(best)
            LOG.info("=> Bin %d chọn duty %d%% (dP/dt≈ %.2f)", b, best["duty"], best["dpdt_avg"])

        # Cập nhật LUT rút gọn (bin/duty)
        self.state.deflate_lut = [{"bin": r["bin"], "duty": int(r["duty"])} for r in lut]
        print("\nLUT mới:")
        for row in self.state.deflate_lut:
            print(f"  Bin {row['bin']:>3} → Duty {row['duty']:>2}%")

        self._apply_state_to_cfg()
        save_yaml(self.config_path, self.cfg)
        if out:
            out.write_text(json.dumps({"target_dpdt": target_dpdt, "period_s": period_s, "lut": lut}, ensure_ascii=False, indent=2), encoding="utf-8")
            LOG.info("Đã lưu %s", out)

    def step_quick_capture_deflate(self, duration_s: float = 20.0, out: Optional[Path] = None) -> None:
        """
        Quick capture chuỗi pressure trong pha xả để kiểm tra dp/dt & chất lượng sơ bộ.
        Không làm envelope; mục đích là sanity check LUT & dp/dt trung bình.
        """
        assert self.hx and self.act and self.state.offset_counts is not None and self.state.slope_mmhg_per_count is not None
        # Inflate lên ~165
        self.act.valve_close()
        LOG.info("Inflate đến %.1f mmHg trước khi xả...", TARGET_INFLATE_MMHG)
        t0 = monotonic()
        while True:
            c = self.hx.sample_median(5)
            if c is None:
                continue
            p = (c - self.state.offset_counts) * self.state.slope_mmhg_per_count
            if p >= self.state.inflate_soft_limit_mmhg:
                self.act.pump_off(); self.act.valve_open()
                raise RuntimeError("Quá áp an toàn!")
            if p < TARGET_INFLATE_MMHG - 2.0:
                self.act.pump_on(); sleep_s(0.25); self.act.pump_off(); sleep_s(0.1)
            else:
                break
            if (monotonic() - t0) > INFLATE_TIMEOUT_S:
                raise RuntimeError("Inflate quá thời gian cho phép.")
        sleep_s(INFLATE_GRACE_S)

        # Xả theo LUT, ghi chuỗi áp
        seq: List[Dict[str, float]] = []
        tstart = monotonic()
        last_p = None
        while (monotonic() - tstart) < duration_s:
            c = self.hx.read_raw()
            if c is None:
                # sensor timeout watchdog
                if (monotonic() - tstart) > EMERGENCY_SENSOR_TIMEOUT_S:
                    self.act.valve_open()
                    LOG.error("Sensor timeout trong quick capture — xả khẩn.")
                    break
                continue
            p = (c - self.state.offset_counts) * self.state.slope_mmhg_per_count
            seq.append({"t": monotonic() - tstart, "p": float(p)})

            # Áp dụng LUT đơn giản theo bin hiện tại
            duty = 50
            for row in self.state.deflate_lut:
                if p >= row["bin"]:
                    duty = int(row["duty"])
                    break
            self.act.valve_pwm(duty, self.state.deflate_pwm_period_s, duration_s=0.5)  # 0.5s mỗi vòng

            if p < 40:
                break

        self.act.valve_open()
        # Tính dp/dt thống kê
        dpdt_series: List[float] = []
        for i in range(1, len(seq)):
            dp = max(0.0, seq[i-1]["p"] - seq[i]["p"])
            dt = max(1e-3, seq[i]["t"] - seq[i-1]["t"])
            dpdt_series.append(dp / dt)
        if dpdt_series:
            avg = sum(dpdt_series) / len(dpdt_series)
            print(f"Quick dp/dt avg ≈ {avg:.2f} mmHg/s  (mục tiêu {self.state.deflate_target_dpdt_mmhg_s})")
        else:
            print("Không đủ dữ liệu để tính dp/dt.")
        if out:
            out.write_text(json.dumps({"pressure_series": seq, "dpdt_series": dpdt_series}, ensure_ascii=False, indent=2), encoding="utf-8")
            LOG.info("Đã lưu %s", out)

    # ------------ menu ------------
    def interactive_menu(self) -> None:
        self._init_hw()
        try:
            while True:
                print("\n=== BP Setup Wizard (HX710B) ===")
                print(" 1) Leak-test (150 mmHg / 60s)")
                print(" 2) Offset @ 0 mmHg (offset_counts)")
                print(" 3) Invert-check (áp↑ -> counts ?)")
                print(" 4) SPS estimate (10 hay 80 SPS)")
                print(" 5) Slope (2-điểm) — nhập P_ref (vd 150)")
                print(" 6) Slope (nhiều điểm) — nhập list (vd 30,60,90,120,150)")
                print(" 7) Deflate-tune (LUT dP/dt≈3.0)")
                print(" 8) Quick capture deflate (kiểm dp/dt)")
                print(" 9) Ghi tham số control/signal/estimate mặc định")
                print(" 0) Thoát")
                choice = input("Chọn: ").strip()

                if choice == "1":
                    out = input("Lưu JSON (đường dẫn hoặc Enter): ").strip() or None
                    self.step_leak_test(target=150.0, hold_s=60, out=Path(out) if out else None)
                elif choice == "2":
                    self.step_offset(samples=200)
                elif choice == "3":
                    self.step_invert_check()
                elif choice == "4":
                    self.step_sps_estimate(dur_s=3.0)
                elif choice == "5":
                    pref = float(input("Nhập P_ref (mmHg) [150]: ").strip() or "150")
                    self.step_slope_two_point(pref_mmhg=pref)
                elif choice == "6":
                    raw = input("Nhập danh sách điểm mmHg (vd 30,60,90,120,150): ").strip()
                    pts = [float(x) for x in raw.split(",") if x.strip()]
                    if not pts:
                        print("Danh sách rỗng.")
                    else:
                        self.step_slope_multi_point(pts)
                elif choice == "7":
                    out = input("Lưu LUT JSON (đường dẫn hoặc Enter): ").strip() or None
                    self.step_deflate_tune(out=Path(out) if out else None)
                elif choice == "8":
                    out = input("Lưu JSON capture (đường dẫn hoặc Enter): ").strip() or None
                    self.step_quick_capture_deflate(duration_s=20.0, out=Path(out) if out else None)
                elif choice == "9":
                    # Ghi toàn bộ tham số control/signal/estimate hiện trong state
                    self._apply_state_to_cfg()
                    save_yaml(self.config_path, self.cfg)
                    print("Đã ghi control/signal/estimate vào config.")
                elif choice == "0":
                    print("Tạm biệt!")
                    break
                else:
                    print("Lựa chọn không hợp lệ.")
        finally:
            self._safe_cleanup()


# ========================= MAIN ================================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Wizard thu thập tham số BP (HX710B)")
    p.add_argument("--config", type=str, default=str(DEFAULT_CONFIG), help="Đường dẫn config/app_config.yaml")
    p.add_argument("--menu", action="store_true", help="Mở menu tương tác (mặc định)")
    # CLI nhanh (tùy chọn)
    sub = p.add_subparsers(dest="cmd")

    ap_leak = sub.add_parser("leak-test")
    ap_leak.add_argument("--target", type=float, default=150.0)
    ap_leak.add_argument("--hold", type=int, default=60)
    ap_leak.add_argument("--out", type=str)

    ap_offset = sub.add_parser("offset")
    ap_offset.add_argument("--samples", type=int, default=200)

    ap_inv = sub.add_parser("invert-check")

    ap_sps = sub.add_parser("sps")

    ap_s2 = sub.add_parser("slope-2pt")
    ap_s2.add_argument("--pref", type=float, default=150.0)

    ap_sN = sub.add_parser("slope-multi")
    ap_sN.add_argument("--points", type=str, default="30,60,90,120,150")

    ap_tune = sub.add_parser("deflate-tune")
    ap_tune.add_argument("--out", type=str)

    ap_cap = sub.add_parser("quick-capture")
    ap_cap.add_argument("--dur", type=float, default=20.0)
    ap_cap.add_argument("--out", type=str)

    return p.parse_args()


def main() -> None:
    args = parse_args()
    wiz = BPSetupWizard(Path(args.config))
    if not args.cmd:
        # default to menu
        wiz.interactive_menu()
        return

    wiz._init_hw()
    try:
        if args.cmd == "leak-test":
            out = Path(args.out) if args.out else None
            wiz.step_leak_test(target=args.target, hold_s=args.hold, out=out)
        elif args.cmd == "offset":
            wiz.step_offset(samples=args.samples)
        elif args.cmd == "invert-check":
            wiz.step_invert_check()
        elif args.cmd == "sps":
            wiz.step_sps_estimate(dur_s=3.0)
        elif args.cmd == "slope-2pt":
            wiz.step_slope_two_point(pref_mmhg=args.pref)
        elif args.cmd == "slope-multi":
            points = [float(x) for x in args.points.split(",") if x.strip()]
            wiz.step_slope_multi_point(points)
        elif args.cmd == "deflate-tune":
            out = Path(args.out) if args.out else None
            wiz.step_deflate_tune(out=out)
        elif args.cmd == "quick-capture":
            out = Path(args.out) if args.out else None
            wiz.step_quick_capture_deflate(duration_s=args.dur, out=out)
        else:
            print("Lệnh không hợp lệ. Dùng --menu để mở menu.")
    finally:
        wiz._safe_cleanup()


if __name__ == "__main__":
    main()
