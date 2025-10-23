#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
hx710b_offset_watch.py — Theo dõi OFFSET (raw counts @ 0 mmHg) từ HX710B liên tục
- Van luôn mở, bơm luôn tắt để đảm bảo 0 mmHg (cuff thông khí).
- In ra: counts hiện tại, median cửa sổ trượt, lệch so với median (delta), ước lượng SPS.
- Tùy chọn ghi CSV để phân tích sau.

Yêu cầu:
- Raspberry Pi + RPi.GPIO
- PyYAML (để đọc adc_inverted từ config/app_config.yaml; nếu thiếu vẫn chạy với mặc định)

Mapping GPIO (KHÔNG đổi):
- Pump (4N35 LED):    GPIO26 (Luôn OFF trong script này)
- Valve (4N35 LED):   GPIO16 (Luôn ON để xả, giữ 0 mmHg)
- HX710B SCK:         GPIO5
- HX710B OUT/DOUT:    GPIO6

Tác giả: Đồ Án — IoT Health Monitor
"""

from __future__ import annotations

import argparse
import csv
import logging
import statistics
import sys
import time
from pathlib import Path
from typing import List, Optional

LOG = logging.getLogger("hx_offset")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

# ---------- Paths ----------
REPO_ROOT = Path(__file__).resolve().parents[1] if len(Path(__file__).parents) >= 2 else Path.cwd()
CONFIG_PATH = REPO_ROOT / "config" / "app_config.yaml"

# ---------- YAML (optional) ----------
def load_adc_inverted(cfg_path: Path) -> bool:
    try:
        import yaml  # type: ignore
        if cfg_path.exists():
            cfg = (yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {})
            return bool(
                cfg.get("sensors", {})
                   .get("hx710b", {})
                   .get("calibration", {})
                   .get("adc_inverted", False)
            )
    except Exception:
        pass
    return False

# ---------- GPIO ----------
try:
    import RPi.GPIO as GPIO  # type: ignore
    ON_PI = True
except Exception:
    print("Cảnh báo: không tìm thấy RPi.GPIO — có vẻ không chạy trên Raspberry Pi.", file=sys.stderr)
    ON_PI = False

GPIO_PUMP = 26   # Output -> LED 4N35 (bơm)
GPIO_VALVE = 16  # Output -> LED 4N35 (van xả NO)
GPIO_HX_SCK = 5  # Output -> HX710B SCK
GPIO_HX_OUT = 6  # Input  -> HX710B OUT/DOUT

def monotonic() -> float:
    return time.monotonic()

def sleep_s(s: float) -> None:
    if s > 0:
        time.sleep(s)

class Gpio:
    """Khởi tạo GPIO an toàn, giữ bơm OFF và van OPEN suốt phiên đo."""
    def __init__(self) -> None:
        self._inited = False

    def setup(self) -> None:
        if not ON_PI or self._inited:
            return
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(GPIO_PUMP, GPIO.OUT, initial=GPIO.LOW)   # pump OFF
        GPIO.setup(GPIO_VALVE, GPIO.OUT, initial=GPIO.HIGH) # valve OPEN (xả)
        GPIO.setup(GPIO_HX_SCK, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(GPIO_HX_OUT, GPIO.IN)
        self._inited = True
        LOG.info("GPIO initialized (pump OFF, valve OPEN).")

    def cleanup(self) -> None:
        if ON_PI and self._inited:
            try:
                GPIO.output(GPIO_PUMP, GPIO.LOW)
                GPIO.output(GPIO_VALVE, GPIO.HIGH)  # giữ mở khi thoát
            finally:
                GPIO.cleanup()
                self._inited = False
                LOG.info("GPIO cleanup done.")

    # HX710B primitives
    @staticmethod
    def _read_out() -> int:
        return 1 if GPIO.input(GPIO_HX_OUT) else 0

    @staticmethod
    def _clk_pulse() -> None:
        GPIO.output(GPIO_HX_SCK, GPIO.HIGH)
        GPIO.output(GPIO_HX_SCK, GPIO.LOW)

    @staticmethod
    def _ready() -> bool:
        return GPIO.input(GPIO_HX_OUT) == GPIO.LOW

class HX710B:
    """Đọc 24-bit từ HX710B; có hỗ trợ đảo dấu (adc_inverted)."""
    def __init__(self, gpio: Gpio, adc_inverted: bool = False) -> None:
        self.gpio = gpio
        self.adc_inverted = adc_inverted

    def read_raw(self, timeout_s: float = 0.3) -> Optional[int]:
        t0 = monotonic()
        while (monotonic() - t0) < timeout_s:
            if not ON_PI or Gpio._ready():
                val = 0
                # 24 bit
                for _ in range(24):
                    Gpio._clk_pulse()
                    bit = Gpio._read_out() if ON_PI else 0
                    val = (val << 1) | bit
                # 1 xung để chốt kênh/gain
                Gpio._clk_pulse()
                # signed 24-bit
                if val & 0x800000:
                    val -= 1 << 24
                if self.adc_inverted:
                    val = -val
                return val
            sleep_s(0.001)
        return None

# ---------- Core loop ----------
def rolling_median(buf: List[int]) -> int:
    return int(statistics.median(buf)) if buf else 0

def main() -> None:
    p = argparse.ArgumentParser(description="Xem OFFSET HX710B liên tục (van mở, bơm tắt).")
    p.add_argument("--win", type=int, default=101, help="Cửa sổ median trượt (mặc định 101 mẫu).")
    p.add_argument("--dur", type=float, default=0.0, help="Thời lượng chạy (s); 0 = chạy đến khi Ctrl+C.")
    p.add_argument("--csv", type=str, default="", help="Đường dẫn CSV để log (tùy chọn).")
    args = p.parse_args()

    adc_inv = load_adc_inverted(CONFIG_PATH)
    print(f"adc_inverted={adc_inv}")

    gpio = Gpio()
    gpio.setup()
    hx = HX710B(gpio, adc_inverted=adc_inv)

    csv_writer = None
    csv_file = None
    if args.csv:
        out = Path(args.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        csv_file = out.open("w", newline="", encoding="utf-8")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["t", "counts", "median", "delta"])

    buf: List[int] = []
    maxlen = max(3, int(args.win))
    t0 = monotonic()
    n_sps = 0
    last_sps_t = t0

    print("Đang theo dõi offset @ 0 mmHg (van mở, bơm tắt). Nhấn Ctrl+C để thoát.")
    print("Cột: counts hiện tại | median(win) | delta=counts - median | SPS≈.. (mỗi ~2s)")

    try:
        while True:
            v = hx.read_raw(timeout_s=0.3)
            if v is None:
                # đọc lỗi/timeout — in chấm để biết còn chạy
                sys.stdout.write("."); sys.stdout.flush()
                continue

            buf.append(v)
            if len(buf) > maxlen:
                buf.pop(0)
            med = rolling_median(buf)
            delta = v - med
            n_sps += 1
            now = monotonic()
            line = f"\rcounts={v:>8d} | med({maxlen})={med:>8d} | delta={delta:>6d}"

            # in SPS mỗi ~2s
            if now - last_sps_t >= 2.0:
                sps = n_sps / (now - last_sps_t)
                line += f" | SPS≈{sps:4.1f}"
                n_sps = 0
                last_sps_t = now

            sys.stdout.write(line)
            sys.stdout.flush()

            if csv_writer:
                csv_writer.writerow([f"{now - t0:.3f}", v, med, delta])

            # tự dừng nếu có --dur
            if args.dur > 0 and (now - t0) >= args.dur:
                print("\nHết thời lượng --dur, thoát.")
                break

            # pace ~10–12 Hz (HX710B ~10–12 SPS mode 10SPS)
            sleep_s(0.02)

    except KeyboardInterrupt:
        print("\nNgười dùng yêu cầu thoát (Ctrl+C).")
    finally:
        try:
            if csv_file:
                csv_file.close()
        finally:
            gpio.cleanup()

if __name__ == "__main__":
    main()
