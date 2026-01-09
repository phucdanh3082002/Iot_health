#!/usr/bin/env python3
"""
Simple Slope Calibration Tool
==============================

Hiệu chuẩn slope bằng cách SO SÁNH trực tiếp:
- Bơm đến áp lực CỐ ĐỊNH (theo counts, không dựa vào slope sai)
- Đo bằng máy thương mại
- Tính slope mới

Author: IoT Health Monitor Team  
Date: 2026-01-10
"""

import logging
import time
import sys
import numpy as np
import yaml
from pathlib import Path
from scipy import stats

sys.path.append('/home/pi/Desktop/IoT_health')

from src.sensors.hx710b_driver import HX710BDriver, HX710Mode

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("SimpleSlope")


def simple_slope_calibration(num_measurements: int = 5):
    """
    Hiệu chuẩn slope đơn giản
    
    Method:
    -------
    1. Bơm đến TARGET_COUNTS cố định (không phụ thuộc slope)
    2. User đo bằng máy thương mại, nhập áp lực thực tế
    3. Lặp lại num_measurements lần
    4. Linear regression: pressure vs (counts - offset) → slope
    
    Args:
        num_measurements: Số lần đo (khuyến nghị 5-10)
    """
    
    logger.info("\n" + "="*70)
    logger.info("SIMPLE SLOPE CALIBRATION")
    logger.info("="*70)
    logger.info("\n📋 PHƯƠNG PHÁP:")
    logger.info("   1. Script bơm căng cuff đến một mức CỐ ĐỊNH")
    logger.info("   2. Bạn đo bằng máy thương mại NGAY LẬP TỨC")
    logger.info("   3. Nhập áp lực từ máy thương mại")
    logger.info("   4. Lặp lại 5-10 lần")
    logger.info("   5. Tính slope chính xác từ linear regression")
    logger.info("\n⚠️  LƯU Ý:")
    logger.info("   - Chuẩn bị máy đo thương mại sẵn sàng")
    logger.info("   - Đo NGAY khi script dừng bơm (chờ 2-3 giây)")
    logger.info("   - Nghỉ 2-3 phút giữa các lần đo")
    logger.info("   - Ngồi yên, không cử động khi đo")
    
    # Load config
    config_path = Path('/home/pi/Desktop/IoT_health/config/app_config.yaml')
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    hx710b_config = config['sensors']['blood_pressure']['hx710b']
    offset_counts = hx710b_config['calibration']['offset_counts']
    
    logger.info(f"\n📊 Current config:")
    logger.info(f"   offset_counts: {offset_counts}")
    logger.info(f"   slope (old): {hx710b_config['calibration']['slope_mmhg_per_count']:.2e}")
    
    if GPIO is None:
        logger.error("\n❌ GPIO not available")
        return
    
    # Setup GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    
    PUMP_GPIO = 26
    VALVE_GPIO = 20
    
    GPIO.setup(PUMP_GPIO, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(VALVE_GPIO, GPIO.OUT, initial=GPIO.LOW)
    
    # Create driver
    driver = HX710BDriver(
        gpio_dout=hx710b_config['gpio_dout'],
        gpio_sck=hx710b_config['gpio_sck'],
        mode=HX710Mode.DIFFERENTIAL_10SPS,
        timeout_ms=500
    )
    
    if not driver.initialize():
        logger.error("\n❌ Failed to initialize HX710B driver")
        GPIO.cleanup()
        return
    
    # Define target counts (bơm đến ~180 mmHg thực tế)
    # Ước tính: cần ~(180 / 2.7e-5) ≈ 6.67M counts offset-corrected
    # Với offset = 992445, target_counts ≈ 992445 + 6.67M = ~7.6M
    # Để an toàn, dùng 5M counts offset-corrected (tương ứng ~135-180 mmHg tùy slope thực)
    TARGET_COUNTS_DELTA = 5_500_000  # offset-corrected counts
    TARGET_COUNTS_ABSOLUTE = offset_counts + TARGET_COUNTS_DELTA
    
    logger.info(f"\n🎯 Target inflate:")
    logger.info(f"   Absolute counts: {TARGET_COUNTS_ABSOLUTE:,}")
    logger.info(f"   Offset-corrected: {TARGET_COUNTS_DELTA:,}")
    logger.info(f"   Expected pressure: 150-190 mmHg (depends on actual slope)")
    
    input("\n   Press ENTER khi sẵn sàng...")
    
    # Data storage
    pressures_commercial = []
    counts_measured = []
    
    try:
        for i in range(num_measurements):
            logger.info(f"\n{'='*70}")
            logger.info(f"MEASUREMENT {i+1}/{num_measurements}")
            logger.info('='*70)
            
            # Step 1: Inflate to target counts
            logger.info("\n⏫ Step 1: Inflating cuff...")
            logger.info("   (Closing valve, starting pump)")
            
            GPIO.output(VALVE_GPIO, GPIO.HIGH)  # ĐÓNG van (NO: HIGH = close)
            GPIO.output(PUMP_GPIO, GPIO.HIGH)   # Bật bơm
            
            max_counts = 0
            
            while True:
                raw = driver.read(timeout_ms=500)
                
                if raw is not None:
                    if raw > max_counts:
                        max_counts = raw
                    
                    # Show current pressure estimate (for reference only)
                    current_pressure_est = (raw - offset_counts) * 3.0e-5
                    print(f"   Current: {raw:,} counts (~{current_pressure_est:.0f} mmHg est)", end='\r')
                    
                    # Stop at target
                    if raw >= TARGET_COUNTS_ABSOLUTE:
                        break
                    
                    # Safety limit
                    if raw >= offset_counts + 7_000_000:
                        logger.warning("\n   ⚠️  Safety limit reached!")
                        break
                
                time.sleep(0.05)
            
            print()  # newline
            GPIO.output(PUMP_GPIO, GPIO.LOW)  # Tắt bơm
            
            logger.info(f"✅ Inflate complete: {max_counts:,} counts")
            logger.info(f"   Offset-corrected: {max_counts - offset_counts:,} counts")
            
            # Step 2: User measures with commercial device
            logger.info("\n📱 Step 2: MEASURE WITH COMMERCIAL DEVICE NOW!")
            logger.info("   ⏱️  Đo NGAY trong 5-10 giây!")
            logger.info("   (Cuff đang giữ áp lực)")
            
            time.sleep(3)  # Wait 3 seconds for stabilization
            
            pressure_str = input("\n   Enter pressure from commercial device (mmHg): ").strip()
            
            if not pressure_str:
                logger.warning("   ⚠️  No input, skipping this measurement")
                # Deflate
                GPIO.output(VALVE_GPIO, GPIO.LOW)  # MỞ van
                time.sleep(10)
                GPIO.output(VALVE_GPIO, GPIO.HIGH)  # ĐÓNG lại
                continue
            
            try:
                pressure_measured = float(pressure_str)
            except ValueError:
                logger.error("   ❌ Invalid number, skipping")
                # Deflate
                GPIO.output(VALVE_GPIO, GPIO.LOW)
                time.sleep(10)
                GPIO.output(VALVE_GPIO, GPIO.HIGH)
                continue
            
            # Validate
            if pressure_measured < 100 or pressure_measured > 250:
                logger.warning(f"   ⚠️  Unusual pressure: {pressure_measured} mmHg")
                confirm = input("   Continue anyway? (y/n): ").strip().lower()
                if confirm != 'y':
                    # Deflate
                    GPIO.output(VALVE_GPIO, GPIO.LOW)
                    time.sleep(10)
                    GPIO.output(VALVE_GPIO, GPIO.HIGH)
                    continue
            
            # Store data
            pressures_commercial.append(pressure_measured)
            counts_measured.append(max_counts - offset_counts)  # Store offset-corrected
            
            logger.info(f"\n✅ Data point recorded:")
            logger.info(f"   Counts (offset-corrected): {max_counts - offset_counts:,}")
            logger.info(f"   Pressure (commercial): {pressure_measured:.1f} mmHg")
            logger.info(f"   Implied slope: {pressure_measured / (max_counts - offset_counts):.3e}")
            
            # Step 3: Deflate
            logger.info("\n⏬ Step 3: Deflating...")
            GPIO.output(VALVE_GPIO, GPIO.LOW)  # MỞ van
            time.sleep(15)  # Full deflate
            GPIO.output(VALVE_GPIO, GPIO.HIGH)  # ĐÓNG lại
            
            # Wait before next measurement
            if i < num_measurements - 1:
                logger.info("\n⏱️  Wait 2 minutes before next measurement...")
                logger.info("   (Or press Ctrl+C to finish early)")
                try:
                    time.sleep(5)  # Short wait (user can interrupt)
                except KeyboardInterrupt:
                    logger.info("\n   User skipped wait")
                    break
        
    except KeyboardInterrupt:
        logger.warning("\n\n⚠️  Interrupted by user")
        
    finally:
        # Emergency cleanup
        GPIO.output(PUMP_GPIO, GPIO.LOW)   # Pump OFF
        GPIO.output(VALVE_GPIO, GPIO.LOW)  # MỞ van (xả khẩn cấp)
        time.sleep(10)
        GPIO.output(VALVE_GPIO, GPIO.HIGH) # ĐÓNG lại
        driver.cleanup()
        GPIO.cleanup()
    
    # Calculate slope
    if len(pressures_commercial) < 3:
        logger.error(f"\n❌ Need at least 3 measurements (have {len(pressures_commercial)})")
        return
    
    logger.info("\n" + "="*70)
    logger.info("CALCULATING OPTIMAL SLOPE")
    logger.info("="*70)
    
    # Linear regression: pressure = slope × counts
    slope, intercept, r_value, p_value, std_err = stats.linregress(
        counts_measured, 
        pressures_commercial
    )
    r_squared = r_value ** 2
    
    logger.info(f"\n📊 Regression results:")
    logger.info(f"   Data points: {len(pressures_commercial)}")
    logger.info(f"   slope: {slope:.10e} mmHg/count")
    logger.info(f"   intercept: {intercept:.2f} mmHg (should be ~0)")
    logger.info(f"   R²: {r_squared:.4f} (good if >0.95)")
    logger.info(f"   Std error: {std_err:.3e}")
    
    # Show individual measurements
    logger.info(f"\n📋 Individual measurements:")
    for i, (counts, pressure) in enumerate(zip(counts_measured, pressures_commercial), 1):
        predicted = slope * counts + intercept
        error = pressure - predicted
        logger.info(f"   #{i}: {counts:,} counts → {pressure:.1f} mmHg (pred: {predicted:.1f}, err: {error:+.1f})")
    
    # Validation
    logger.info("\n" + "="*70)
    logger.info("VALIDATION:")
    logger.info("="*70)
    
    if r_squared < 0.90:
        logger.warning("⚠️  Low R² (<0.90) - measurements inconsistent")
        logger.warning("   → Check measurement technique or repeat")
    elif r_squared < 0.95:
        logger.info("⚙️  Acceptable R² (0.90-0.95)")
    else:
        logger.info("✅ Excellent R² (>0.95)")
    
    if abs(intercept) > 10.0:
        logger.warning(f"⚠️  High intercept ({intercept:.1f} mmHg)")
        logger.warning("   → May need to re-check zero offset")
    else:
        logger.info("✅ Intercept OK (<10 mmHg)")
    
    # Compare with old slope
    old_slope = hx710b_config['calibration']['slope_mmhg_per_count']
    change_pct = (slope - old_slope) / old_slope * 100
    
    logger.info(f"\n📊 Comparison:")
    logger.info(f"   Old slope: {old_slope:.10e}")
    logger.info(f"   New slope: {slope:.10e}")
    logger.info(f"   Change: {change_pct:+.1f}%")
    
    # Recommendation
    logger.info("\n" + "="*70)
    logger.info("RECOMMENDATION:")
    logger.info("="*70)
    logger.info(f"\nUpdate config/app_config.yaml:")
    logger.info(f"   slope_mmhg_per_count: {slope:.10e}")
    
    if r_squared >= 0.95 and abs(intercept) < 10:
        logger.info("\n✅ Calibration SUCCESSFUL - safe to use new slope")
    elif r_squared >= 0.90:
        logger.info("\n⚙️  Calibration ACCEPTABLE - can use with caution")
    else:
        logger.info("\n⚠️  Calibration UNCERTAIN - consider repeating")
    
    # Save results
    output_dir = Path('/home/pi/Desktop/IoT_health/tests/calibration_results')
    output_dir.mkdir(exist_ok=True)
    
    results = {
        'calibration_date': time.strftime('%Y-%m-%d %H:%M:%S'),
        'offset_counts': int(offset_counts),
        'old_slope': float(old_slope),
        'new_slope': float(slope),
        'intercept': float(intercept),
        'r_squared': float(r_squared),
        'std_error': float(std_err),
        'num_measurements': len(pressures_commercial),
        'measurements': [
            {'counts': int(c), 'pressure': float(p)} 
            for c, p in zip(counts_measured, pressures_commercial)
        ]
    }
    
    output_file = output_dir / 'slope_calibration_results.yaml'
    with open(output_file, 'w') as f:
        yaml.dump(results, f, default_flow_style=False)
    
    logger.info(f"\n💾 Results saved to: {output_file}")


if __name__ == "__main__":
    try:
        simple_slope_calibration(num_measurements=5)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        if GPIO:
            GPIO.output(26, GPIO.LOW)  # Pump OFF
            GPIO.output(20, GPIO.LOW)  # MỞ van
            time.sleep(10)
            GPIO.cleanup()
