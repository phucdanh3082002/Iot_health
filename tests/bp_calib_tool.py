#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/bp_calib_tool.py

Bộ công cụ 1 file để thu thập các giá trị hiệu chuẩn & tối ưu đo huyết áp (HX710B):

📋 CALIBRATION & DATA COLLECTION:
- offset-electric  : offset 0 mmHg khi KHÔNG đeo cuff (van mở) ❌ bơm
- offset-cuff      : offset 0 mmHg khi CÓ đeo cuff (van mở) ❌ bơm
- noise            : đo nhiễu nền (RMS, MAD) & PSD 50/60 Hz ❌ bơm
- sps              : ước lượng tần số lấy mẫu thực (SPS) ❌ bơm
- slope            : fit slope mmHg/count từ các điểm chuẩn ✅ cần bơm + manometer
- capture-deflate  : đo một pha xả (deflate) đầy đủ ✅ cần bơm
- capture-paired   : thu oscillometric + nhập reference SYS/DIA ✅ cần bơm

🔧 AUTOMATION & ANALYSIS:
- batch-calib-suite: chạy tự động offset→noise→sps→slope ✅ cần bơm cho slope
- safety-check     : kiểm tra GPIO/bơm/van/offset ✅ test bơm 0.5s
- visualize-envelope: vẽ đồ thị envelope & mark MAP/SYS/DIA (cần matplotlib)
- analyze-replay   : phân tích lại file JSON dữ liệu đã thu
- commit           : cập nhật app_config.yaml các khóa an toàn (offset/slope/SPS…)

💻 SỬ DỤNG:
1. Chế độ MENU TƯƠNG TÁC (khuyến nghị):
   python tests/bp_calib_tool.py
   hoặc
   python tests/bp_calib_tool.py menu

2. Chế độ CLI (lệnh cụ thể):
   python tests/bp_calib_tool.py offset-electric --dur 6 --out offset_electric.json
   python tests/bp_calib_tool.py slope --points 0 100 150 --out slope_fit.json
   python tests/bp_calib_tool.py capture-paired --out paired_001.json
   python tests/bp_calib_tool.py batch-calib-suite
   python tests/bp_calib_tool.py commit --from slope_fit.json --keys slope offset

🔒 AN TOÀN:
- Luôn chạy safety-check trước khi đo lần đầu
- Kiểm tra relief valve (250-300 mmHg) đã lắp
- Không vượt quá 200 mmHg khi bơm
- Van xả (GPIO16) là NO (Normally Open) → mặc định an toàn

📁 OUTPUT:
- Các file JSON lưu trong thư mục chỉ định hoặc data/calibration_YYYYMMDD_HHMMSS/
- Dùng visualize-envelope để xem đồ thị nhanh
- Dùng commit để ghi kết quả vào app_config.yaml

Yêu cầu:
- Không sinh dữ liệu giả; cần phần cứng thực (trừ analyze-replay).
- Không đổi public schema dự án.

