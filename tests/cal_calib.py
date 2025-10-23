#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
bp_setup_harvester.py — Trợ lý thu thập tham số cho module đo BP (HX710B + MPS20N0040D)
- Menu thao tác từng bước, ghi kết quả vào config/app_config.yaml, và log JSON/CSV cho phân tích.
- Không đổi schema dự án. Không tạo dữ liệu giả. An toàn với van NO (mặc định MỞ).

TÍNH NĂNG CHÍNH
1) Offset watch (xem offset 0 mmHg liên tục, median/độ trôi, CSV tuỳ chọn)
2) Đo offset nhanh (ghi offset_counts)
3) Invert-check (áp↑ → counts↑ hay ↓) → gợi ý adc_inverted
4) Ước lượng SPS (10/80) → sps_mode
5) Khởi tạo slope từ datasheet (3.3V); yêu cầu hệ số suy hao A (nếu biết)
6) Capture deflate run → log JSON/CSV (dp/dt, duty, p_est) — phục vụ tinh LUT & fit
7) MAP lock (paired) → nhập SYS/DIA để tinh slope từ C_map
8) Fit sys_frac/dia_frac từ nhiều paired logs
9) LUT refine: điều chỉnh duty% theo dp/dt từng bin để gần 3.0 mmHg/s
10) Dump snapshot: in & lưu YAML các tham số hiện có (để bạn gửi mình)
11) Actuator test: nhát bơm/xả; đóng/mở van (NO)

YÊU CẦU: RPi 4B, Pi OS 64-bit, RPi.GPIO, PyYAML
GPIO (KHÔNG đổi): Pump=GPIO26, Valve=GPIO16 (NO), HX710B SCK=GPIO5, OUT=GPIO6
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# -------------------- Logging --------------------
LOG = logging.getLogger("bp_harvester")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

# -------------------- Paths ----------------------
REPO_ROOT = Path(__file__).resolve().parents[1] if len(Path(__file__).parents) >= 2 else Path.cwd()
CONFIG_PATH = REPO_ROOT / "config" / "app_config.yaml"
DATA_DIR = REPO_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# -------------------- YAML utils -----------------
try:
    import yaml  # type: ignore
except Exception:
    LOG.error("Thiếu PyYAML. Cài: pip install pyyaml")
    raise

def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

def save_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
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

# -------------------- GPIO -----------------------
try:
    import RPi.GPIO as GPIO  # type: ignore
    ON_PI = True
except Exception:
    LOG.warning("Không tìm thấy RPi.GPIO — đang chạy ngoài Raspberry Pi (dev mode).")
    ON_PI = False

GPIO_PUMP  = 26  # Output -> LED 4N35 (bơm)
GPIO_VALVE = 16  # Output -> LED 4N35 (van xả NO)
GPIO_HX_SCK = 5  # Output -> HX710B SCK
GPIO_HX_OUT = 6  # Input  -> HX710B OUT/DOUT

def monotonic() -> float:
    return time.monotonic()

def sleep_s(s: float) -> None:
    if s > 0:
        time.sleep(s)

def now_tag() -> str:
    return time.strftime("%Y%m%d-%H%M%S")

