
#!/usr/bin/env python3
"""
ADC Analysis Tool - Find optimal offset and slope

This tool helps diagnose ADC reading issues and calibrate offset/slope
by collecting multiple readings and analyzing patterns.

Usage:
    python3 tests/analyze_adc_readings.py
"""

import sys
import os
import time
import yaml
from pathlib import Path
from collections import Counter
import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None

from src.sensors.blood_pressure_sensor import HX710B

# GPIO pins for pump/valve
GPIO_PUMP = 26   # Pump control
GPIO_VALVE = 16  # Valve control (NO: HIGH=close, LOW=open)


def setup_pump_valve_safe():
    """Setup pump and valve to safe state (pump OFF, valve OPEN)"""
    if not GPIO:
        return
    
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        # Setup pump (OFF)
        GPIO.setup(GPIO_PUMP, GPIO.OUT, initial=GPIO.LOW)
        
        # Setup valve (OPEN for NO valve - LOW=open, HIGH=close)
        GPIO.setup(GPIO_VALVE, GPIO.OUT, initial=GPIO.LOW)
        
        print("✅ Pump OFF, Valve OPEN (zero pressure mode)")
        
    except Exception as e:
        print(f"⚠️  Failed to setup pump/valve: {e}")


def cleanup_pump_valve():
    """Cleanup pump/valve GPIO"""
    if not GPIO:
        return
    
    try:
        # Keep valve OPEN on exit
        GPIO.output(GPIO_PUMP, GPIO.LOW)
        GPIO.output(GPIO_VALVE, GPIO.LOW)
    except:
        pass


