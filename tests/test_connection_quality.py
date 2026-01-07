#!/usr/bin/env python3
"""
HX710B Connection Quality Test
===============================

Kiểm tra chất lượng connection và đề xuất fix.

Author: IoT Health Monitor Team
Date: 2026-01-05
"""

import logging
import time
import sys
import numpy as np

sys.path.append('/home/pi/Desktop/IoT_health')

from src.sensors.hx710b_driver import HX710BDriver, HX710Mode
import yaml

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

def test_connection_quality():
    """Test HX710B connection quality"""
    
    print("\n" + "="*60)
    print("HX710B CONNECTION QUALITY TEST")
    print("="*60)
    print("\n⚠️  CRITICAL CHECKS:")
    print("   1. Cuff must be EMPTY")
    print("   2. Valve must be OPEN")
    print("   3. Pump must be OFF")
    print("   4. All wiring secure")
    print()
    
    input("Press ENTER when ready...")
    
    # Load config
    with open('/home/pi/Desktop/IoT_health/config/app_config.yaml') as f:
        config = yaml.safe_load(f)
    
    hx710b_config = config['sensors']['blood_pressure']['hx710b']
    
    # Create driver directly
    driver = HX710BDriver(
        gpio_dout=hx710b_config['gpio_dout'],
        gpio_sck=hx710b_config['gpio_sck'],
        mode=HX710Mode.DIFFERENTIAL_10SPS,
        timeout_ms=500
    )
    
    if not driver.initialize():
        print("❌ Failed to initialize driver")
        return
    
    print("\n📊 Reading 100 samples...")
    print("   (This will take ~10 seconds)")
    
    raw_counts = []
    saturated_count = 0
    timeout_count = 0
    
    for i in range(100):
        counts = driver.read(timeout_ms=500)
        
        if counts is None:
            timeout_count += 1
            print(f"\r  {i+1}/100: TIMEOUT", end='', flush=True)
        elif driver.is_saturated(counts):
            saturated_count += 1
            raw_counts.append(counts)
            print(f"\r  {i+1}/100: SATURATED ({counts})", end='', flush=True)
        else:
            raw_counts.append(counts)
            if (i + 1) % 10 == 0:
                print(f"\r  {i+1}/100: {counts}", end='', flush=True)
        
        time.sleep(0.1)
    
    print("\n")
    
    if len(raw_counts) < 50:
        print("\n❌ CRITICAL: Too many timeouts!")
        print(f"   Timeouts: {timeout_count}/100")
        print("\n   Possible causes:")
        print("   1. DOUT (GPIO6) not connected")
        print("   2. SCK (GPIO5) not connected")
        print("   3. Power supply issue")
        print("   4. Module damaged")
        driver.cleanup()
        return
    
    # Statistics
    mean_counts = np.mean(raw_counts)
    std_counts = np.std(raw_counts)
    min_counts = np.min(raw_counts)
    max_counts = np.max(raw_counts)
    range_counts = max_counts - min_counts
    
    print("="*60)
    print("CONNECTION QUALITY RESULTS:")
    print("="*60)
    print(f"Valid samples:   {len(raw_counts)}/100")
    print(f"Timeouts:        {timeout_count}/100")
    print(f"Saturated:       {saturated_count}/100")
    print()
    print(f"Mean:            {mean_counts:.0f} counts")
    print(f"Std:             {std_counts:.1f} counts")
    print(f"Range:           {min_counts} to {max_counts}")
    print(f"Span:            {range_counts} counts")
    print()
    
    # Quality assessment
    print("="*60)
    print("QUALITY ASSESSMENT:")
    print("="*60)
    
    # Check 1: Timeout rate
    timeout_rate = timeout_count / 100
    if timeout_rate > 0.1:
        print(f"❌ FAIL: High timeout rate ({timeout_rate:.0%})")
        print("   → Check DOUT/SCK connections")
    elif timeout_rate > 0.05:
        print(f"⚠️  WARNING: Some timeouts ({timeout_rate:.0%})")
    else:
        print(f"✅ PASS: Timeout rate OK ({timeout_rate:.0%})")
    
    # Check 2: Saturation
    sat_rate = saturated_count / len(raw_counts) if raw_counts else 0
    if sat_rate > 0.1:
        print(f"❌ FAIL: High saturation rate ({sat_rate:.0%})")
        print("   → Voltage divider needed or sensor output too high")
    elif sat_rate > 0:
        print(f"⚠️  WARNING: Some saturation ({sat_rate:.0%})")
    else:
        print(f"✅ PASS: No saturation")
    
    # Check 3: Noise (std)
    if std_counts > mean_counts:
        print(f"❌ FAIL: Extremely high noise (std > mean)")
        print(f"   std={std_counts:.0f}, mean={mean_counts:.0f}")
        print("   → Possible causes:")
        print("      1. Loose connection (vibration)")
        print("      2. Missing ground")
        print("      3. EMI/RFI interference")
        print("      4. Power supply noise")
    elif std_counts > 100000:
        print(f"❌ FAIL: Very high noise (std={std_counts:.0f})")
        print("   → Check grounding and shielding")
    elif std_counts > 10000:
        print(f"⚠️  WARNING: High noise (std={std_counts:.0f})")
        print("   → Acceptable but consider improvements")
    elif std_counts > 1000:
        print(f"⚙️  ACCEPTABLE: Moderate noise (std={std_counts:.0f})")
    else:
        print(f"✅ EXCELLENT: Low noise (std={std_counts:.0f})")
    
    # Check 4: Range
    if range_counts > 1000000:
        print(f"❌ FAIL: Excessive range ({range_counts:,} counts)")
        print("   → Signal unstable, check connections")
    elif range_counts > 100000:
        print(f"⚠️  WARNING: Large range ({range_counts:,} counts)")
    else:
        print(f"✅ PASS: Stable range ({range_counts:,} counts)")
    
    # Check 5: Mean position
    adc_max = 8388607
    if abs(mean_counts) > adc_max * 0.5:
        print(f"⚠️  WARNING: Mean offset high ({mean_counts/adc_max*100:.1f}% of max)")
        print("   → Limited headroom for measurement")
    else:
        print(f"✅ PASS: Mean offset reasonable ({mean_counts/adc_max*100:.1f}% of max)")
    
    # Overall verdict
    print("\n" + "="*60)
    print("OVERALL VERDICT:")
    print("="*60)
    
    if timeout_rate > 0.1 or sat_rate > 0.1 or std_counts > mean_counts:
        print("❌ CONNECTION QUALITY: POOR")
        print("\n   IMMEDIATE ACTIONS REQUIRED:")
        print("   1. Check all wire connections (especially GND)")
        print("   2. Re-seat connectors")
        print("   3. Check power supply voltage (should be 5.0V ±0.25V)")
        print("   4. Add bypass capacitor (100nF) near module VCC")
    elif std_counts > 10000 or range_counts > 100000:
        print("⚠️  CONNECTION QUALITY: FAIR")
        print("\n   RECOMMENDED ACTIONS:")
        print("   1. Tighten all connections")
        print("   2. Check ground continuity")
        print("   3. Keep wires away from power cables")
    else:
        print("✅ CONNECTION QUALITY: GOOD")
        print("\n   System ready for calibration")
        print(f"   Recommended offset: {int(mean_counts)}")
    
    driver.cleanup()

if __name__ == "__main__":
    test_connection_quality()