# -------------------- HW Control -----------------
class GpioController:
    """Quản lý GPIO; AN TOÀN với van NO: mặc định mở xả."""
    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger
        self._inited = False

    def setup(self) -> None:
        if not ON_PI or self._inited:
            if not ON_PI:
                self.logger.warning("Bỏ qua GPIO setup (không phải Pi).")
            return
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(GPIO_PUMP, GPIO.OUT, initial=GPIO.LOW)    # pump OFF
        GPIO.setup(GPIO_VALVE, GPIO.OUT, initial=GPIO.HIGH)  # valve OPEN (NO -> HIGH = đóng? tùy mạch)
        # LƯU Ý: nếu mạch của bạn HIGH=ĐÓNG van NO, để valve an toàn mở khi khởi tạo hãy set về mức mở NO:
        GPIO.output(GPIO_VALVE, GPIO.LOW)  # mở xả với van NO khi bắt đầu
        GPIO.setup(GPIO_HX_SCK, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(GPIO_HX_OUT, GPIO.IN)
        self._inited = True
        self.logger.info("GPIO initialized (pump OFF, valve OPEN).")

    def cleanup(self) -> None:
        if ON_PI and self._inited:
            try:
                GPIO.output(GPIO_PUMP, GPIO.LOW)
                # giữ xả khi thoát (NO -> mở)
                GPIO.output(GPIO_VALVE, GPIO.LOW)
            finally:
                GPIO.cleanup()
                self._inited = False
                self.logger.info("GPIO cleanup done.")

    # Actuators
    def pump_on(self) -> None:
        if ON_PI:
            GPIO.output(GPIO_PUMP, GPIO.HIGH)

    def pump_off(self) -> None:
        if ON_PI:
            GPIO.output(GPIO_PUMP, GPIO.LOW)

    def valve_open(self) -> None:
        """Mở xả (NO): để an toàn, chúng ta coi LOW = OPEN. Điều chỉnh nếu phần cứng khác."""
        if ON_PI:
            GPIO.output(GPIO_VALVE, GPIO.LOW)

    def valve_close(self) -> None:
        """Đóng van NO (để giữ áp)."""
        if ON_PI:
            GPIO.output(GPIO_VALVE, GPIO.HIGH)

    # HX710B low level
    @staticmethod
    def hx_ready() -> bool:
        if not ON_PI:
            return True
        return GPIO.input(GPIO_HX_OUT) == GPIO.LOW

    @staticmethod
    def hx_clk_pulse() -> None:
        if ON_PI:
            GPIO.output(GPIO_HX_SCK, GPIO.HIGH)
            GPIO.output(GPIO_HX_SCK, GPIO.LOW)

# -------------------- HX710B Reader ---------------
class HX710BReader:
    """Đọc 24-bit từ HX710B; hỗ trợ đảo dấu nếu adc_inverted=True."""
    def __init__(self, gpio: GpioController, logger: logging.Logger, adc_inverted: bool = False) -> None:
        self.gpio = gpio
        self.logger = logger
        self.adc_inverted = adc_inverted

    def read_raw(self, timeout_s: float = 0.3) -> Optional[int]:
        t0 = monotonic()
        while (monotonic() - t0) < timeout_s:
            if self.gpio.hx_ready():
                val = 0
                for _ in range(24):
                    self.gpio.hx_clk_pulse()
                    bit = (1 if GPIO.input(GPIO_HX_OUT) else 0) if ON_PI else 0
                    val = (val << 1) | bit
                self.gpio.hx_clk_pulse()  # set channel/gain
                if val & 0x800000:
                    val -= 1 << 24
                if self.adc_inverted:
                    val = -val
                return val
            sleep_s(0.001)
        return None

    def sample_median(self, n: int = 50, timeout_s: float = 0.3) -> Optional[int]:
        vals: List[int] = []
        for _ in range(n):
            v = self.read_raw(timeout_s=timeout_s)
            if v is not None:
                vals.append(v)
        if not vals:
            return None
        return int(statistics.median(vals))

# -------------------- Calib & math ----------------
@dataclass
class CalibState:
    offset_counts: Optional[int] = None
    slope_mmhg_per_count: Optional[float] = None
    adc_inverted: bool = False
    sps_mode: Optional[str] = None  # "10" | "80"

class PressureMath:
    """Chuyển counts -> mmHg."""
    def __init__(self, offset_counts: int, slope_mmhg_per_count: float) -> None:
        self.off = int(offset_counts)
        self.slope = float(slope_mmhg_per_count)

    def to_mmhg(self, counts: int) -> float:
        return (int(counts) - self.off) * self.slope

# -------------------- Signal helpers --------------
def detrend_linear(t: List[float], y: List[float]) -> List[float]:
    n = len(t)
    if n < 2:
        return list(y)
    tm = sum(t)/n; ym = sum(y)/n
    num = sum((ti-tm)*(yi-ym) for ti, yi in zip(t, y))
    den = sum((ti-tm)**2 for ti in t) or 1.0
    a = num/den; b = ym - a*tm
    return [yi - (a*ti + b) for ti, yi in zip(t, y)]

def moving_rms(seq: List[float], win: int) -> List[float]:
    if win <= 1:
        return [abs(x) for x in seq]
    out: List[float] = []; s = 0.0; buf: List[float] = []
    for x in seq:
        xx = x*x; buf.append(xx); s += xx
        if len(buf) > win:
            s -= buf.pop(0)
        out.append((s/len(buf))**0.5)
    return out

# -------------------- Harvester core ---------------
class BPHarvester:
    """Menu thu thập & ghi tham số/nhật ký cho module đo BP."""
    def __init__(self, cfg_path: Path) -> None:
        self.cfg_path = cfg_path
        self.cfg = load_yaml(cfg_path)
        self.gpio = GpioController(LOG)
        self.state = CalibState()
        self._load_state_from_cfg()
        self.hx: Optional[HX710BReader] = None

        # Tham số control mặc định (không ghi đè config nếu đã có)
        self.infl_target = float(deep_get(self.cfg, ["bp", "control", "inflate_target_mmhg"], 165.0))
        self.infl_soft   = float(deep_get(self.cfg, ["bp", "control", "inflate_soft_limit_mmhg"], 200.0))
        self.infl_timeout= float(deep_get(self.cfg, ["bp", "control", "inflate_timeout_s"], 25.0))
        self.infl_grace  = float(deep_get(self.cfg, ["bp", "control", "inflate_grace_s"], 1.5))
        self.infl_pulse  = float(deep_get(self.cfg, ["bp", "control", "inflate_pulse_s"], 0.30))
        self.def_period  = float(deep_get(self.cfg, ["bp", "control", "deflate_pwm_period_s"], 0.5))
        self.def_timeout = float(deep_get(self.cfg, ["bp", "control", "deflate_timeout_s"], 90.0))

    # ---------- cfg IO ----------
    def _load_state_from_cfg(self) -> None:
        off = deep_get(self.cfg, ["sensors", "hx710b", "calibration", "offset_counts"])
        slope = deep_get(self.cfg, ["sensors", "hx710b", "calibration", "slope_mmhg_per_count"])
        inv = bool(deep_get(self.cfg, ["sensors", "hx710b", "calibration", "adc_inverted"], False))
        sps = deep_get(self.cfg, ["sensors", "hx710b", "calibration", "sps_mode"])
        self.state.offset_counts = int(off) if off is not None else None
        self.state.slope_mmhg_per_count = float(slope) if slope is not None else None
        self.state.adc_inverted = bool(inv)
        self.state.sps_mode = sps if sps in ("10","80") else None

    def _save_state_to_cfg(self) -> None:
        deep_set(self.cfg, ["sensors","hx710b","calibration","offset_counts"], self.state.offset_counts)
        deep_set(self.cfg, ["sensors","hx710b","calibration","slope_mmhg_per_count"], self.state.slope_mmhg_per_count)
        deep_set(self.cfg, ["sensors","hx710b","calibration","adc_inverted"], self.state.adc_inverted)
        if self.state.sps_mode:
            deep_set(self.cfg, ["sensors","hx710b","calibration","sps_mode"], self.state.sps_mode)
        save_yaml(self.cfg_path, self.cfg)

    # ---------- HW ----------
    def init_hw(self) -> None:
        self.gpio.setup()
        self.hx = HX710BReader(self.gpio, LOG, adc_inverted=self.state.adc_inverted)

    def close_hw(self) -> None:
        self.gpio.cleanup()

    # ---------- Steps ----------
    def step_offset_watch(self, win:int=101, dur:float=0.0, csv_out:Optional[Path]=None) -> None:
        """Theo dõi offset liên tục (van mở, bơm tắt), in counts/median/delta & SPS; CSV tuỳ chọn."""
        assert self.hx
        self.gpio.pump_off(); self.gpio.valve_open()
        buf: List[int] = []
        maxlen = max(3,int(win))
        t0 = monotonic(); last = t0; n=0
        writer = None; f=None
        if csv_out:
            csv_out.parent.mkdir(parents=True, exist_ok=True)
            f = csv_out.open("w", newline="", encoding="utf-8")
            writer = csv.writer(f); writer.writerow(["t","counts","median","delta"])
        print("Offset watch — Ctrl+C để thoát.")
        try:
            while True:
                v = self.hx.read_raw()
                if v is None:
                    sys.stdout.write("."); sys.stdout.flush()
                    continue
                buf.append(v); 
                if len(buf)>maxlen: buf.pop(0)
                med = int(statistics.median(buf))
                delta = v - med
                n+=1; now=monotonic()
                line = f"\rcounts={v:>8d} | med({maxlen})={med:>8d} | delta={delta:>6d}"
                if now-last>=2.0:
                    sps = n/(now-last); n=0; last=now
                    line += f" | SPS≈{sps:4.1f}"
                sys.stdout.write(line); sys.stdout.flush()
                if writer:
                    writer.writerow([f"{now-t0:.3f}", v, med, delta])
                if dur>0 and (now-t0)>=dur:
                    print("\nHết --dur, thoát.")
                    break
                sleep_s(0.02)
        except KeyboardInterrupt:
            print("\nThoát do người dùng.")
        finally:
            if f: f.close()

    def step_offset_quick(self, samples:int=200) -> None:
        """Đo offset nhanh @ 0 mmHg và ghi vào config."""
        assert self.hx
        self.gpio.pump_off(); self.gpio.valve_open()
        LOG.info("Đang đo offset 0 mmHg ...")
        vals: List[int] = []
        t0 = monotonic()
        while len(vals)<samples and (monotonic()-t0)<10.0:
            v = self.hx.read_raw()
            if v is not None: vals.append(v)
            sleep_s(0.01)
        if not vals:
            raise RuntimeError("Không đọc được ADC.")
        off = int(statistics.median(vals))
        self.state.offset_counts = off
        print(f"offset_counts = {off} (median {len(vals)} mẫu)")
        self._save_state_to_cfg()

    def step_invert_check(self) -> None:
        """Bơm nhát & so sánh c0/c1 để gợi ý adc_inverted."""
        assert self.hx
        if self.state.offset_counts is None:
            raise RuntimeError("Chưa có offset_counts.")
        self.gpio.valve_open(); sleep_s(0.5)
        base=[self.hx.read_raw() for _ in range(30)]
        base=[int(x) for x in base if x is not None]
        if not base: raise RuntimeError("Không đọc base ADC.")
        c0 = int(statistics.median(base))
        self.gpio.valve_close()
        self.gpio.pump_on(); sleep_s(1.0); self.gpio.pump_off()
        sleep_s(0.3)
        top=[self.hx.read_raw() for _ in range(30)]
        top=[int(x) for x in top if x is not None]
        c1=int(statistics.median(top)) if top else c0
        delta=c1-c0; inv = delta<0
        print(f"c0={c0}, c1={c1}, delta={delta}, adc_inverted_recommend={inv}")
        self.gpio.valve_open()

    def step_sps(self, dur:float=3.0) -> None:
        """Ước lượng SPS (10/80) và ghi sps_mode vào config."""
        assert self.hx
        cnt=0; t0=monotonic()
        while (monotonic()-t0)<dur:
            if self.hx.read_raw() is not None:
                cnt+=1
        sps = cnt/dur; mode="80" if sps>40 else "10"
        self.state.sps_mode = mode
        print(f"SPS≈{sps:.1f} => sps_mode='{mode}'")
        self._save_state_to_cfg()

    def step_init_slope_from_datasheet(self, A:float, fso_mv_5v:float=75.0, vref:float=3.3) -> None:
        """Khởi tạo slope từ datasheet (3.3V). A=hệ số suy hao điện áp cầu→ngõ vào HX710B (0.2–0.4 điển hình)."""
        fso_mv_33 = fso_mv_5v * (3.3/5.0)  # mV @3.3V
        s_sensor_v_per_kpa = (fso_mv_33/1000.0)/40.0
        s_in = A * s_sensor_v_per_kpa
        vfs_in = 0.0039 * vref
        N = 2**23
        slope = (7.5006 * vfs_in)/(N * s_in)
        self.state.slope_mmhg_per_count = float(slope)
        print(f"Khởi tạo slope≈{slope:.6e} mmHg/count (A={A}, FSO@5V={fso_mv_5v}mV)")
        self._save_state_to_cfg()

    def _pick_duty_from_lut(self, p: float) -> int:
        lut = deep_get(self.cfg, ["bp","control","deflate_lut"], [])
        duty = 50
        for row in lut:
            if p >= float(row.get("bin",160)):
                duty = int(row.get("duty",50))
                break
        return duty

    def step_capture_deflate(self, out_prefix:str="bpdeflate") -> Path:
        """Chạy inflate→grace→deflate theo LUT; lưu JSON/CSV."""
        assert self.hx
        if self.state.offset_counts is None or self.state.slope_mmhg_per_count is None:
            raise RuntimeError("Thiếu offset/slope trong config.")
        math = PressureMath(self.state.offset_counts, self.state.slope_mmhg_per_count)

        # Inflate (nhát) tới mục tiêu
        self.gpio.valve_close()
        t0 = monotonic()
        print("Inflate tới mục tiêu ...")
        while True:
            c = self.hx.sample_median(5)
            if c is None: continue
            p = math.to_mmhg(c)
            if p >= self.infl_soft:
                self.gpio.pump_off(); self.gpio.valve_open()
                raise RuntimeError("Quá áp an toàn khi inflate.")
            if p < self.infl_target - 2.0:
                self.gpio.pump_on(); sleep_s(self.infl_pulse); self.gpio.pump_off(); sleep_s(0.10)
            else:
                break
            if (monotonic()-t0) > self.infl_timeout:
                self.gpio.valve_open()
                raise RuntimeError("Inflate quá thời gian cho phép.")

        sleep_s(self.infl_grace)

        # Deflate + log
        print("Deflate + ghi log ...")
        rows: List[Dict[str,Any]] = []
        tstart = monotonic()
        last_t=None; last_p=None
        while True:
            c = self.hx.read_raw()
            if c is None:
                if (monotonic()-tstart) > 2.0:
                    self.gpio.valve_open(); LOG.error("Sensor timeout, xả khẩn."); break
                continue
            t = monotonic()-tstart
            p = math.to_mmhg(c)
            duty = self._pick_duty_from_lut(p)
            # PWM khoảng ngắn
            self.gpio.valve_open(); sleep_s(self.def_period*duty/100.0)
            self.gpio.valve_close(); sleep_s(self.def_period*(100-duty)/100.0)

            dpdt = None
            if last_t is not None and last_p is not None:
                dp = max(0.0, last_p - p); dt = max(1e-3, t - last_t); dpdt = dp/dt
            rows.append({"t": t, "counts": int(c), "p": float(p), "duty": duty, "dpdt": (float(dpdt) if dpdt is not None else None)})
            last_t=t; last_p=p
            if p < 40.0 or (monotonic()-tstart)>self.def_timeout:
                break

        self.gpio.valve_open()

        out_json = DATA_DIR / f"{out_prefix}-{now_tag()}.json"
        out_json.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        LOG.info("Đã lưu %s", out_json)
        out_csv = out_json.with_suffix(".csv")
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["t","counts","p","duty","dpdt"])
            w.writeheader()
            for r in rows: w.writerow(r)
        LOG.info("Đã lưu %s", out_csv)
        return out_json

    def _estimate_map_index(self, t: List[float], p: List[float]) -> int:
        n = len(t)
        if n < 50: return max(0,n//2)
        osc = detrend_linear(t,p)
        env = moving_rms(osc, max(5,n//100))
        a=int(0.3*n); b=int(0.8*n)
        if b<=a: a=0; b=n
        seg = env[a:b]
        if not seg: return max(0,n//2)
        i = a + max(range(len(seg)), key=lambda k: seg[k])
        return i

    def step_lock_map(self, json_path: Path, sys_ref: float, dia_ref: float) -> None:
        """Khóa MAP từ paired run để cập nhật slope."""
        assert self.state.offset_counts is not None
        data = json.loads(json_path.read_text(encoding="utf-8"))
        rows = data.get("rows", [])
        if not rows: raise RuntimeError("Log trống.")
        t=[float(r["t"]) for r in rows]; counts=[int(r["counts"]) for r in rows]
        # nếu đã có slope cũ, dùng p_est; nếu không, scale tạm để tìm index
        if self.state.slope_mmhg_per_count is not None:
            math = PressureMath(self.state.offset_counts, self.state.slope_mmhg_per_count)
            p_est = [math.to_mmhg(c) for c in counts]
        else:
            c0=self.state.offset_counts; span=max(1, max(counts)-min(counts))
            p_est = [200.0*(c-c0)/span for c in counts]
        idx = self._estimate_map_index(t,p_est)
        c_map = counts[idx]; c0=self.state.offset_counts
        map_ref = float(dia_ref + (sys_ref - dia_ref)/3.0)
        denom = max(1,(c_map - c0))
        new_slope = map_ref/denom
        self.state.slope_mmhg_per_count=float(new_slope)
        print(f"Khóa MAP: C_map={c_map}, C0={c0}, MAP_ref={map_ref:.1f} => slope_new={new_slope:.6f}")
        self._save_state_to_cfg()

    def _find_press_at_frac(self, t: List[float], p: List[float], frac: float) -> Tuple[Optional[float], Optional[float]]:
        osc=detrend_linear(t,p); env=moving_rms(osc, max(5,len(osc)//100))
        n=len(env); a=int(0.2*n); b=int(0.9*n)
        if b<=a: a=0; b=n
        env_seg=env[a:b]; p_seg=p[a:b]
        if not env_seg: return None, None
        peak=max(env_seg); thr=frac*peak
        ps=None; pd=None
        for i in range(1,len(env_seg)):
            if env_seg[i-1] < thr <= env_seg[i]: ps=p_seg[i]; break
        for i in range(len(env_seg)-2,-1,-1):
            if env_seg[i+1] < thr <= env_seg[i]: pd=p_seg[i]; break
        return ps, pd

    def step_fit_sys_dia(self, json_paths: List[Path],
                         grid_sys=(0.45,0.65,0.02), grid_dia=(0.70,0.90,0.02)) -> None:
        """Fit sys_frac/dia_frac từ nhiều paired logs (yêu cầu slope/offset hợp lệ)."""
        assert self.state.offset_counts is not None and self.state.slope_mmhg_per_count is not None
        math = PressureMath(self.state.offset_counts, self.state.slope_mmhg_per_count)
        paired=[]
        for jp in json_paths:
            data=json.loads(jp.read_text(encoding="utf-8"))
            rows=data.get("rows",[])
            meta=data.get("meta",{})
            sys_ref=meta.get("sys_ref"); dia_ref=meta.get("dia_ref")
            if sys_ref is None or dia_ref is None:
                try:
                    sys_ref=float(input(f"[{jp.name}] SYS_ref: ").strip())
                    dia_ref=float(input(f"[{jp.name}] DIA_ref: ").strip())
                except Exception:
                    LOG.error("Thiếu SYS/DIA cho %s", jp.name); continue
            t=[float(r["t"]) for r in rows]
            p=[math.to_mmhg(int(r["counts"])) for r in rows]
            paired.append({"t":t,"p":p,"sys_ref":float(sys_ref),"dia_ref":float(dia_ref)})
        if not paired: raise RuntimeError("Không có log paired hợp lệ.")

        def frange(a,b,s):
            x=a
            while x<=b+1e-9:
                yield round(x,3); x+=s

        best=(None,None,1e9)
        for sf in frange(*grid_sys):
            for df in frange(*grid_dia):
                err=0.0; k=0
                for it in paired:
                    ps,_ = self._find_press_at_frac(it["t"], it["p"], sf)
                    _,pd = self._find_press_at_frac(it["t"], it["p"], df)
                    if ps is None or pd is None: continue
                    err += abs(ps - it["sys_ref"]) + abs(pd - it["dia_ref"]); k+=2
                if k>0 and (err/k) < best[2]:
                    best=(sf,df,err/k)
        if best[0] is None: raise RuntimeError("Không fit được sys_frac/dia_frac.")
        sf, df, mae = best
        print(f"sys_frac={sf:.3f}, dia_frac={df:.3f} (MAE≈{mae:.2f} mmHg)")
        deep_set(self.cfg, ["bp","estimate","sys_frac"], float(sf))
        deep_set(self.cfg, ["bp","estimate","dia_frac"], float(df))
        save_yaml(self.cfg_path, self.cfg)

    def step_lut_refine(self, json_path: Path, target_dpdt: float = 3.0) -> None:
        """Điều chỉnh LUT duty theo dp/dt trung bình mỗi bin để gần target."""
        data=json.loads(json_path.read_text(encoding="utf-8"))
        rows=data.get("rows",[])
        lut=deep_get(self.cfg, ["bp","control","deflate_lut"], [])
        if not rows or not lut: raise RuntimeError("Thiếu log hoặc LUT.")
        bin_stats: Dict[int,List[float]] = {int(r["bin"]): [] for r in lut}
        for r in rows:
            p=float(r.get("p",0)); dpdt=r.get("dpdt",None)
            if dpdt is None: continue
            for b in sorted(bin_stats.keys(), reverse=True):
                if p>=b: bin_stats[b].append(float(dpdt)); break
        new_lut=[]
        for row in lut:
            b=int(row["bin"]); duty=int(row["duty"])
            vals=bin_stats.get(b,[])
            if not vals: new_lut.append({"bin":b,"duty":duty}); continue
            avg=sum(vals)/len(vals); ratio=(target_dpdt/avg) if avg>0 else 1.0
            duty_new=int(round(max(15, min(85, duty*ratio))))
            new_lut.append({"bin":b,"duty":duty_new})
            print(f"Bin {b}: dp/dt_avg={avg:.2f} -> duty {duty}% => {duty_new}%")
        deep_set(self.cfg, ["bp","control","deflate_lut"], new_lut)
        save_yaml(self.cfg_path, self.cfg)

    def step_dump_snapshot(self, out_yaml: Optional[Path]=None) -> None:
        """In & lưu YAML snapshot các tham số hiện có (để gửi cho mình)."""
        snap = {
            "sensors": {"hx710b": {"calibration": {
                "offset_counts": self.state.offset_counts,
                "slope_mmhg_per_count": self.state.slope_mmhg_per_count,
                "adc_inverted": self.state.adc_inverted,
                "sps_mode": self.state.sps_mode,
            }}},
            "bp": {
                "control": deep_get(self.cfg, ["bp","control"], {}),
                "signal":  deep_get(self.cfg, ["bp","signal"], {}),
                "estimate":deep_get(self.cfg, ["bp","estimate"], {})
            }
        }
        txt = yaml.safe_dump(snap, allow_unicode=True, sort_keys=False)
        print("\n===== SNAPSHOT =====\n"+txt)
        if out_yaml:
            out_yaml.write_text(txt, encoding="utf-8"); print(f"Đã lưu {out_yaml}")

    def step_actuator_test(self) -> None:
        """Test bơm/van: i=nhát bơm, v=nhát xả, o=mở, c=đóng, q=thoát."""
        print("Actuator test — phím: i=bơm 0.3s, v=xả 0.3s, o=mở, c=đóng, q=thoát")
        try:
            while True:
                ch=input("> ").strip().lower()
                if ch=="q": break
                elif ch=="i": self.gpio.pump_on(); sleep_s(0.30); self.gpio.pump_off()
                elif ch=="v": self.gpio.valve_open(); sleep_s(0.30); self.gpio.valve_close()
                elif ch=="o": self.gpio.valve_open(); print("Valve OPEN")
                elif ch=="c": self.gpio.valve_close(); print("Valve CLOSE")
        finally:
            self.gpio.pump_off(); self.gpio.valve_open()

# -------------------- Menu ------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="BP Setup Harvester — Thu thập tham số BP")
    ap.add_argument("--config", type=str, default=str(CONFIG_PATH), help="Đường dẫn config/app_config.yaml")
    args = ap.parse_args()

    tool = BPHarvester(Path(args.config))
    tool.init_hw()
    try:
        while True:
            print("\n=== BP Setup Harvester (HX710B) ===")
            print(" 1) Offset watch (liên tục) → CSV tuỳ chọn")
            print(" 2) Đo offset nhanh (ghi offset_counts)")
            print(" 3) Invert-check (áp↑ -> counts ?)")
            print(" 4) SPS estimate (10/80)")
            print(" 5) Khởi tạo slope từ datasheet (3.3V)")
            print(" 6) Capture một phiên deflate (log JSON/CSV)")
            print(" 7) MAP lock (paired): nhập SYS/DIA để tinh slope")
            print(" 8) Fit sys_frac / dia_frac từ nhiều paired logs")
            print(" 9) LUT refine dP/dt từ một log deflate")
            print("10) Dump snapshot tham số hiện có")
            print("11) Actuator test (bơm/van)")
            print(" 0) Thoát")
            choice = input("Chọn: ").strip()

            if choice == "1":
                dur = float(input("Thời lượng (s, 0=đến khi Ctrl+C) [0]: ") or "0")
                win = int(input("Cửa sổ median (mặc định 101) [101]: ") or "101")
                path = input("CSV (để trống nếu không ghi) []: ").strip()
                csv_out = Path(path) if path else None
                tool.step_offset_watch(win=win, dur=dur, csv_out=csv_out)

            elif choice == "2":
                tool.step_offset_quick(samples=200)

            elif choice == "3":
                tool.step_invert_check()

            elif choice == "4":
                tool.step_sps(dur=3.0)

            elif choice == "5":
                A = float(input("Nhập hệ số suy hao A (0.2–0.4 điển hình) [0.25]: ") or "0.25")
                fso = float(input("FSO cảm biến @5V mV (50–100) [75]: ") or "75")
                tool.step_init_slope_from_datasheet(A=A, fso_mv_5v=fso, vref=3.3)

            elif choice == "6":
                out = tool.step_capture_deflate(out_prefix="bpdeflate")
                # hỏi thêm meta SYS/DIA để dùng sau (tuỳ chọn)
                try:
                    ans = input("Nhập SYS/DIA máy thương mại? (vd 124/78, Enter bỏ): ").strip()
                    if ans:
                        sys_str, dia_str = ans.split("/")
                        data = json.loads(out.read_text(encoding="utf-8"))
                        data["meta"] = {"sys_ref": float(sys_str), "dia_ref": float(dia_str)}
                        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                        LOG.info("Đã ghi meta SYS/DIA vào %s", out)
                except Exception:
                    LOG.warning("Bỏ qua meta SYS/DIA.")

            elif choice == "7":
                jp = Path(input("Chọn file JSON deflate: ").strip())
                sys_ref = float(input("SYS_ref: ").strip())
                dia_ref = float(input("DIA_ref: ").strip())
                tool.step_lock_map(jp, sys_ref=sys_ref, dia_ref=dia_ref)

            elif choice == "8":
                raw = input("Danh sách file JSON (cách nhau bởi dấu phẩy): ").strip()
                paths = [Path(x.strip()) for x in raw.split(",") if x.strip()]
                tool.step_fit_sys_dia(paths)

            elif choice == "9":
                jp = Path(input("Chọn file JSON deflate: ").strip())
                tgt = float(input("Target dP/dt (mmHg/s) [3.0]: ") or "3.0")
                tool.step_lut_refine(jp, target_dpdt=tgt)

            elif choice == "10":
                out = input("Lưu snapshot YAML (Enter=bỏ): ").strip()
                tool.step_dump_snapshot(Path(out) if out else None)

            elif choice == "11":
                tool.step_actuator_test()

            elif choice == "0":
                print("Tạm biệt!"); break
            else:
                print("Lựa chọn không hợp lệ.")
    finally:
        tool.close_hw()

if __name__ == "__main__":
    main()