def load_config():
    """Load configuration"""
    config_path = Path(__file__).parent.parent / "config" / "app_config.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def analyze_adc_readings(duration_s=10, verbose=False):
    """
    Collect and analyze ADC readings
    
    Args:
        duration_s: How long to collect data (seconds)
        verbose: Show each reading
    """
    print("="*70)
    print("ADC READING ANALYSIS TOOL")
    print("="*70)
    
    # Load config
    config = load_config()
    hx_config = config['sensors']['hx710b']
    calib = hx_config['calibration']
    
    print(f"\n📊 Current Configuration:")
    print(f"   Slope:  {calib['slope_mmhg_per_count']:.10f} mmHg/count")
    print(f"   Offset: {calib['offset_counts']} counts")
    print(f"   GPIO:   DOUT={hx_config['gpio_dout']}, SCK={hx_config['gpio_sck']}")
    print(f"   Timeout: {hx_config['timeout_ms']} ms")
    
    # Setup pump and valve first (CRITICAL!)
    print(f"\n🔧 Setting up pump and valve...")
    setup_pump_valve_safe()
    
    # Initialize HX710B
    print(f"\n🔧 Initializing HX710B...")
    adc = HX710B(
        gpio_dout=hx_config['gpio_dout'],
        gpio_sck=hx_config['gpio_sck'],
        timeout_ms=hx_config['timeout_ms']
    )
    
    if not adc.initialize():
        print("❌ Failed to initialize HX710B")
        return
    
    print("✅ HX710B initialized")
    
    # Quick test read
    print("\n🔍 Testing ADC connection...")
    test_success = 0
    for attempt in range(5):
        raw = adc.read_raw()
        if raw is not None and raw not in [-1, 0, -2]:
            test_success += 1
            print(f"   Test {attempt+1}/5: ✅ {raw:10d} counts")
        else:
            print(f"   Test {attempt+1}/5: ❌ Timeout or error")
        time.sleep(0.2)
    
    # Warn if timeout too short
    if hx_config['timeout_ms'] < 300:
        print(f"\n⚠️  Timeout is only {hx_config['timeout_ms']}ms - this is too short for 10 SPS mode!")
        print(f"   Recommend: timeout_ms: 500 in config/app_config.yaml")
        print(f"   (10 SPS = 100ms per sample, need margin for jitter)")
    
    if test_success == 0:
        print("\n❌ ADC test failed - no valid readings!")
        print("   Check:")
        print("   1. HX710B power (3.3V on VCC pin)")
        print("   2. Wiring: DOUT→GPIO6, SCK→GPIO5, GND→GND")
        print("   3. Sensor connected to E+/E-")
        print("   4. Valve is OPEN (should hear air escaping)")
        adc.cleanup()
        cleanup_pump_valve()
        return
    elif test_success < 3:
        print(f"\n⚠️  ADC unreliable ({test_success}/5 success)")
        print("   Continuing anyway, but expect many timeouts...")
    else:
        print(f"\n✅ ADC working ({test_success}/5 success)")
    
    # Collect readings
    print(f"\n📡 Collecting readings for {duration_s}s...")
    print("   ⚠️  IMPORTANT: Valve is now OPEN - you should hear air escaping from cuff")
    print("   This ensures ZERO pressure for accurate offset measurement")
    print("   Note: HX710B has LOW sample rate (~10 SPS), so this will be slow\n")
    
    input("Press ENTER to start collecting (or Ctrl+C to abort)...")
    
    readings = []
    timeouts = 0
    error_values = 0  # Count -1, 0, -2
    start_time = time.time()
    last_print = start_time
    
    print("\n📊 Collecting data...")
    print("   (Each '.' = timeout, each '+' = valid reading)\n")
    
    while time.time() - start_time < duration_s:
        raw = adc.read_raw()
        
        if raw is not None:
            # Check for error values
            if raw in [-1, 0, -2]:
                error_values += 1
                if verbose:
                    print(f"   [ERR] Raw: {raw:10d} counts (ERROR VALUE - rejected)")
                sys.stdout.write("E")  # E = error value
                sys.stdout.flush()
            else:
                readings.append(raw)
                
                if verbose:
                    pressure = (raw - calib['offset_counts']) * calib['slope_mmhg_per_count']
                    print(f"   [{len(readings):3d}] Raw: {raw:10d} counts → {pressure:6.2f} mmHg")
                else:
                    sys.stdout.write("+")  # + = valid
                    sys.stdout.flush()
        else:
            timeouts += 1
            if not verbose:
                sys.stdout.write(".")  # . = timeout
                sys.stdout.flush()
        
        # Progress indicator
        if not verbose and time.time() - last_print > 5.0:
            elapsed = time.time() - start_time
            print(f"\n   Progress: {elapsed:.1f}s / {duration_s}s  |  Valid: {len(readings)}  |  Timeouts: {timeouts}  |  Errors: {error_values}")
            last_print = time.time()
        
        # Wait longer between reads (HX710B is SLOW ~10 SPS)
        time.sleep(0.15)  # 150ms (safe for 10 SPS = 100ms per sample)
    
    print()  # New line after progress dots
    
    # Cleanup
    adc.cleanup()
    cleanup_pump_valve()
    
    # Analysis
    print("\n" + "="*70)
    print("ANALYSIS RESULTS")
    print("="*70)
    
    if not readings:
        print("❌ No valid readings collected!")
        print(f"   Timeouts: {timeouts}")
        print(f"   Error values (-1/0/-2): {error_values}")
        print("\n   Possible issues:")
        print("   1. HX710B not powered (check 3.3V VCC)")
        print("   2. Wiring incorrect (DOUT→GPIO6, SCK→GPIO5)")
        print("   3. GPIO pins wrong in config")
        print("   4. HX710B damaged or in power-down mode")
        print(f"   5. Timeout too short ({hx_config['timeout_ms']}ms) for low SPS mode")
        print("   6. Valve not opening (check GPIO16 wiring)")
        cleanup_pump_valve()
        return
    
    # Statistics
    readings_np = np.array(readings)
    
    print(f"\n📊 Collection Summary:")
    print(f"   Duration:           {duration_s:.1f} s")
    print(f"   Valid readings:     {len(readings)}")
    print(f"   Timeouts:           {timeouts}")
    print(f"   Error values:       {error_values}")
    print(f"   Total attempts:     {len(readings) + timeouts + error_values}")
    print(f"   Success rate:       {len(readings)/(len(readings)+timeouts+error_values)*100:.1f}%")
    print(f"   Effective SPS:      {len(readings)/duration_s:.1f} Hz (expected: ~{hx_config.get('sps_hint', 10)} Hz)")
    
    if len(readings) < 10:
        print(f"\n⚠️  WARNING: Very few readings ({len(readings)})!")
        print(f"   Results may not be reliable. Consider:")
        print(f"   - Increase duration (--duration 30 or more)")
        print(f"   - Check HX710B power stability")
        print(f"   - Check for electrical noise")
    
    print(f"\n📈 Raw Counts (ADC values):")
    print(f"   Min:    {readings_np.min():10d}")
    print(f"   Max:    {readings_np.max():10d}")
    print(f"   Mean:   {readings_np.mean():10.1f}")
    print(f"   Median: {np.median(readings_np):10.1f}")
    print(f"   StdDev: {readings_np.std():10.1f}")
    
    # Convert to pressure
    pressures = (readings_np - calib['offset_counts']) * calib['slope_mmhg_per_count']
    
    print(f"\n💧 Pressure (mmHg) using current calibration:")
    print(f"   Min:    {pressures.min():6.2f} mmHg")
    print(f"   Max:    {pressures.max():6.2f} mmHg")
    print(f"   Mean:   {pressures.mean():6.2f} mmHg")
    print(f"   Median: {np.median(pressures):6.2f} mmHg")
    print(f"   StdDev: {pressures.std():6.2f} mmHg")
    
    # Find most common values (detect stuck readings)
    counter = Counter(readings)
    most_common = counter.most_common(5)
    
    print(f"\n🔢 Most Common Raw Values:")
    for value, count in most_common:
        percentage = count / len(readings) * 100
        pressure = (value - calib['offset_counts']) * calib['slope_mmhg_per_count']
        print(f"   {value:10d} counts → {pressure:7.2f} mmHg  |  {count:4d} times ({percentage:5.1f}%)")
    
    # Detect issues
    print(f"\n⚠️  Issue Detection:")
    issues_found = False
    
    # Check for -1, 0, -2 (error values)
    error_values = [r for r in readings if r in [-1, 0, -2]]
    if error_values:
        print(f"   ❌ Found {len(error_values)} error readings ({len(error_values)/len(readings)*100:.1f}%)")
        print(f"      Values: {Counter(error_values)}")
        issues_found = True
    
    # Check if single value dominates (stuck ADC)
    if most_common[0][1] > len(readings) * 0.5:
        print(f"   ❌ ADC stuck at {most_common[0][0]} ({most_common[0][1]/len(readings)*100:.1f}% of readings)")
        issues_found = True
    
    # Check if range is too small (no variation)
    if readings_np.std() < 10:
        print(f"   ⚠️  Very low variation (StdDev={readings_np.std():.1f} counts)")
        print(f"      ADC may not be responding to pressure changes")
        issues_found = True
    
    # Check if pressure range is reasonable
    if abs(pressures.mean()) > 10:
        print(f"   ⚠️  Zero-pressure reading is {pressures.mean():.1f} mmHg (should be ~0)")
        print(f"      OFFSET DRIFT detected - recommend recalibration")
        issues_found = True
    
    if not issues_found:
        print(f"   ✅ No obvious issues detected")
    
    # Recommendations
    print(f"\n" + "="*70)
    print("RECOMMENDATIONS")
    print("="*70)
    
    # Calculate recommended offset (median of readings at zero pressure)
    recommended_offset = int(np.median(readings_np))
    offset_change = recommended_offset - calib['offset_counts']
    
    print(f"\n📝 Offset Calibration:")
    print(f"   Current offset:     {calib['offset_counts']} counts")
    print(f"   Measured zero:      {recommended_offset} counts (median)")
    print(f"   Recommended change: {offset_change:+d} counts")
    
    if abs(offset_change) > 1000:
        print(f"   ⚠️  LARGE OFFSET DRIFT: {offset_change:+d} counts")
        print(f"   Action: Update offset in config/app_config.yaml:")
        print(f"           offset_counts: {recommended_offset}")
    elif abs(offset_change) > 100:
        print(f"   ⚠️  Moderate drift: {offset_change:+d} counts")
        print(f"   Recommend recalibration")
    else:
        print(f"   ✅ Offset is good (drift < 100 counts)")
    
    # Slope recommendation
    print(f"\n📐 Slope Verification:")
    print(f"   Current slope: {calib['slope_mmhg_per_count']:.10f} mmHg/count")
    print(f"   Expected:      9.536743e-06 mmHg/count (from datasheet)")
    slope_error = abs(calib['slope_mmhg_per_count'] - 9.536743e-06) / 9.536743e-06 * 100
    print(f"   Error:         {slope_error:.2f}%")
    
    if slope_error > 10:
        print(f"   ❌ Slope differs significantly from datasheet")
        print(f"   Recommend slope calibration with known pressure reference")
    else:
        print(f"   ✅ Slope is within tolerance")
    
    # Next steps
    print(f"\n🎯 Next Steps:")
    print(f"   1. If offset drift detected:")
    print(f"      → python3 tests/bp_calib_tool.py offset-electric")
    print(f"   2. If slope error high:")
    print(f"      → python3 tests/bp_calib_tool.py slope-manual --pressure 150")
    print(f"   3. Re-run this analysis to verify:")
    print(f"      → python3 tests/analyze_adc_readings.py")
    print(f"   4. Test BP measurement:")
    print(f"      → python3 tests/test_bp_v2.py")


if __name__ == "__main__":
    try:
        import argparse
        parser = argparse.ArgumentParser(description="Analyze HX710B ADC readings")
        parser.add_argument('-d', '--duration', type=int, default=10,
                          help='Collection duration in seconds (default: 10)')
        parser.add_argument('-v', '--verbose', action='store_true',
                          help='Show each reading')
        
        args = parser.parse_args()
        
        analyze_adc_readings(duration_s=args.duration, verbose=args.verbose)
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        cleanup_pump_valve()
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
        cleanup_pump_valve()
