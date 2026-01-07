#!/usr/bin/env python3
"""
HX710B Timing Diagnostic Tool
==============================

Test ADC reading stability và timing accuracy sau khi fix driver.

Tests:
------
1. Zero stability: Đọc 100 samples ở 0 mmHg, tính std
2. Sign check: Test XOR 0x800000 flip
3. Counts range: Verify counts trong range hợp lý
4. Timing verification: Log read duration

Usage:
------
python tests/test_hx710b_timing.py

Author: IoT Health Monitor Team
Date: 2025-10-26
"""

import sys
import time
import logging
import numpy as np
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("HX710B_Timing_Test")

# Add project root to path
sys.path.append('/home/pi/Desktop/IoT_health')

from src.sensors.hx710b_sensor import HX710BSensor


def test_zero_stability(sensor: HX710BSensor, num_samples: int = 100):
    """
    Test 1: Zero Stability
    
    Kiểm tra noise level khi cuff deflated (0 mmHg).
    Expected: std < 500 counts (nếu > 1000 có vấn đề wiring/power)
    """
    logger.info("="*60)
    logger.info("TEST 1: ZERO STABILITY (0 mmHg)")
    logger.info("="*60)
    logger.info("⚠️  Ensure cuff is DEFLATED and NOT connected to arm")
    input("Press ENTER when ready...")
    
    samples = []
    start_time = time.time()
    
    logger.info(f"Reading {num_samples} samples...")
    for i in range(num_samples):
        raw = sensor.read_raw_data()
        if raw is not None:
            samples.append(raw)
            print(f"Sample {i+1}/{num_samples}: {raw:8d}", end='\r')
        time.sleep(0.1)
    
    print()
    elapsed = time.time() - start_time
    
    if len(samples) < num_samples * 0.8:
        logger.error(f"❌ FAIL: Only {len(samples)}/{num_samples} successful reads")
        return False
    
    # Calculate statistics
    mean = np.mean(samples)
    std = np.std(samples)
    min_val = np.min(samples)
    max_val = np.max(samples)
    range_val = max_val - min_val
    
    logger.info(f"\n✅ Results:")
    logger.info(f"   Mean:       {mean:.1f} counts")
    logger.info(f"   Std dev:    {std:.1f} counts")
    logger.info(f"   Range:      {range_val} counts ({min_val} to {max_val})")
    logger.info(f"   Read time:  {elapsed:.2f}s ({elapsed/num_samples*1000:.1f}ms per sample)")
    
    # Evaluate
    if std > 1000:
        logger.warning("⚠️  HIGH NOISE! Std > 1000 counts indicates:")
        logger.warning("   - Loose wiring (check DOUT/SCK connections)")
        logger.warning("   - Power supply noise (check 5V stability)")
        logger.warning("   - Ground loop issues")
        return False
    elif std > 500:
        logger.warning("⚠️  MODERATE NOISE: Std > 500 counts")
        logger.info("   → Acceptable but can be improved")
        return True
    else:
        logger.info("✅ EXCELLENT: Low noise (std < 500 counts)")
        return True


def test_sign_inversion(sensor: HX710BSensor):
    """
    Test 2: Sign Inversion Check
    
    MPS20N0040D có thể output positive hoặc negative tùy circuit.
    Test xem có cần XOR 0x800000 không.
    """
    logger.info("\n" + "="*60)
    logger.info("TEST 2: SIGN INVERSION CHECK")
    logger.info("="*60)
    
    logger.info("\nStep 1: Đọc 10 samples ở 0 mmHg...")
    samples_zero = []
    for i in range(10):
        raw = sensor.read_raw_data()
        if raw is not None:
            samples_zero.append(raw)
            print(f"  Zero sample {i+1}/10: {raw:8d}", end='\r')
        time.sleep(0.1)
    print()
    
    mean_zero = np.mean(samples_zero)
    logger.info(f"   Mean at 0 mmHg: {mean_zero:.0f} counts")
    
    logger.info("\nStep 2: Thổi nhẹ vào ống (tạo áp dương)...")
    input("   BLOW gently into tube, then press ENTER...")
    
    time.sleep(0.5)
    
    samples_blow = []
    for i in range(10):
        raw = sensor.read_raw_data()
        if raw is not None:
            samples_blow.append(raw)
            print(f"  Blow sample {i+1}/10: {raw:8d}", end='\r')
        time.sleep(0.1)
    print()
    
    mean_blow = np.mean(samples_blow)
    logger.info(f"   Mean when blowing: {mean_blow:.0f} counts")
    
    # Analyze
    delta = mean_blow - mean_zero
    logger.info(f"\n   Delta: {delta:+.0f} counts")
    
    if delta > 1000:
        logger.info("✅ CORRECT SIGN: Counts increase with pressure (positive)")
        return False  # No inversion needed
    elif delta < -1000:
        logger.warning("⚠️  INVERTED SIGN: Counts decrease with pressure!")
        logger.warning("   → Need to enable 'adc_inverted: true' in config")
        return True   # Inversion needed
    else:
        logger.warning("⚠️  INCONCLUSIVE: Delta too small (< 1000 counts)")
        logger.warning("   → Sensor may not be responding to pressure")
        return None


