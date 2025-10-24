#!/usr/bin/env python3
"""
Test HX710B Driver - Verify datasheet-accurate implementation
==============================================================

Usage:
    python3 tests/test_hx710b_driver.py [--mode MODE] [--duration SECONDS]

Options:
    --mode MODE        10sps or 40sps (default: 10sps)
    --duration SECONDS Test duration in seconds (default: 10)
"""

import sys
import argparse
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.sensors.hx710b_driver import HX710BDriver, HX710Mode

def main():
    parser = argparse.ArgumentParser(description='Test HX710B Driver')
    parser.add_argument('--mode', choices=['10sps', '40sps'], default='10sps',
                       help='Data rate mode')
    parser.add_argument('--duration', type=int, default=10,
                       help='Test duration (seconds)')
    args = parser.parse_args()
    
    # Select mode
    mode = HX710Mode.DIFFERENTIAL_10SPS if args.mode == '10sps' else HX710Mode.DIFFERENTIAL_40SPS
    
    print("="*70)
    print("HX710B DRIVER TEST (Datasheet-accurate implementation)")
    print("="*70)
    print(f"\nMode: {mode.name}")
    print(f"Duration: {args.duration}s")
    
    # Initialize driver
    print("\n🔧 Initializing driver...")
    driver = HX710BDriver(
        gpio_dout=6,
        gpio_sck=5,
        mode=mode,
        timeout_ms=500
    )
    
    if not driver.initialize():
        print("❌ Initialization failed")
        return 1
    
    print("✅ Driver initialized")
    
    # Test reads
    print(f"\n📊 Reading {args.duration}s of data...")
    print("   (Each '+' = valid, 'S' = saturated, '.' = timeout)\n")
    
    readings = []
    saturated = []
    timeouts = 0
    start_time = time.time()
    
    while time.time() - start_time < args.duration:
        value = driver.read()
        
        if value is not None:
            if driver.is_saturated(value):
                sys.stdout.write("S")
                saturated.append(value)
            else:
                sys.stdout.write("+")
                readings.append(value)
        else:
            sys.stdout.write(".")
            timeouts += 1
        
        sys.stdout.flush()
        
        # Progress indicator every 20 readings
        total = len(readings) + len(saturated) + timeouts
        if total % 20 == 0 and total > 0:
            elapsed = time.time() - start_time
            sps = total / elapsed
            print(f"  [{total} reads, {sps:.1f} SPS]")
        
        time.sleep(0.01)  # Brief pause
    
    elapsed = time.time() - start_time
    
    # Statistics
    print(f"\n\n📊 Results:")
    print(f"   Duration:      {elapsed:.2f}s")
    print(f"   Valid reads:   {len(readings)}")
    print(f"   Saturated:     {len(saturated)}")
    print(f"   Timeouts:      {timeouts}")
    print(f"   Total:         {len(readings) + len(saturated) + timeouts}")
    print(f"   Success rate:  {len(readings)/(len(readings)+len(saturated)+timeouts)*100:.1f}%")
    print(f"   Effective SPS: {len(readings)/elapsed:.1f} Hz")
    
    if readings:
        import numpy as np
        readings_np = np.array(readings)
        
        print(f"\n📈 Statistics (valid readings only):")
        print(f"   Min:    {readings_np.min():10d} counts")
        print(f"   Max:    {readings_np.max():10d} counts")
        print(f"   Mean:   {readings_np.mean():10.1f} counts")
        print(f"   Median: {np.median(readings_np):10.1f} counts")
        print(f"   StdDev: {readings_np.std():10.1f} counts")
    
    # Driver stats
    stats = driver.get_stats()
    print(f"\n📊 Driver Statistics:")
    print(f"   Read count:    {stats['read_count']}")
    print(f"   Error count:   {stats['error_count']}")
    print(f"   Error rate:    {stats['error_rate']*100:.1f}%")
    print(f"   Last value:    {stats['last_value']}")
    
    # Diagnosis
    print(f"\n🎯 Diagnosis:")
    expected_sps = 10 if mode == HX710Mode.DIFFERENTIAL_10SPS else 40
    actual_sps = len(readings) / elapsed
    
    if len(readings) >= expected_sps * elapsed * 0.8:  # At least 80% expected rate
        print(f"   ✅ EXCELLENT - Achieving ~{actual_sps:.1f} SPS (expected ~{expected_sps})")
    elif len(readings) >= expected_sps * elapsed * 0.5:
        print(f"   ⚠️  MODERATE - Only {actual_sps:.1f} SPS (expected ~{expected_sps})")
    else:
        print(f"   ❌ POOR - Only {actual_sps:.1f} SPS (expected ~{expected_sps})")
    
    if len(saturated) > 0:
        print(f"   ⚠️  {len(saturated)} saturated values (check sensor wiring)")
    
    if timeouts > len(readings) * 0.2:  # More than 20% timeouts
        print(f"   ⚠️  High timeout rate ({timeouts}/{len(readings)+timeouts})")
    
    if readings:
        stability = readings_np.std() / abs(readings_np.mean()) if readings_np.mean() != 0 else 0
        if stability < 0.01:  # < 1% variation
            print(f"   ✅ Good stability (StdDev/Mean = {stability*100:.2f}%)")
        else:
            print(f"   ⚠️  High variation (StdDev/Mean = {stability*100:.2f}%)")
    
    # Cleanup
    driver.cleanup()
    print("\n✅ Cleanup done")
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