"""

import sys
import os
import time
import json
import math
import argparse
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

# Thêm root project vào sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml
import statistics
import numpy as np

# Import driver & logger của dự án (không đổi)
from src.sensors.blood_pressure_sensor import BloodPressureSensor
from src.utils.logger import get_logger

LOG = get_logger("tests.bp_calib_tool")

# ========================= TIỆN ÍCH CHUNG =========================

def load_config(config_path: Path) -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    bp_cfg = cfg.get("sensors", {}).get("blood_pressure", {})
    hx_cfg = cfg.get("sensors", {}).get("hx710b", {})
    if not bp_cfg or not hx_cfg:
        raise RuntimeError("Không tìm thấy sensors.blood_pressure hoặc sensors.hx710b trong app_config.yaml")
    merged = dict(bp_cfg)
    merged["hx710b"] = hx_cfg
    return cfg  # trả nguyên file cấu hình đầy đủ

def merged_bp_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    bp_cfg = cfg.get("sensors", {}).get("blood_pressure", {})
    hx_cfg = cfg.get("sensors", {}).get("hx710b", {})
    merged = dict(bp_cfg)
    merged["hx710b"] = hx_cfg
    return merged

def robust_stats(x: List[float]) -> Dict[str, float]:
    """Median, MAD, std_est (MAD*1.4826), RMS (lưu ý RMS theo lệch so median)."""
    if not x:
        return dict(median=0.0, mad=0.0, std_est=0.0, rms=0.0)
    med = float(np.median(x))
    mad = float(np.median(np.abs(np.array(x) - med)))
    std_est = 1.4826 * mad
    rms = float(np.sqrt(np.mean((np.array(x) - med)**2)))
    return dict(median=med, mad=mad, std_est=std_est, rms=rms)

def hampel_mask(x: np.ndarray, k: int = 7, t: float = 3.0) -> np.ndarray:
    """Trả về mask boolean đánh dấu outlier (True = outlier) theo Hampel."""
    n = len(x)
    if n < 2*k+1:
        return np.zeros(n, dtype=bool)
    out = np.zeros(n, dtype=bool)
    for i in range(k, n-k):
        window = x[i-k:i+k+1]
        med = np.median(window)
        mad = np.median(np.abs(window - med))
        sigma = 1.4826 * mad if mad > 0 else 0
        if sigma > 0 and abs(x[i] - med) > t * sigma:
            out[i] = True
    return out

def compute_psd_approx(x: np.ndarray, fs: float) -> Dict[str, float]:
    """Tính PSD thô quanh 50/60 Hz (nếu fs đủ cao)."""
    if fs <= 0 or len(x) < 8:
        return {"psd_50": 0.0, "psd_60": 0.0}
    # Demean
    x = x - np.mean(x)
    # FFT
    X = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), d=1.0/fs)
    def band_power(f0: float, bw: float = 1.0) -> float:
        idx = np.where((freqs >= f0-bw/2) & (freqs <= f0+bw/2))[0]
        if idx.size == 0:
            return 0.0
        return float(np.sum(np.abs(X[idx])**2) / idx.size)
    return {"psd_50": band_power(50.0), "psd_60": band_power(60.0)}

def ensure_gpio_silence():
    """Tắt cảnh báo GPIO nếu có."""
    try:
        import RPi.GPIO as GPIO
        GPIO.setwarnings(False)
    except Exception:
        pass

def sensor_boot(cfg_full: Dict[str, Any]) -> BloodPressureSensor:
    merged = merged_bp_cfg(cfg_full)
    sensor = BloodPressureSensor(merged)
    ensure_gpio_silence()
    if not sensor.start():
        raise RuntimeError("Khởi tạo BloodPressureSensor thất bại")
    return sensor

def valve_open(sensor: BloodPressureSensor):
    try:
        sensor._valve_open()
    except Exception:
        pass

def valve_close(sensor: BloodPressureSensor):
    try:
        sensor._valve_close()
    except Exception:
        pass

def safe_cleanup(sensor: BloodPressureSensor):
    try:
        sensor.cleanup()
    except Exception:
        pass

# ========================= 1) OFFSET 0 mmHg =========================

def cmd_offset(args, cfg_full):
    """
    Đo offset 0 mmHg (counts) khi van OPEN.
    --mode electric : KHÔNG đeo cuff (ống thẳng, không đè)
    --mode cuff     : CÓ đeo cuff (van vẫn mở)
    """
    sensor = sensor_boot(cfg_full)
    try:
        valve_open(sensor)
        time.sleep(0.8)  # cân bằng khí quyển

        N = int(max(50, args.samples))
        sps_hint = cfg_full.get("sensors", {}).get("hx710b", {}).get("sps_hint", 50)
        dt = 1.0 / max(1.0, float(sps_hint))
        raw = []

        LOG.info(f"Thu {N} mẫu offset @~{sps_hint} SPS, mode={args.mode}")
        t0 = time.time()
        # dùng hàm đọc nội bộ của driver (bit-banged HX710B)
        for i in range(N):
            v = sensor._read_adc_value(timeout=0.2)  # dùng nội bộ, an toàn trong test
            if v is not None:
                raw.append(int(v))
            time.sleep(dt)

        if len(raw) < max(30, N//2):
            raise RuntimeError(f"Thu {len(raw)}/{N} mẫu — quá ít, kiểm tra phần cứng/van.")

        x = np.array(raw, dtype=float)
        mask = hampel_mask(x, k=7, t=3.0)
        x_clean = x[~mask]
        stats_all = robust_stats(raw)
        stats_clean = robust_stats(x_clean.tolist())

        out = {
            "mode": args.mode,
            "samples": len(raw),
            "samples_after_hampel": int(len(x_clean)),
            "stats_all": stats_all,
            "stats_clean": stats_clean,
            "offset_counts_recommend": int(round(stats_clean["median"])),
            "raw_preview": raw[:10],
            "ts": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(out, f, indent=2, ensure_ascii=False)
            LOG.info(f"Đã lưu {args.out}")

        print("\nKẾT QUẢ OFFSET")
        print("-"*40)
        print(f"  Mode               : {args.mode}")
        print(f"  Mẫu (thô/clean)    : {len(raw)} / {len(x_clean)}")
        print(f"  Median (clean)     : {stats_clean['median']:.1f} counts")
        print(f"  MAD (clean)        : {stats_clean['mad']:.1f} counts")
        print(f"  RMS (clean)        : {stats_clean['rms']:.1f} counts")
        print(f"  Gợi ý offset_counts: {out['offset_counts_recommend']}")

    finally:
        safe_cleanup(sensor)

# ========================= 2) NOISE / PSD =========================

def cmd_noise(args, cfg_full):
    """
    Đo nhiễu nền và PSD 50/60 Hz tại 0 mmHg (van OPEN).
    """
    sensor = sensor_boot(cfg_full)
    try:
        valve_open(sensor)
        time.sleep(1.0)
        dur = float(args.dur)
        sps_hint = cfg_full.get("sensors", {}).get("hx710b", {}).get("sps_hint", 50)
        dt = 1.0 / max(1.0, float(sps_hint))
        raw: List[int] = []

        LOG.info(f"Đo noise {dur:.1f}s @~{sps_hint} SPS")
        t_end = time.time() + dur
        while time.time() < t_end:
            v = sensor._read_adc_value(timeout=0.2)
            if v is not None:
                raw.append(int(v))
            time.sleep(dt)

        if len(raw) < max(50, dur * sps_hint * 0.5):
            raise RuntimeError(f"Dữ liệu quá ít: {len(raw)}")

        stats_clean = robust_stats(raw)
        # ước lượng fs thực từ thời lượng & số mẫu
        fs_est = len(raw) / max(0.001, dur)
        psd = compute_psd_approx(np.array(raw, dtype=float), fs=fs_est)

        out = {
            "duration_s": dur,
            "samples": len(raw),
            "fs_est_hz": fs_est,
            "noise_stats": stats_clean,
            "psd_approx": psd,
            "ts": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(out, f, indent=2, ensure_ascii=False)
            LOG.info(f"Đã lưu {args.out}")

        print("\nKẾT QUẢ NOISE/PSD")
        print("-"*40)
        print(f"  fs_est (Hz)        : {fs_est:.2f}")
        print(f"  Median (counts)    : {stats_clean['median']:.1f}")
        print(f"  RMS (counts)       : {stats_clean['rms']:.1f}")
        print(f"  PSD@50/60Hz (arb)  : {psd['psd_50']:.2e} / {psd['psd_60']:.2e}")

    finally:
        safe_cleanup(sensor)

# ========================= 3) SPS THỰC =========================

def cmd_sps(args, cfg_full):
    """
    Ước lượng tần số lấy mẫu thực (Hz) bằng cách đo chuỗi ngắn.
    """
    sensor = sensor_boot(cfg_full)
    try:
        valve_open(sensor)
        time.sleep(0.5)
        dur = float(args.dur)
        sps_hint = cfg_full.get("sensors", {}).get("hx710b", {}).get("sps_hint", 50)
        dt = 1.0 / max(1.0, float(sps_hint))
        ts: List[float] = []
        t0 = time.time()
        while time.time() - t0 < dur:
            v = sensor._read_adc_value(timeout=0.2)
            now = time.time()
            if v is not None:
                ts.append(now)
            time.sleep(dt)

        if len(ts) < 5:
            raise RuntimeError("Không đủ điểm để ước lượng SPS")

        diffs = np.diff(np.array(ts))
        fs_est = 1.0 / float(np.median(diffs))
        out = {
            "duration_s": dur,
            "samples": len(ts),
            "fs_est_hz": fs_est,
            "ts": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(out, f, indent=2, ensure_ascii=False)
            LOG.info(f"Đã lưu {args.out}")

        print("\nKẾT QUẢ SPS")
        print("-"*40)
        print(f"  Mẫu: {len(ts)}")
        print(f"  fs_est (Hz): {fs_est:.2f}")

    finally:
        safe_cleanup(sensor)

# ========================= 4) SLOPE mmHg/count =========================

def cmd_slope(args, cfg_full):
    """
    Fit slope mmHg/count từ các điểm chuẩn với điều khiển bơm/van TỰ ĐỘNG.
    Bạn cung cấp các điểm tham chiếu mmHg qua --points, ví dụ: 0 100 150.
    
    Quy trình TỰ ĐỘNG cho mỗi điểm:
    1. Bơm đến áp mục tiêu (với tolerance ±2 mmHg)
    2. Đóng van để giữ áp ổn định
    3. Thu mẫu ADC trong 3-5s
    4. Xả về 0 mmHg trước khi chuyển điểm tiếp theo
    
    *Lưu ý: Cần calibration offset/slope sơ bộ để đọc được áp hiện tại!
    """
    sensor = sensor_boot(cfg_full)
    try:
        ref_points = [float(p) for p in args.points]
        if len(ref_points) < 2:
            raise RuntimeError("Cần ≥2 điểm tham chiếu mmHg để fit tuyến tính")
        
        # Sort để bơm từ thấp đến cao (tránh phải xả nhiều)
        ref_points = sorted(ref_points)

        N = int(max(80, args.samples))
        sps_hint = cfg_full.get("sensors", {}).get("hx710b", {}).get("sps_hint", 50)
        dt = 1.0 / max(1.0, float(sps_hint))
        
        # Thông số điều khiển
        TOLERANCE_MMHG = 2.0          # ±2 mmHg chấp nhận được
        PUMP_STEP_DURATION = 0.3      # Bơm từng burst 0.3s
        STABILIZE_TIME = 2.0          # Đợi áp ổn định trước khi thu mẫu
        MAX_PUMP_TIME = 30.0          # Timeout bơm (an toàn)
        DEFLATE_TIME = 3.0            # Thời gian xả giữa các điểm

        pairs: List[Tuple[int, float]] = []  # (counts_median, mmHg_ref)

        print("\n" + "="*60)
        print("  AUTOMATIC SLOPE CALIBRATION")
        print("="*60)
        print(f"\nĐiểm chuẩn: {ref_points} mmHg")
        print("\nQuy trình TỰ ĐỘNG:")
        print("  1. Bơm đến áp mục tiêu (±2 mmHg)")
        print("  2. Đóng van, đợi ổn định 2s")
        print("  3. Thu mẫu ADC")
        print("  4. Xả về 0 mmHg")
        print("\n⚠ Kiểm tra:")
        print("  - Relief valve đã lắp?")
        print("  - Cuff/ống nối kín khí?")
        print("  - Calibration offset/slope sơ bộ đã có?")
        input("\n→ Nhấn ENTER để bắt đầu...")

        for i, target_mmhg in enumerate(ref_points, 1):
            print(f"\n{'='*60}")
            print(f"[{i}/{len(ref_points)}] Điểm chuẩn: {target_mmhg:.1f} mmHg")
            print("="*60)
            
            # Helper: đọc áp hiện tại
            def read_current_pressure() -> float:
                raw = sensor._read_adc_value(timeout=0.2)
                if raw is None:
                    return 0.0
                corrected = raw - sensor._offset_counts
                if sensor._adc_inverted:
                    pressure = -corrected * sensor._slope
                else:
                    pressure = corrected * sensor._slope
                return max(0.0, pressure)
            
            # BƯỚC 1: Bơm đến target (nếu target > 0)
            if target_mmhg > 0.5:
                LOG.info(f"Bơm đến {target_mmhg:.1f} mmHg...")
                print(f"  [1/4] Đang bơm đến {target_mmhg:.1f} mmHg...")
                valve_close(sensor)
                time.sleep(0.2)
                
                pump_start = time.time()
                last_pressure = 0.0
                
                while True:
                    current_p = read_current_pressure()
                    
                    # Kiểm tra đã đạt target
                    if abs(current_p - target_mmhg) <= TOLERANCE_MMHG:
                        sensor._pump_off()
                        print(f"    ✅ Đạt {current_p:.1f} mmHg (target {target_mmhg:.1f})")
                        break
                    
                    # Kiểm tra timeout
                    if time.time() - pump_start > MAX_PUMP_TIME:
                        sensor._pump_off()
                        raise RuntimeError(f"Timeout bơm sau {MAX_PUMP_TIME}s — kiểm tra rò khí!")
                    
                    # Kiểm tra quá áp
                    if current_p > sensor.safety_pressure:
                        sensor._pump_off()
                        valve_open(sensor)
                        raise RuntimeError(f"Quá áp an toàn ({sensor.safety_pressure} mmHg)!")
                    
                    # Điều khiển bơm
                    if current_p < target_mmhg - TOLERANCE_MMHG:
                        # Cần bơm thêm
                        sensor._pump_on()
                        time.sleep(PUMP_STEP_DURATION)
                        sensor._pump_off()
                        time.sleep(0.1)  # Đợi áp tăng
                    else:
                        # Gần đến target, dừng bơm
                        sensor._pump_off()
                        time.sleep(0.5)
                    
                    # Debug output (mỗi giây)
                    if current_p != last_pressure:
                        print(f"    Áp hiện tại: {current_p:.1f} mmHg", end='\r')
                        last_pressure = current_p
                
                # BƯỚC 2: Đóng van, đợi ổn định
                print(f"\n  [2/4] Đóng van, đợi ổn định {STABILIZE_TIME}s...")
                valve_close(sensor)
                time.sleep(STABILIZE_TIME)
                
            else:
                # Điểm 0 mmHg: chỉ cần mở van
                print(f"  [1/4] Điểm 0 mmHg: mở van...")
                valve_open(sensor)
                time.sleep(2.0)
                print(f"  [2/4] Đã ổn định tại 0 mmHg")
            
            # BƯỚC 3: Thu mẫu
            print(f"  [3/4] Thu {N} mẫu ADC...")
            LOG.info(f"Thu mẫu tại {target_mmhg} mmHg")
            vals: List[int] = []
            pressures_check: List[float] = []
            
            for k in range(N):
                raw = sensor._read_adc_value(timeout=0.2)
                if raw is not None:
                    vals.append(int(raw))
                    # Kiểm tra áp có ổn định không
                    if k % 20 == 0:
                        p_check = read_current_pressure()
                        pressures_check.append(p_check)
                time.sleep(dt)
            
            if len(vals) < max(30, N//2):
                raise RuntimeError(f"Điểm {target_mmhg}: thu {len(vals)}/{N} mẫu — quá ít.")
            
            # Kiểm tra áp có drift nhiều không
            if len(pressures_check) > 2:
                pressure_std = float(np.std(pressures_check))
                if pressure_std > 5.0:
                    LOG.warning(f"Áp không ổn định: std={pressure_std:.2f} mmHg")
                    print(f"    ⚠ Cảnh báo: Áp dao động ±{pressure_std:.1f} mmHg")
            
            # Xử lý dữ liệu
            x = np.array(vals, dtype=float)
            mask = hampel_mask(x, k=7, t=3.0)
            x_clean = x[~mask]
            med = float(np.median(x_clean))
            pairs.append((int(round(med)), target_mmhg))
            
            print(f"    ✅ median counts={med:.1f} @ {target_mmhg:.1f} mmHg")
            print(f"       (clean {len(x_clean)}/{len(x)} samples)")
            
            # BƯỚC 4: Xả về 0 (trừ điểm cuối)
            if i < len(ref_points):
                print(f"  [4/4] Xả về 0 mmHg...")
                valve_open(sensor)
                time.sleep(DEFLATE_TIME)
                current_p = read_current_pressure()
                print(f"    Áp sau xả: {current_p:.1f} mmHg")
            else:
                print(f"  [4/4] Hoàn tất (điểm cuối)")
                valve_open(sensor)
                time.sleep(1.0)

        # ============ FIT TUYẾN TÍNH ============
        print(f"\n{'='*60}")
        print("FIT SLOPE mmHg/count")
        print("="*60)
        
        # Fit tuyến tính: mmHg ≈ slope*(counts - offset)
        counts = np.array([p[0] for p in pairs], dtype=float)
        refs   = np.array([p[1] for p in pairs], dtype=float)
        # fit y = a*x + b
        a, b = np.polyfit(counts, refs, 1)
        # Tính offset_counts sao cho 0 mmHg → counts_offset
        # 0 = a*offset + b → offset = -b/a
        if abs(a) < 1e-12:
            raise RuntimeError("Slope quá nhỏ, fit không hợp lệ.")
        offset_counts = -b / a
        # R^2
        y_pred = a*counts + b
        ss_res = np.sum((refs - y_pred)**2)
        ss_tot = np.sum((refs - np.mean(refs))**2)
        r2 = 1.0 - (ss_res / ss_tot if ss_tot > 0 else 0)

        out = {
            "pairs": [{"counts_median": int(c), "mmHg_ref": float(r)} for c, r in pairs],
            "fit": {
                "slope_mmhg_per_count": float(a),
                "intercept_mmhg": float(b),
                "offset_counts": float(offset_counts),
                "r2": float(r2)
            },
            "method": "automatic_pump_control",
            "ts": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(out, f, indent=2, ensure_ascii=False)
            LOG.info(f"Đã lưu {args.out}")

        print("\nKẾT QUẢ FIT SLOPE")
        print("-"*60)
        print(f"  slope (mmHg/count): {a:.6f}")
        print(f"  offset_counts     : {offset_counts:.1f}")
        print(f"  R^2               : {r2:.6f}")
        print("\nĐiểm đo:")
        for c, r in pairs:
            pred = a * c + b
            err = abs(pred - r)
            print(f"  {r:6.1f} mmHg → counts {c:8d} (err: {err:.2f} mmHg)")

    finally:
        safe_cleanup(sensor)

# ========================= 5) CAPTURE DEFLATE =========================

def cmd_capture_deflate(args, cfg_full):
    """
    Thực hiện một chu trình đo để ghi riêng pha DEFLATE cho phân tích dP/dt & envelope.
    (Sử dụng luồng đo chuẩn trong driver, không đổi API.)
    """
    sensor = sensor_boot(cfg_full)
    try:
        if not sensor.start_measurement():
            raise RuntimeError("start_measurement() thất bại")
        raw = sensor.read_raw_data()
        if not raw or raw.get("read_size", 0) == 0:
            raise RuntimeError("Không thu được dữ liệu deflate")

        # Phân tích tốc độ xả
        pressures = raw.get("pressure") or []
        duration = raw.get("duration") or 0.0
        timestamps = raw.get("timestamps")
        def analyze_dpdt(pressures, timestamps=None, duration=None):
            if timestamps and len(timestamps) == len(pressures):
                rates = []
                for i in range(1, len(pressures)):
                    dt = timestamps[i]-timestamps[i-1]
                    if dt > 1e-4:
                        rates.append(abs((pressures[i]-pressures[i-1]) / dt))
                if rates:
                    return dict(method="timestamps", avg=float(np.mean(rates)),
                                max=float(np.max(rates)), min=float(np.min(rates)))
            if duration and duration > 0 and len(pressures) > 1:
                dt = duration / (len(pressures)-1)
                rates = [abs((pressures[i]-pressures[i-1]) / dt) for i in range(1, len(pressures))]
                if rates:
                    return dict(method="duration_even", avg=float(np.mean(rates)),
                                max=float(np.max(rates)), min=float(np.min(rates)))
            return dict(method="unknown", avg=0.0, max=0.0, min=0.0)

        dpdt = analyze_dpdt(pressures, timestamps, duration)

        # Xử lý BP để tham chiếu
        result = sensor.process_data(raw)
        qa = sensor.get_measurement_quality()

        bundle = {
            "metadata": {
                "collection_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "mode": "real_hardware",
                "sensor_config": merged_bp_cfg(cfg_full)
            },
            "raw_oscillometric_data": {
                "adc_counts": raw.get("raw", []),
                "pressure_mmhg": pressures,
                "timestamps": timestamps,
                "sample_count": raw.get("read_size"),
                "duration_seconds": duration
            },
            "calculated_bp": result,
            "quality_metrics": qa,
            "deflate_dpdt": dpdt
        }

        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(bundle, f, indent=2, ensure_ascii=False)
            LOG.info(f"Đã lưu {args.out}")

        print("\nKẾT QUẢ CAPTURE DEFLATE")
        print("-"*40)
        print(f"  N điểm     : {raw.get('read_size')}")
        print(f"  duration(s): {duration:.3f}")
        print(f"  dP/dt avg  : {dpdt['avg']:.2f} mmHg/s (mục tiêu 2–4)")
        if result:
            print(f"  SYS/DIA/MAP: {result.get('systolic')}/{result.get('diastolic')}/{result.get('map')} mmHg")

    finally:
        safe_cleanup(sensor)

# ========================= 6) ANALYZE REPLAY JSON =========================

def cmd_analyze_replay(args, cfg_full):
    """
    Phân tích lại một file JSON dữ liệu đã thu (không sinh data).
    Tính dP/dt & (tuỳ chọn) chạy process_data() để tính BP.
    """
    p = Path(args.json).resolve()
    if not p.exists():
        raise SystemExit(f"Không tìm thấy file: {p}")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    sensor = BloodPressureSensor(merged_bp_cfg(cfg_full))
    raw = data.get("raw_oscillometric_data", {})
    norm = {
        "pressure": raw.get("pressure_mmhg") or raw.get("pressure") or [],
        "raw": raw.get("adc_counts") or raw.get("raw") or [],
        "read_size": raw.get("sample_count") or (len(raw.get("pressure_mmhg", [])) if raw.get("pressure_mmhg") else 0),
        "duration": raw.get("duration_seconds"),
        "timestamps": raw.get("timestamps"),
    }

    pressures = norm.get("pressure") or []
    duration = norm.get("duration")
    timestamps = norm.get("timestamps")

    # dP/dt
    def analyze_dpdt(pressures, timestamps=None, duration=None):
        if timestamps and len(timestamps) == len(pressures):
            rates = []
            for i in range(1, len(pressures)):
                dt = timestamps[i]-timestamps[i-1]
                if dt > 1e-4:
                    rates.append(abs((pressures[i]-pressures[i-1]) / dt))
            if rates:
                return dict(method="timestamps", avg=float(np.mean(rates)),
                            max=float(np.max(rates)), min=float(np.min(rates)))
        if duration and duration > 0 and len(pressures) > 1:
            dt = duration / (len(pressures)-1)
            rates = [abs((pressures[i]-pressures[i-1]) / dt) for i in range(1, len(pressures))]
            if rates:
                return dict(method="duration_even", avg=float(np.mean(rates)),
                            max=float(np.max(rates)), min=float(np.min(rates)))
        return dict(method="unknown", avg=0.0, max=0.0, min=0.0)

    dpdt = analyze_dpdt(pressures, timestamps, duration)
    print("\nANALYZE REPLAY")
    print("-"*40)
    print(f"  N điểm       : {norm.get('read_size')}")
    print(f"  duration (s) : {duration}")
    print(f"  dP/dt avg    : {dpdt['avg']:.2f} mmHg/s")

    if args.compute_bp:
        res = sensor.process_data(norm)
        qa = sensor.get_measurement_quality()
        print("\nPROCESS_DATA")
        print("-"*40)
        if res:
            print(f"  SYS/DIA/MAP  : {res.get('systolic')}/{res.get('diastolic')}/{res.get('map')} mmHg")
        else:
            print("  ! Không tính được BP")
        print("\nQA")
        for k, v in (qa or {}).items():
            print(f"  {k}: {v}")

# ========================= 7) CAPTURE PAIRED (oscillometric + reference) =========================

def cmd_capture_paired(args, cfg_full):
    """
    Thực hiện một chu trình đo đầy đủ (inflate→deflate) và nhập giá trị tham chiếu
    SYS/DIA từ máy đo huyết áp chuẩn để lưu paired data cho tối ưu sys_frac/dia_frac.
    
    Quy trình:
    1. Chuẩn bị: đeo cuff cho đối tượng, chuẩn bị máy tham chiếu
    2. Tool chạy measurement → thu raw oscillometric data
    3. Nhập reference SYS/DIA từ máy tham chiếu
    4. Lưu bundle JSON với cả raw data và reference
    """
    sensor = sensor_boot(cfg_full)
    try:
        print("\n" + "="*50)
        print("  CAPTURE PAIRED MEASUREMENT")
        print("="*50)
        print("\nQuy trình:")
        print("  1. Đeo cuff cho đối tượng (vị trí chuẩn trên cánh tay)")
        print("  2. Chuẩn bị máy đo huyết áp tham chiếu (hoặc ghi nhận đo trước đó)")
        print("  3. Nhấn ENTER để bắt đầu đo oscillometric...")
        print("  4. Sau khi đo xong, nhập SYS/DIA từ máy tham chiếu")
        print()
        input("→ Sẵn sàng? Nhấn ENTER để tiếp tục...")
        
        # Chạy measurement
        LOG.info("Bắt đầu paired measurement...")
        if not sensor.start_measurement():
            raise RuntimeError("start_measurement() thất bại")
        
        raw = sensor.read_raw_data()
        if not raw or raw.get("read_size", 0) == 0:
            raise RuntimeError("Không thu được dữ liệu oscillometric")
        
        # Process để tính BP predicted
        result = sensor.process_data(raw)
        qa = sensor.get_measurement_quality()
        
        print("\n✅ Đo oscillometric hoàn tất!")
        if result:
            print(f"   Predicted: SYS={result.get('systolic')} DIA={result.get('diastolic')} MAP={result.get('map')} mmHg")
        
        # Nhập reference
        print("\n→ Nhập giá trị huyết áp từ máy tham chiếu:")
        while True:
            try:
                ref_sys = input("  SYS (mmHg): ").strip()
                ref_dia = input("  DIA (mmHg): ").strip()
                ref_sys = int(ref_sys)
                ref_dia = int(ref_dia)
                if ref_sys <= ref_dia or ref_sys < 50 or ref_dia < 30:
                    print("  ⚠ Giá trị không hợp lý, nhập lại...")
                    continue
                break
            except (ValueError, KeyboardInterrupt):
                print("  ⚠ Nhập không hợp lệ, thử lại...")
        
        # Metadata
        subject_id = input("  Subject ID (optional, Enter để bỏ qua): ").strip() or "unknown"
        notes = input("  Ghi chú (optional): ").strip() or ""
        
        # Bundle output
        bundle = {
            "metadata": {
                "collection_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "mode": "paired_real_hardware",
                "subject_id": subject_id,
                "notes": notes,
                "sensor_config": merged_bp_cfg(cfg_full)
            },
            "raw_oscillometric_data": {
                "adc_counts": raw.get("raw", []),
                "pressure_mmhg": raw.get("pressure", []),
                "timestamps": raw.get("timestamps"),
                "sample_count": raw.get("read_size"),
                "duration_seconds": raw.get("duration")
            },
            "reference_bp": {
                "systolic": ref_sys,
                "diastolic": ref_dia,
                "map": None  # typically not provided by consumer devices
            },
            "predicted_bp": result,
            "quality_metrics": qa
        }
        
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(bundle, f, indent=2, ensure_ascii=False)
            LOG.info(f"Đã lưu paired data: {args.out}")
        
        print("\n" + "="*50)
        print("KẾT QUẢ PAIRED MEASUREMENT")
        print("="*50)
        print(f"  Reference      : SYS={ref_sys} DIA={ref_dia} mmHg")
        if result:
            pred_sys = result.get('systolic')
            pred_dia = result.get('diastolic')
            err_sys = abs(pred_sys - ref_sys) if pred_sys else None
            err_dia = abs(pred_dia - ref_dia) if pred_dia else None
            print(f"  Predicted      : SYS={pred_sys} DIA={pred_dia} mmHg")
            if err_sys and err_dia:
                print(f"  Error (abs)    : SYS={err_sys} DIA={err_dia} mmHg")
        print(f"  N điểm         : {raw.get('read_size')}")
        print(f"  File saved     : {args.out or '(not saved)'}")
        print()
        
    finally:
        safe_cleanup(sensor)

# ========================= 8) SAFETY CHECK =========================

def cmd_safety_check(args, cfg_full):
    """
    Kiểm tra an toàn trước khi đo:
    - GPIO init OK
    - Đọc offset hiện tại → cảnh báo nếu lệch quá xa
    - Test bơm/van ngắn (0.5s mỗi cái)
    - Kiểm tra relief valve (nhắc người dùng)
    """
    sensor = sensor_boot(cfg_full)
    try:
        print("\n" + "="*50)
        print("  SAFETY PRE-FLIGHT CHECK")
        print("="*50)
        
        # 1. GPIO init
        print("\n[1/5] GPIO Initialization...")
        if sensor._gpio_initialized:
            print("  ✅ GPIO initialized OK")
        else:
            print("  ❌ GPIO NOT initialized")
            return
        
        # 2. Đọc offset hiện tại
        print("\n[2/5] Current Offset Check...")
        valve_open(sensor)
        time.sleep(1.0)
        samples = []
        for _ in range(20):
            v = sensor._read_adc_value(timeout=0.2)
            if v is not None:
                samples.append(int(v))
            time.sleep(0.05)
        
        if samples:
            current_median = int(statistics.median(samples))
            config_offset = sensor._offset_counts
            diff = abs(current_median - config_offset)
            print(f"  Current median : {current_median} counts")
            print(f"  Config offset  : {config_offset} counts")
            print(f"  Difference     : {diff} counts")
            
            # Convert to mmHg để đánh giá
            pressure_est = diff * abs(sensor._slope)
            if pressure_est > 15.0:
                print(f"  ⚠ WARNING: Offset drift ~{pressure_est:.1f} mmHg!")
                print(f"     → Chạy 'offset-electric' để hiệu chỉnh lại")
            else:
                print(f"  ✅ Offset OK (drift ~{pressure_est:.1f} mmHg)")
        else:
            print("  ❌ Không đọc được ADC")
        
        # 3. Test van
        print("\n[3/5] Valve Test (open/close cycle)...")
        valve_close(sensor)
        time.sleep(0.5)
        valve_open(sensor)
        time.sleep(0.5)
        valve_close(sensor)
        print("  ✅ Valve test complete (check manually for clicking sound)")
        
        # 4. Test bơm ngắn
        print("\n[4/5] Pump Short Test (0.5s)...")
        print("  ⚠ Đảm bảo van đóng, cuff an toàn...")
        valve_close(sensor)
        time.sleep(0.3)
        sensor._pump_on()
        time.sleep(0.5)
        sensor._pump_off()
        print("  ✅ Pump test complete (listen for motor sound)")
        
        # 5. Relief valve reminder
        print("\n[5/5] Relief Valve Check...")
        print("  ⚠ NHẮC NHỞ: Kiểm tra van relief (250-300 mmHg) đã lắp chưa?")
        resp = input("  → Van relief OK? (y/n): ").strip().lower()
        if resp == 'y':
            print("  ✅ Relief valve confirmed")
        else:
            print("  ⚠ Cảnh báo: KHÔNG chạy measurement khi chưa có relief valve!")
        
        # Final
        valve_open(sensor)
        time.sleep(1.0)
        print("\n" + "="*50)
        print("SAFETY CHECK COMPLETE")
        print("="*50)
        
    finally:
        safe_cleanup(sensor)

# ========================= 9) BATCH CALIBRATION SUITE =========================

def cmd_batch_calib(args, cfg_full):
    """
    Chạy tự động chuỗi calibration:
    1. offset-electric (400 samples)
    2. noise (30s)
    3. sps (5s)
    4. slope (3 điểm: 0, 100, 150 mmHg) — cần điều khiển thủ công
    
    Lưu tất cả output vào thư mục data/calibration_YYYYMMDD_HHMMSS/
    """
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "data" / f"calibration_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    print("\n" + "="*60)
    print("  BATCH CALIBRATION SUITE")
    print("="*60)
    print(f"\nOutput directory: {out_dir}")
    print("\nChuỗi sẽ chạy:")
    print("  1. offset-electric (400 samples)")
    print("  2. noise (30s)")
    print("  3. sps (5s)")
    print("  4. slope (3 điểm: 0, 100, 150 mmHg) — cần thao tác thủ công")
    print()
    input("→ Nhấn ENTER để bắt đầu...")
    
    # 1. Offset
    print("\n" + "-"*60)
    print("[1/4] OFFSET-ELECTRIC")
    print("-"*60)
    args_off = argparse.Namespace(
        config=args.config,
        samples=400,
        out=str(out_dir / "offset_electric.json"),
        mode="electric"
    )
    cmd_offset(args_off, cfg_full)
    
    # 2. Noise
    print("\n" + "-"*60)
    print("[2/4] NOISE")
    print("-"*60)
    args_noise = argparse.Namespace(
        config=args.config,
        dur=30.0,
        out=str(out_dir / "noise_30s.json")
    )
    cmd_noise(args_noise, cfg_full)
    
    # 3. SPS
    print("\n" + "-"*60)
    print("[3/4] SPS")
    print("-"*60)
    args_sps = argparse.Namespace(
        config=args.config,
        dur=5.0,
        out=str(out_dir / "sps.json")
    )
    cmd_sps(args_sps, cfg_full)
    
    # 4. Slope
    print("\n" + "-"*60)
    print("[4/4] SLOPE (3 điểm: 0, 100, 150 mmHg)")
    print("-"*60)
    print("⚠ Bước này cần thao tác thủ công để đặt áp suất chuẩn.")
    resp = input("→ Tiếp tục? (y/n): ").strip().lower()
    if resp == 'y':
        args_slope = argparse.Namespace(
            config=args.config,
            points=["0", "100", "150"],
            samples=200,
            out=str(out_dir / "slope_fit.json")
        )
        cmd_slope(args_slope, cfg_full)
    else:
        print("  Bỏ qua slope calibration.")
    
    # Summary
    print("\n" + "="*60)
    print("BATCH CALIBRATION COMPLETE")
    print("="*60)
    print(f"All files saved to: {out_dir}")
    print("\nTiếp theo:")
    print(f"  python tests/bp_calib_tool.py commit --from {out_dir}/offset_electric.json --keys offset")
    print(f"  python tests/bp_calib_tool.py commit --from {out_dir}/slope_fit.json --keys slope")
    print(f"  python tests/bp_calib_tool.py commit --from {out_dir}/sps.json --keys sps")
    print()

# ========================= 10) VISUALIZE ENVELOPE =========================

def cmd_visualize(args, cfg_full):
    """
    Vẽ đồ thị envelope, mark MAP/SYS/DIA từ một file JSON oscillometric đã thu.
    Yêu cầu matplotlib.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("❌ Matplotlib không có — cài đặt: pip install matplotlib")
        return
    
    p = Path(args.json).resolve()
    if not p.exists():
        raise SystemExit(f"Không tìm thấy file: {p}")
    
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    raw = data.get("raw_oscillometric_data", {})
    pressures = raw.get("pressure_mmhg") or raw.get("pressure") or []
    if not pressures:
        print("❌ Không tìm thấy dữ liệu pressure trong JSON")
        return
    
    # Re-process để tính envelope
    sensor = BloodPressureSensor(merged_bp_cfg(cfg_full))
    norm = {
        "pressure": pressures,
        "raw": raw.get("adc_counts") or raw.get("raw") or [],
        "read_size": len(pressures),
        "duration": raw.get("duration_seconds")
    }
    
    # Detrend & envelope
    filtered = sensor._filter_pressure_signal(pressures)
    envelope = sensor._detect_oscillations(filtered)
    
    # Tìm MAP
    oscillation_data = [{"pressure": p, "amplitude": a} for p, a in zip(pressures, envelope)]
    map_point = sensor._find_maximum_oscillation(oscillation_data)
    
    # Tính SYS/DIA
    sys_val, dia_val = sensor._apply_oscillometric_ratios(map_point, oscillation_data) if map_point else (None, None)
    
    # Plot
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    
    # Subplot 1: Pressure
    axes[0].plot(pressures, 'b-', label='Cuff Pressure', linewidth=1.5)
    axes[0].axhline(map_point['pressure'], color='g', linestyle='--', label=f"MAP={map_point['pressure']:.0f}")
    if sys_val:
        axes[0].axhline(sys_val, color='r', linestyle='--', label=f"SYS={sys_val:.0f}")
    if dia_val:
        axes[0].axhline(dia_val, color='orange', linestyle='--', label=f"DIA={dia_val:.0f}")
    axes[0].set_ylabel('Pressure (mmHg)')
    axes[0].legend(loc='upper right')
    axes[0].grid(True, alpha=0.3)
    axes[0].set_title('Blood Pressure Oscillometric Analysis')
    
    # Subplot 2: Envelope
    axes[1].plot(envelope, 'g-', label='Oscillation Envelope', linewidth=1.5)
    map_idx = oscillation_data.index(map_point) if map_point in oscillation_data else -1
    if map_idx >= 0:
        axes[1].axvline(map_idx, color='g', linestyle='--', alpha=0.5, label='MAP position')
    axes[1].set_xlabel('Sample Index')
    axes[1].set_ylabel('Amplitude')
    axes[1].legend(loc='upper right')
    axes[1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if args.out:
        plt.savefig(args.out, dpi=150)
        print(f"✅ Đã lưu plot: {args.out}")
    else:
        plt.show()

# ========================= 11) INTERACTIVE MENU =========================

def cmd_interactive_menu(cfg_full):
    """
    Menu tương tác chính — cho phép chọn các lệnh mà không cần gõ CLI dài.
    """
    while True:
        print("\n" + "="*60)
        print("  BP CALIBRATION TOOL — INTERACTIVE MENU")
        print("="*60)
        print("\n📋 CALIBRATION & DATA COLLECTION")
        print("  1. offset-electric    : Offset 0 mmHg (không đeo cuff)")
        print("  2. offset-cuff        : Offset 0 mmHg (có đeo cuff)")
        print("  3. noise              : Đo nhiễu nền & PSD 50/60 Hz")
        print("  4. sps                : Ước lượng tần số lấy mẫu (Hz)")
        print("  5. slope              : Fit slope mmHg/count (3+ điểm)")
        print("  6. capture-deflate    : Thu một pha DEFLATE đầy đủ")
        print("  7. capture-paired     : Thu oscillometric + reference SYS/DIA")
        print("\n🔧 AUTOMATION & ANALYSIS")
        print("  8. batch-calib-suite  : Chạy tự động offset→noise→sps→slope")
        print("  9. safety-check       : Kiểm tra GPIO/bơm/van/offset")
        print(" 10. visualize-envelope : Vẽ đồ thị envelope & BP từ JSON")
        print(" 11. analyze-replay     : Phân tích lại file JSON đã thu")
        print("\n💾 CONFIGURATION")
        print(" 12. commit             : Cập nhật app_config.yaml từ JSON")
        print("\n 0. Exit")
        print("="*60)
        
        choice = input("\n→ Chọn (0-12): ").strip()
        
        if choice == '0':
            print("Thoát.")
            break
        elif choice == '1':
            out = input("  Output file (Enter=không lưu): ").strip() or None
            args = argparse.Namespace(config=str(ROOT/"config"/"app_config.yaml"),
                                     samples=400, out=out, mode="electric")
            cmd_offset(args, cfg_full)
        elif choice == '2':
            out = input("  Output file: ").strip() or None
            args = argparse.Namespace(config=str(ROOT/"config"/"app_config.yaml"),
                                     samples=400, out=out, mode="cuff")
            cmd_offset(args, cfg_full)
        elif choice == '3':
            dur = input("  Duration (s) [30]: ").strip() or "30"
            out = input("  Output file: ").strip() or None
            args = argparse.Namespace(config=str(ROOT/"config"/"app_config.yaml"),
                                     dur=float(dur), out=out)
            cmd_noise(args, cfg_full)
        elif choice == '4':
            dur = input("  Duration (s) [5]: ").strip() or "5"
            out = input("  Output file: ").strip() or None
            args = argparse.Namespace(config=str(ROOT/"config"/"app_config.yaml"),
                                     dur=float(dur), out=out)
            cmd_sps(args, cfg_full)
        elif choice == '5':
            pts = input("  Điểm mmHg (space-separated) [0 100 150]: ").strip() or "0 100 150"
            samples = input("  Samples/point [200]: ").strip() or "200"
            out = input("  Output file: ").strip() or None
            args = argparse.Namespace(config=str(ROOT/"config"/"app_config.yaml"),
                                     points=pts.split(), samples=int(samples), out=out)
            cmd_slope(args, cfg_full)
        elif choice == '6':
            out = input("  Output file: ").strip() or None
            args = argparse.Namespace(config=str(ROOT/"config"/"app_config.yaml"), out=out)
            cmd_capture_deflate(args, cfg_full)
        elif choice == '7':
            out = input("  Output file: ").strip() or None
            args = argparse.Namespace(config=str(ROOT/"config"/"app_config.yaml"), out=out)
            cmd_capture_paired(args, cfg_full)
        elif choice == '8':
            args = argparse.Namespace(config=str(ROOT/"config"/"app_config.yaml"))
            cmd_batch_calib(args, cfg_full)
        elif choice == '9':
            args = argparse.Namespace(config=str(ROOT/"config"/"app_config.yaml"))
            cmd_safety_check(args, cfg_full)
        elif choice == '10':
            json_file = input("  JSON file: ").strip()
            out = input("  Output PNG (Enter=show): ").strip() or None
            args = argparse.Namespace(config=str(ROOT/"config"/"app_config.yaml"),
                                     json=json_file, out=out)
            cmd_visualize(args, cfg_full)
        elif choice == '11':
            json_file = input("  JSON file: ").strip()
            compute = input("  Compute BP? (y/n) [n]: ").strip().lower() == 'y'
            args = argparse.Namespace(config=str(ROOT/"config"/"app_config.yaml"),
                                     json=json_file, compute_bp=compute)
            cmd_analyze_replay(args, cfg_full)
        elif choice == '12':
            from_file = input("  From JSON: ").strip()
            keys_str = input("  Keys (space-sep) [offset slope sps]: ").strip() or "offset slope sps"
            args = argparse.Namespace(config=str(ROOT/"config"/"app_config.yaml"),
                                     from_json=from_file, keys=keys_str.split())
            cmd_commit(args, cfg_full)
        else:
            print("❌ Lựa chọn không hợp lệ.")
        
        input("\n→ Nhấn ENTER để tiếp tục...")

# ========================= 12) COMMIT app_config.yaml =========================

def deep_set(d: Dict[str, Any], path: List[str], value: Any):
    cur = d
    for k in path[:-1]:
        if k not in cur or not isinstance(cur[k], dict):
            cur[k] = {}
        cur = cur[k]
    cur[path[-1]] = value

def cmd_commit(args, cfg_full):
    """
    Cập nhật app_config.yaml từ 1 file JSON kết quả tool (vd slope_fit.json).
    --keys quy định sẽ ghi gì: offset, slope, sps  (chọn bất kỳ)
    """
    src = Path(args.from_json).resolve()
    if not src.exists():
        raise SystemExit(f"Không tìm thấy file: {src}")
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)

    new_cfg = dict(cfg_full)  # shallow copy an toàn

    keys = set(args.keys or [])
    if "offset" in keys:
        # Ưu tiên trường offset_counts_recommend (offset-electric)
        off = data.get("offset_counts_recommend")
        if off is None:
            # hoặc trong fit.slope (offset_counts từ slope)
            fit = data.get("fit", {})
            off = fit.get("offset_counts")
        if off is not None:
            deep_set(new_cfg, ["sensors", "hx710b", "calibration", "offset_counts"], int(round(float(off))))
            LOG.info(f"Set calibration.offset_counts = {off}")

    if "slope" in keys:
        fit = data.get("fit", {})
        slope = fit.get("slope_mmhg_per_count")
        if slope is not None:
            deep_set(new_cfg, ["sensors", "hx710b", "calibration", "slope_mmhg_per_count"], float(slope))
            LOG.info(f"Set calibration.slope_mmhg_per_count = {slope}")

    if "sps" in keys:
        # từ noise/sps output
        fs = data.get("fs_est_hz")
        if fs is None:
            fs = data.get("sample_rate_hz") or data.get("quality_metrics", {}).get("sample_rate_hz")
        if fs is not None:
            deep_set(new_cfg, ["sensors", "hx710b", "sps_hint"], float(fs))
            LOG.info(f"Set hx710b.sps_hint = {fs}")

    # Ghi lại file
    dst = Path(args.config).resolve()
    with open(dst, "w", encoding="utf-8") as f:
        yaml.safe_dump(new_cfg, f, sort_keys=False, allow_unicode=True)
    print(f"✅ Đã cập nhật {dst}")