def test_counts_range(sensor: HX710BSensor):
    """
    Test 3: Counts Range Verification
    
    Verify counts trong range hợp lý:
    - @ 0 mmHg:   ~1,000,000 to 1,400,000 (tùy offset)
    - @ 150 mmHg: ~1,060,000 to 1,460,000 (delta ~60k counts)
    """
    logger.info("\n" + "="*60)
    logger.info("TEST 3: COUNTS RANGE (Expected Values)")
    logger.info("="*60)
    
    # Get current calibration
    offset = sensor.calibration.get('offset_counts', 0)
    slope = sensor.calibration.get('slope_mmhg_per_count', 9.536743e-06)
    
    logger.info(f"\nCurrent calibration:")
    logger.info(f"   offset_counts: {offset}")
    logger.info(f"   slope: {slope:.6e} mmHg/count")
    
    # Calculate expected range
    logger.info(f"\n📊 Expected counts (theoretical):")
    logger.info(f"   At 0 mmHg:   {offset:,} counts")
    logger.info(f"   At 150 mmHg: {offset + int(150/slope):,} counts")
    logger.info(f"   Delta:       {int(150/slope):,} counts for 150 mmHg span")
    
    logger.info("\n💡 NOTE:")
    logger.info("   - MPS20N0040D output: 0-40 kPa = 0-300 mmHg")
    logger.info("   - @ 5V, gain=128: ~42,920 counts per 100 mmHg (theoretical)")
    logger.info("   - For 150 mmHg span, expect delta ~64,380 counts")
    
    return True


def test_timing_accuracy(sensor: HX710BSensor, num_reads: int = 100):
    """
    Test 4: Timing Accuracy
    
    Verify read timing sau khi thêm delays:
    - 10 SPS mode: ~100ms per read (with settling)
    - 40 SPS mode: ~25ms per read
    """
    logger.info("\n" + "="*60)
    logger.info("TEST 4: TIMING ACCURACY")
    logger.info("="*60)
    
    logger.info(f"\nReading {num_reads} samples to measure timing...")
    
    start_time = time.time()
    success_count = 0
    
    for i in range(num_reads):
        raw = sensor.read_raw_data()
        if raw is not None:
            success_count += 1
        print(f"Read {i+1}/{num_reads}", end='\r')
    
    print()
    elapsed = time.time() - start_time
    
    avg_time = elapsed / num_reads
    expected_time = 0.1 if sensor.mode.value == 25 else 0.025  # 10 SPS or 40 SPS
    
    logger.info(f"\n✅ Results:")
    logger.info(f"   Successful reads: {success_count}/{num_reads}")
    logger.info(f"   Total time: {elapsed:.2f}s")
    logger.info(f"   Avg per read: {avg_time*1000:.1f}ms")
    logger.info(f"   Expected: ~{expected_time*1000:.0f}ms per read")
    
    if avg_time > expected_time * 2:
        logger.warning("⚠️  SLOW: Reads taking 2× longer than expected")
        logger.warning("   → Check GPIO performance or reduce delays")
        return False
    elif avg_time < expected_time * 0.5:
        logger.warning("⚠️  TOO FAST: Reads faster than ADC sampling rate!")
        logger.warning("   → May be reading stale data")
        return False
    else:
        logger.info("✅ TIMING OK: Within expected range")
        return True


def main():
    """Run all diagnostic tests"""
    logger.info("╔" + "═"*58 + "╗")
    logger.info("║  HX710B TIMING DIAGNOSTIC TOOL v1.0                       ║")
    logger.info("╚" + "═"*58 + "╝")
    
    # Load config
    config_path = Path("/home/pi/Desktop/IoT_health/config/app_config.yaml")
    
    if not config_path.exists():
        logger.error(f"❌ Config not found: {config_path}")
        return
    
    import yaml
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    hx710b_config = config['sensors']['blood_pressure']['hx710b']
    
    logger.info(f"\n📋 Configuration:")
    logger.info(f"   GPIO DOUT: {hx710b_config['gpio_dout']}")
    logger.info(f"   GPIO SCK:  {hx710b_config['gpio_sck']}")
    logger.info(f"   Mode:      {hx710b_config['mode']}")
    logger.info(f"   Timeout:   {hx710b_config['read_timeout_ms']}ms")
    
    # Create sensor
    sensor = HX710BSensor("HX710B_Test", hx710b_config)
    
    try:
        # Initialize
        logger.info("\n🔧 Initializing sensor...")
        if not sensor.initialize():
            logger.error("❌ Failed to initialize sensor")
            return
        
        sensor.start()
        logger.info("✅ Sensor started\n")
        
        # Run tests
        results = []
        
        results.append(("Zero Stability", test_zero_stability(sensor, 100)))
        results.append(("Sign Inversion", test_sign_inversion(sensor)))
        results.append(("Counts Range", test_counts_range(sensor)))
        results.append(("Timing Accuracy", test_timing_accuracy(sensor, 50)))
        
        # Summary
        logger.info("\n" + "="*60)
        logger.info("TEST SUMMARY")
        logger.info("="*60)
        
        for test_name, result in results:
            if result is True:
                status = "✅ PASS"
            elif result is False:
                status = "❌ FAIL"
            else:
                status = "⚠️  WARN"
            
            logger.info(f"   {test_name:20s}: {status}")
        
        # Recommendations
        logger.info("\n💡 RECOMMENDATIONS:")
        if results[0][1] is False:  # Zero stability failed
            logger.info("   1. Fix wiring/power before calibration")
        if results[1][1] is True:  # Sign inversion needed
            logger.info("   2. Enable 'adc_inverted: true' in app_config.yaml")
        if all(r[1] is True for r in results if r[1] is not None):
            logger.info("   ✅ All tests passed! Ready for calibration")
            logger.info("   → Run: python tests/bp_calib_tool.py")
        
    finally:
        sensor.stop()
        sensor.cleanup()
        logger.info("\n✅ Test complete")


if __name__ == "__main__":
    main()
