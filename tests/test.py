#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Blood Pressure Sensor Slope Calibration Tool
============================================
So sánh với máy đo huyết áp thương mại để tính slope chính xác

Quy trình:
1. Đeo cuff vào tay
2. Bơm đến 3 mức áp: 100, 150, 190 mmHg (theo IoT)
3. Tại mỗi mức, đo bằng máy thương mại
4. Script tính slope mới từ linear regression
5. Cập nhật vào config

Hardware:
- HX710B + MPS20N0040D
- Pump + Valve (GPIO 26, 16)
- Máy đo BP thương mại (để so sánh)

Usage:
    python tests/calibrate_slope.py
"""

import time
import logging
import sys
import pathlib
import numpy as np
import RPi.GPIO as GPIO
from typing import List, Tuple

# Setup path
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.sensors.hx710b_sensor import HX710BSensor

# ============================================================================
# CONFIGURATION
# ============================================================================
GPIO_PUMP = 26
GPIO_VALVE = 16

# HX710B config
HX710B_CONFIG = {
    'enabled': True,
    'gpio_dout': 6,
    'gpio_sck': 5,
    'mode': '10sps',
    'read_timeout_ms': 1000,
    'calibration': {
        'offset_counts': 1357387,  # Offset hiện tại (đã hiệu chỉnh)
        'slope_mmhg_per_count': 3.5765743256e-05,  # Slope cũ (sẽ tính lại)
        'adc_inverted': False
    }
}

# Calibration points (áp suất mục tiêu theo IoT)
CALIBRATION_POINTS = [100.0, 150.0, 190.0]  # mmHg

TIMEOUT_INFLATE = 30  # seconds

# ============================================================================
# LOGGING
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger("Slope_Calibration")

# ============================================================================
# GPIO CONTROL
# ============================================================================
def setup_gpio():
    """Khởi tạo GPIO cho bơm và van"""
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(GPIO_PUMP, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(GPIO_VALVE, GPIO.OUT, initial=GPIO.LOW)  # NO: LOW = open
    log.info("GPIO initialized: Pump=%d, Valve=%d", GPIO_PUMP, GPIO_VALVE)


def pump_on():
    """Bật bơm"""
    GPIO.output(GPIO_PUMP, GPIO.HIGH)


def pump_off():
    """Tắt bơm"""
    GPIO.output(GPIO_PUMP, GPIO.LOW)


def valve_open():
    """Mở van xả (NO: LOW = open)"""
    GPIO.output(GPIO_VALVE, GPIO.LOW)


def valve_close():
    """Đóng van (NO: HIGH = close)"""
    GPIO.output(GPIO_VALVE, GPIO.HIGH)


def cleanup_gpio():
    """Cleanup GPIO"""
    pump_off()
    valve_open()
    GPIO.cleanup([GPIO_PUMP, GPIO_VALVE])
    log.info("GPIO cleaned up")


# ============================================================================
# PRESSURE READING
# ============================================================================
def get_pressure_from_sensor(sensor: HX710BSensor) -> float:
    """
    Đọc áp suất từ HX710BSensor
    
    Args:
        sensor: HX710BSensor instance
        
    Returns:
        Áp suất (mmHg), None nếu lỗi
    """
    try:
        data = sensor.get_latest_data()
        if data and 'pressure_mmhg' in data:
            return data['pressure_mmhg']
    except Exception as e:
        log.error(f"Error reading pressure: {e}")
    return None


def get_counts_from_sensor(sensor: HX710BSensor) -> int:
    """
    Đọc raw counts từ HX710BSensor
    
    Args:
        sensor: HX710BSensor instance
        
    Returns:
        Counts (int), None nếu lỗi
    """
    try:
        data = sensor.get_latest_data()
        if data and 'counts' in data:
            return data['counts']
    except Exception as e:
        log.error(f"Error reading counts: {e}")
    return None


# ============================================================================
# INFLATE TO TARGET
# ============================================================================
def inflate_to_target(sensor: HX710BSensor, target_mmhg: float) -> Tuple[int, float]:
    """
    Bơm đến áp suất mục tiêu
    
    Args:
        sensor: HX710BSensor instance
        target_mmhg: Áp suất mục tiêu (theo IoT readings)
        
    Returns:
        (counts, pressure_iot): Counts và áp suất IoT tại điểm target
        None nếu thất bại
    """
    log.info(f"Inflating to {target_mmhg:.0f} mmHg (IoT reading)...")
    
    # Đóng van, bật bơm
    valve_close()
    time.sleep(0.3)
    pump_on()
    
    t0 = time.time()
    
    try:
        while True:
            pressure = get_pressure_from_sensor(sensor)
            
            if pressure is None:
                time.sleep(0.1)
                continue
            
            print(f"\rInflating: {pressure:6.1f} / {target_mmhg:.1f} mmHg", end="", flush=True)
            
            # Đạt target
            if pressure >= target_mmhg:
                pump_off()
                print(f"\n✓ Target reached: {pressure:.1f} mmHg")
                
                # Đợi ổn định
                time.sleep(1.0)
                
                # Đọc counts và pressure final
                counts = get_counts_from_sensor(sensor)
                pressure_final = get_pressure_from_sensor(sensor)
                
                if counts is not None and pressure_final is not None:
                    log.info(f"Stable at: counts={counts}, pressure_iot={pressure_final:.1f} mmHg")
                    return counts, pressure_final
                else:
                    log.error("Failed to read final values")
                    return None
            
            # Safety checks
            if pressure > 220:
                log.error("Pressure too high! Aborting.")
                pump_off()
                valve_open()
                return None
            
            if (time.time() - t0) > TIMEOUT_INFLATE:
                log.error("Inflate timeout")
                pump_off()
                valve_open()
                return None
            
            time.sleep(0.1)
            
    except Exception as e:
        log.error(f"Inflate error: {e}")
        pump_off()
        valve_open()
        return None


# ============================================================================
# DEFLATE
# ============================================================================
def deflate_complete(sensor: HX710BSensor):
    """Xả hoàn toàn cuff"""
    log.info("Deflating cuff completely...")
    
    pump_off()
    valve_open()
    
    print("Deflating", end="", flush=True)
    for _ in range(10):
        time.sleep(0.5)
        print(".", end="", flush=True)
    print(" Done!\n")
    
    time.sleep(1.0)


# ============================================================================
# MAIN CALIBRATION
# ============================================================================
def calibrate_slope():
    """
    Quy trình hiệu chỉnh slope
    
    Workflow:
    1. Khởi tạo sensor
    2. Đo tại 3 điểm: 100, 150, 190 mmHg (IoT)
    3. Nhập giá trị máy thương mại
    4. Tính slope mới từ linear regression
    5. Hiển thị kết quả
    """
    print("\n" + "="*60)
    print("BLOOD PRESSURE SENSOR SLOPE CALIBRATION")
    print("="*60)
    print("\nQuy trình:")
    print("1. Đeo cuff vào tay (hoặc chuẩn bị ống áp chuẩn)")
    print("2. Chuẩn bị máy đo huyết áp thương mại")
    print("3. Script sẽ bơm đến 3 mức: 100, 150, 190 mmHg")
    print("4. Tại mỗi mức, đo bằng máy thương mại và nhập giá trị")
    print("5. Script tính slope mới")
    print("\nLưu ý:")
    print("- Offset phải đã được hiệu chỉnh trước (tests/calibrate_offset.py)")
    print("- Cuff phải được bơm đủ chặt (giống máy thương mại)")
    print("="*60 + "\n")
    
    input("Press ENTER khi sẵn sàng...")
    
    # Setup
    setup_gpio()
    
    # Khởi tạo sensor
    log.info("Initializing HX710BSensor...")
    sensor = HX710BSensor("BP_ADC", HX710B_CONFIG)
    
    if not sensor.start():
        log.error("Failed to start HX710BSensor!")
        cleanup_gpio()
        return
    
    log.info("Sensor started")
    time.sleep(1.0)
    
    # Xả cuff trước
    deflate_complete(sensor)
    
    # Data collection
    calibration_data = []  # List of (counts, pressure_iot, pressure_commercial)
    
    try:
        for i, target_mmhg in enumerate(CALIBRATION_POINTS, 1):
            print(f"\n{'='*60}")
            print(f"CALIBRATION POINT {i}/{len(CALIBRATION_POINTS)}: {target_mmhg:.0f} mmHg")
            print('='*60)
            
            # Inflate to target
            result = inflate_to_target(sensor, target_mmhg)
            
            if result is None:
                log.error(f"Failed to inflate to {target_mmhg} mmHg. Aborting.")
                break
            
            counts, pressure_iot = result
            
            # Nhập giá trị máy thương mại
            print(f"\n📱 IoT system reads: {pressure_iot:.1f} mmHg")
            print("📟 Đo bằng máy thương mại:")
            
            while True:
                try:
                    pressure_commercial = float(input("   Nhập giá trị (mmHg): ").strip())
                    
                    if pressure_commercial <= 0 or pressure_commercial > 300:
                        print("   ⚠️  Giá trị không hợp lệ. Nhập lại.")
                        continue
                    
                    # Confirm
                    print(f"\n   IoT:        {pressure_iot:.1f} mmHg")
                    print(f"   Commercial: {pressure_commercial:.1f} mmHg")
                    print(f"   Counts:     {counts}")
                    
                    confirm = input("\n   Xác nhận (y/n)? ").strip().lower()
                    if confirm == 'y':
                        calibration_data.append((counts, pressure_iot, pressure_commercial))
                        log.info(f"Point {i}: counts={counts}, IoT={pressure_iot:.1f}, Commercial={pressure_commercial:.1f}")
                        break
                    else:
                        print("   Nhập lại giá trị...")
                        
                except ValueError:
                    print("   ⚠️  Lỗi nhập liệu. Nhập lại.")
                except KeyboardInterrupt:
                    raise
            
            # Xả sau mỗi điểm (trừ điểm cuối)
            if i < len(CALIBRATION_POINTS):
                deflate_complete(sensor)
        
        # ========== CALCULATE NEW SLOPE ==========
        if len(calibration_data) < 2:
            log.error("Không đủ dữ liệu để tính slope (cần ít nhất 2 điểm)")
            return
        
        print("\n" + "="*60)
        print("CALCULATING NEW SLOPE")
        print("="*60)
        
        # Extract data
        counts_list = [d[0] for d in calibration_data]
        pressure_commercial_list = [d[2] for d in calibration_data]
        
        # Linear regression: pressure_commercial = slope_new × (counts - offset)
        offset = HX710B_CONFIG['calibration']['offset_counts']
        counts_offset = [c - offset for c in counts_list]
        
        # Least squares fit
        slope_new, residuals, rank, s = np.linalg.lstsq(
            np.array(counts_offset).reshape(-1, 1),
            np.array(pressure_commercial_list),
            rcond=None
        )
        slope_new = float(slope_new[0])
        
        # Calculate R² (goodness of fit)
        predicted = [slope_new * (c - offset) for c in counts_list]
        ss_res = sum((p - pc)**2 for p, pc in zip(predicted, pressure_commercial_list))
        ss_tot = sum((pc - np.mean(pressure_commercial_list))**2 for pc in pressure_commercial_list)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        # Display results
        print("\nCalibration Data:")
        print(f"{'Point':<8} {'Counts':<12} {'IoT (mmHg)':<12} {'Commercial (mmHg)':<18} {'Predicted (mmHg)':<18} {'Error (mmHg)':<12}")
        print("-" * 90)
        
        for i, (counts, p_iot, p_comm) in enumerate(calibration_data, 1):
            p_pred = slope_new * (counts - offset)
            error = p_pred - p_comm
            print(f"{i:<8} {counts:<12} {p_iot:<12.1f} {p_comm:<18.1f} {p_pred:<18.1f} {error:+12.1f}")
        
        print("\n" + "="*60)
        print("CALIBRATION RESULTS")
        print("="*60)
        print(f"Old slope: {HX710B_CONFIG['calibration']['slope_mmhg_per_count']:.15e}")
        print(f"New slope: {slope_new:.15e}")
        print(f"Change:    {(slope_new / HX710B_CONFIG['calibration']['slope_mmhg_per_count'] - 1) * 100:+.2f}%")
        print(f"R² (fit):  {r_squared:.4f}")
        print("="*60)
        
        print("\nCập nhật vào config/app_config.yaml:")
        print("```yaml")
        print("sensors:")
        print("  hx710b:")
        print("    calibration:")
        print(f"      offset_counts: {offset}")
        print(f"      slope_mmhg_per_count: {slope_new:.15e}")
        print("```")
        print("\nHoặc trong tests/test_full_bp_measurement.py:")
        print(f"'slope_mmhg_per_count': {slope_new:.15e},")
        print("="*60 + "\n")
        
        # Save to file (optional)
        save = input("Lưu kết quả vào file calibration_result.txt (y/n)? ").strip().lower()
        if save == 'y':
            with open(ROOT / 'calibration_result.txt', 'w') as f:
                f.write("="*60 + "\n")
                f.write("BLOOD PRESSURE SENSOR SLOPE CALIBRATION RESULT\n")
                f.write("="*60 + "\n\n")
                f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(f"Old slope: {HX710B_CONFIG['calibration']['slope_mmhg_per_count']:.15e}\n")
                f.write(f"New slope: {slope_new:.15e}\n")
                f.write(f"Change: {(slope_new / HX710B_CONFIG['calibration']['slope_mmhg_per_count'] - 1) * 100:+.2f}%\n")
                f.write(f"R²: {r_squared:.4f}\n\n")
                f.write("Calibration Points:\n")
                for i, (counts, p_iot, p_comm) in enumerate(calibration_data, 1):
                    f.write(f"  Point {i}: counts={counts}, IoT={p_iot:.1f}, Commercial={p_comm:.1f}\n")
                f.write("\nConfig update:\n")
                f.write(f"  slope_mmhg_per_count: {slope_new:.15e}\n")
            print(f"✓ Saved to {ROOT / 'calibration_result.txt'}")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Calibration cancelled by user")
        
    finally:
        # Cleanup
        print("\nCleaning up...")
        deflate_complete(sensor)
        sensor.stop()
        cleanup_gpio()
        print("✓ Done\n")


# ============================================================================
# ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    try:
        calibrate_slope()
    except Exception as e:
        log.error(f"Calibration error: {e}", exc_info=True)
        print(f"\n❌ Error: {e}\n")