#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Manual pressure inflate control
-------------------------------
Bơm đến áp suất mục tiêu (mmHg) rồi dừng, có kiểm soát an toàn.

Yêu cầu:
- HX710B driver: src/sensors/hx710b_driver.py
- Bơm: GPIO26 (active HIGH)
- Van NO: GPIO16 (active HIGH để ĐÓNG)
- Nguồn 6 V tách biệt (cách ly qua opto)
"""

import time
import logging
import RPi.GPIO as GPIO
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]  # .../IoT_health
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.sensors.hx710b_driver import HX710BDriver, HX710Mode

# --- cấu hình cơ bản ---
GPIO_PUMP = 26      # bơm
GPIO_VALVE = 16     # van NO (HIGH = đóng)
PRESSURE_TARGET = 190.0   # mmHg
PRESSURE_LIMIT = 200.0    # an toàn mềm
TIMEOUT_S = 25            # timeout bơm
SLOPE = 0.000035765743256     # mmHg/count (theo datasheet)
OFFSET = 1357387          # offset đã hiệu chỉnh

log = logging.getLogger("inflate_control")


def counts_to_mmhg(counts: int) -> float:
    """Chuyển đổi counts → mmHg"""
    return (counts - OFFSET) * SLOPE


def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(GPIO_PUMP, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(GPIO_VALVE, GPIO.OUT, initial=GPIO.LOW)  # NO: LOW = mở
    log.info("GPIO ready: pump=%d valve=%d", GPIO_PUMP, GPIO_VALVE)


def safe_stop():
    """Dừng bơm, mở van"""
    GPIO.output(GPIO_PUMP, GPIO.LOW)
    GPIO.output(GPIO_VALVE, GPIO.LOW)
    log.info("Pump OFF, valve OPEN")


def main():
    setup_gpio()
    hx = HX710BDriver(gpio_dout=6, gpio_sck=5, mode=HX710Mode.DIFFERENTIAL_10SPS)
    hx.initialize()

    log.info("Target pressure: %.1f mmHg", PRESSURE_TARGET)
    GPIO.output(GPIO_VALVE, GPIO.HIGH)   # đóng van (NO)
    time.sleep(0.3)
    GPIO.output(GPIO_PUMP, GPIO.HIGH)    # bật bơm

    t0 = time.time()
    try:
        while True:
            val = hx.read()
            if val is None:
                continue
            p = counts_to_mmhg(val)
            print(f"\rPressure: {p:7.2f} mmHg", end="", flush=True)

            if p >= PRESSURE_TARGET:
                log.info("\nReached target (%.1f mmHg) → stop pump", p)
                GPIO.output(GPIO_PUMP, GPIO.LOW)
                time.sleep(1.5)
                GPIO.output(GPIO_VALVE, GPIO.LOW)  # mở xả
                break

            if p >= PRESSURE_LIMIT:
                log.warning("\nOverpressure! (%.1f mmHg) → emergency stop", p)
                safe_stop()
                break

            if (time.time() - t0) > TIMEOUT_S:
                log.warning("\nTimeout inflate → safety stop")
                safe_stop()
                break

            time.sleep(0.1)

    except KeyboardInterrupt:
        log.info("User aborted.")
        safe_stop()
    finally:
        hx.cleanup()
        GPIO.cleanup()
        print("\nDone.")


if __name__ == "__main__":
    main()