# ========================= MAIN & ARGPARSE =========================

def main():
    ap = argparse.ArgumentParser(description="BP Calibration/Optimization Tool (HX710B)")
    ap.add_argument("--config", default=str(ROOT / "config" / "app_config.yaml"),
                    help="Đường dẫn app_config.yaml (mặc định ./config/app_config.yaml)")

    sub = ap.add_subparsers(dest="cmd", required=False)  # Make required=False for interactive mode

    # Interactive menu (new)
    ap_menu = sub.add_parser("menu", help="Chế độ menu tương tác")
    ap_menu.set_defaults(func=lambda args, cfg: cmd_interactive_menu(cfg))

    # offset-electric / offset-cuff
    ap_off = sub.add_parser("offset-electric", help="Offset 0 mmHg khi KHÔNG đeo cuff (van mở)")
    ap_off.add_argument("--samples", type=int, default=400, help="Số mẫu (>=200 khuyến nghị)")
    ap_off.add_argument("--out", type=str, help="Lưu JSON kết quả")
    ap_off.set_defaults(func=lambda args, cfg: cmd_offset(argparse.Namespace(**vars(args), mode="electric"), cfg))

    ap_offc = sub.add_parser("offset-cuff", help="Offset 0 mmHg khi CÓ đeo cuff (van mở)")
    ap_offc.add_argument("--samples", type=int, default=400)
    ap_offc.add_argument("--out", type=str)
    ap_offc.set_defaults(func=lambda args, cfg: cmd_offset(argparse.Namespace(**vars(args), mode="cuff"), cfg))

    # noise
    ap_noise = sub.add_parser("noise", help="Đo nhiễu nền & PSD 50/60 Hz tại 0 mmHg (van mở)")
    ap_noise.add_argument("--dur", type=float, default=30.0, help="Thời gian đo (s)")
    ap_noise.add_argument("--out", type=str)
    ap_noise.set_defaults(func=cmd_noise)

    # sps
    ap_sps = sub.add_parser("sps", help="Ước lượng tần số lấy mẫu thực (Hz)")
    ap_sps.add_argument("--dur", type=float, default=5.0)
    ap_sps.add_argument("--out", type=str)
    ap_sps.set_defaults(func=cmd_sps)

    # slope
    ap_slope = sub.add_parser("slope", help="Fit slope mmHg/count từ các điểm áp chuẩn (nhập via --points)")
    ap_slope.add_argument("--points", nargs="+", required=True, help="Danh sách điểm mmHg (ví dụ: 0 100 150)")
    ap_slope.add_argument("--samples", type=int, default=200, help="Mẫu/điểm (>=80)")
    ap_slope.add_argument("--out", type=str)
    ap_slope.set_defaults(func=cmd_slope)

    # capture-deflate
    ap_def = sub.add_parser("capture-deflate", help="Chạy một chu trình đo để ghi riêng pha DEFLATE")
    ap_def.add_argument("--out", type=str)
    ap_def.set_defaults(func=cmd_capture_deflate)

    # capture-paired (NEW)
    ap_paired = sub.add_parser("capture-paired", help="Thu oscillometric + nhập reference SYS/DIA từ máy tham chiếu")
    ap_paired.add_argument("--out", type=str, help="Lưu paired data JSON")
    ap_paired.set_defaults(func=cmd_capture_paired)

    # safety-check (NEW)
    ap_safety = sub.add_parser("safety-check", help="Kiểm tra GPIO/bơm/van/offset trước khi đo")
    ap_safety.set_defaults(func=cmd_safety_check)

    # batch-calib-suite (NEW)
    ap_batch = sub.add_parser("batch-calib-suite", help="Chạy tự động offset→noise→sps→slope")
    ap_batch.set_defaults(func=cmd_batch_calib)

    # visualize-envelope (NEW)
    ap_viz = sub.add_parser("visualize-envelope", help="Vẽ đồ thị envelope & BP từ JSON oscillometric")
    ap_viz.add_argument("--json", required=True, help="File JSON dữ liệu oscillometric")
    ap_viz.add_argument("--out", type=str, help="Lưu PNG (nếu không có sẽ hiển thị)")
    ap_viz.set_defaults(func=cmd_visualize)

    # analyze-replay
    ap_rep = sub.add_parser("analyze-replay", help="Phân tích lại file JSON đã thu (dP/dt, và có thể tính BP)")
    ap_rep.add_argument("--json", required=True, help="File JSON dữ liệu đã thu")
    ap_rep.add_argument("--compute-bp", action="store_true", help="Chạy process_data() để tính SYS/DIA/MAP")
    ap_rep.set_defaults(func=cmd_analyze_replay)

    # commit
    ap_commit = sub.add_parser("commit", help="Cập nhật app_config.yaml từ file JSON kết quả")
    ap_commit.add_argument("--from", dest="from_json", required=True, help="File JSON nguồn (offset/slope/sps)")
    ap_commit.add_argument("--keys", nargs="+", choices=["offset","slope","sps"], required=True,
                           help="Các khóa sẽ cập nhật vào config")
    ap_commit.add_argument("--config", default=str(ROOT / "config" / "app_config.yaml"))
    ap_commit.set_defaults(func=cmd_commit)

    args = ap.parse_args()
    
    # If no command provided, launch interactive menu
    if not args.cmd:
        cfg_full = load_config(Path(args.config))
        cmd_interactive_menu(cfg_full)
        return 0
    
    cfg_full = load_config(Path(args.config))

    try:
        return args.func(args, cfg_full)
    except KeyboardInterrupt:
        print("\nHủy bởi người dùng.")
        return 2
    except Exception as e:
        LOG.exception("Lỗi:")
        return 1

if __name__ == "__main__":
    sys.exit(main())
