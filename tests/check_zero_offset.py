#!/usr/bin/env python3
"""
Check Zero Offset
=================

Kiểm tra raw counts khi zero pressure và recommend offset mới.

Author: IoT Health Monitor Team
Date: 2026-01-05
"""

import logging
import time
import sys
import numpy as np

sys.path.append('/home/pi/Desktop/IoT_health')

from src.sensors.hx710b_sensor import HX710BSensor
import yaml

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

def check_zero_offset():
    """Check raw counts at zero pressure"""
    
    # Load config
    with open('/home/pi/Desktop/IoT_health/config/app_config.yaml') as f:
        config = yaml.safe_load(f)
    
    hx710b_config = config['sensors']['blood_pressure']['hx710b']
    
    # Create sensor
    sensor = HX710BSensor("HX710B_Test", hx710b_config)
    
    if not sensor.initialize():
        print("❌ Failed to initialize sensor")
        return
    
    sensor.start()
    
    print("\n" + "="*60)
    print("ZERO OFFSET CHECK")
    print("="*60)
    print("\n⚠️  IMPORTANT: Ensure NO pressure on sensor!")
    print("   - Cuff must be EMPTY")
    print("   - Valve must be OPEN")
    print("   - No external force on sensor")
    print()
    
    input("Press ENTER when ready...")
    
    print("\n📊 Reading raw counts (100 samples)...")
    
    raw_counts = []
    
    for i in range(100):
        raw_data = sensor.read_raw_data()
        
        if raw_data is not None:
            raw_counts.append(raw_data)
            
            if (i + 1) % 10 == 0:
                print(f"  {i+1}/100: {raw_data}")
        
        time.sleep(0.1)
    
    if len(raw_counts) < 50:
        print("\n❌ Insufficient readings")
        sensor.stop()
        sensor.cleanup()
        return
    
    # Statistics
    mean_counts = np.mean(raw_counts)
    std_counts = np.std(raw_counts)
    min_counts = np.min(raw_counts)
    max_counts = np.max(raw_counts)
    
    # Current config
    current_offset = hx710b_config['calibration']['offset_counts']
    
    print("\n" + "="*60)
    print("RESULTS:")
    print("="*60)
    print(f"Samples:         {len(raw_counts)}")
    print(f"Mean:            {mean_counts:.0f} counts")
    print(f"Std:             {std_counts:.1f} counts")
    print(f"Range:           {min_counts} to {max_counts}")
    print(f"\nCurrent offset:  {current_offset} counts")
    print(f"Difference:      {mean_counts - current_offset:+.0f} counts")
    
    # Check headroom
    max_adc = 8388607
    headroom_current = max_adc - current_offset
    headroom_new = max_adc - mean_counts
    
    print("\n" + "-"*60)
    print("HEADROOM ANALYSIS:")
    print("-"*60)
    print(f"ADC Max:                {max_adc:,} counts")
    print(f"Current offset:         {current_offset:,} counts")
    print(f"Headroom (current):     {headroom_current:,} counts ({headroom_current/max_adc*100:.1f}%)")
    print(f"\nMeasured zero:          {mean_counts:.0f} counts")
    print(f"Headroom (if updated):  {headroom_new:,.0f} counts ({headroom_new/max_adc*100:.1f}%)")
    
    # Calculate max measurable pressure with each offset
    slope = hx710b_config['calibration']['slope_mmhg_per_count']
    
    max_pressure_current = headroom_current * slope
    max_pressure_new = headroom_new * slope
    
    print("\n" + "-"*60)
    print("MAX MEASURABLE PRESSURE:")
    print("-"*60)
    print(f"With current offset ({current_offset}): {max_pressure_current:.0f} mmHg")
    print(f"With new offset ({mean_counts:.0f}):    {max_pressure_new:.0f} mmHg")
    
    # Recommendation
    print("\n" + "="*60)
    print("RECOMMENDATION:")
    print("="*60)
    
    if mean_counts < current_offset - 100000:
        print("⚠️  WARNING: Zero offset decreased significantly!")
        print(f"   Change: {current_offset} → {mean_counts:.0f} ({mean_counts - current_offset:+.0f})")
        print("\n   This may indicate:")
        print("   1. Sensor drift")
        print("   2. Temperature change")
        print("   3. Previous calibration was wrong")
        
    if max_pressure_new < 250:
        print("❌ CRITICAL: Insufficient headroom!")
        print(f"   Can only measure up to {max_pressure_new:.0f} mmHg")
        print("\n   Solutions:")
        print("   1. Increase ADC gain (if possible)")
        print("   2. Use voltage divider on sensor output")
        print("   3. Accept lower max pressure range")
    else:
        print(f"✅ Sufficient headroom: {max_pressure_new:.0f} mmHg max")
        print(f"\n   Recommended new offset: {mean_counts:.0f}")
        print(f"   Update in config/app_config.yaml:")
        print(f"   offset_counts: {int(mean_counts)}")
    
    # Saturation check
    if any(c >= max_adc - 1000 for c in raw_counts):
        print("\n❌ DANGER: Some readings near saturation!")
        print("   ADC may already be saturated at zero pressure")
        print("   → Hardware adjustment required")
    
    sensor.stop()
    sensor.cleanup()

if __name__ == "__main__":
    check_zero_offset()
