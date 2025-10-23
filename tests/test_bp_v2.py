1#!/usr/bin/env python3
"""
Test script for BloodPressureSensor (V2 - Rewritten)

Usage:
    python3 tests/test_bp_v2.py
"""

import sys
import os
import time
import yaml
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.sensors.blood_pressure_sensor import BloodPressureSensor, MeasurementPhase


def load_config():
    """Load configuration from app_config.yaml"""
    config_path = Path(__file__).parent.parent / "config" / "app_config.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def on_measurement_complete(success, result=None, error=None):
    """Callback when measurement completes"""
    print("\n" + "="*60)
    print("MEASUREMENT CALLBACK")
    print("="*60)
    
    if success and result:
        print(f"✅ SUCCESS!")
        print(f"\n📊 BLOOD PRESSURE RESULTS:")
        print(f"  Systolic:        {result.systolic:.1f} mmHg")
        print(f"  Diastolic:       {result.diastolic:.1f} mmHg")
        print(f"  MAP:             {result.map:.1f} mmHg")
        print(f"  Pulse Pressure:  {result.pulse_pressure:.1f} mmHg")
        
        print(f"\n📈 QUALITY METRICS:")
        print(f"  Points collected:    {result.points_collected}")
        print(f"  Sample rate:         {result.sample_rate_hz:.1f} Hz")
        print(f"  Deflate duration:    {result.deflate_duration_s:.2f} s")
        print(f"  Oscillation amp:     {result.oscillation_amplitude:.4f} mmHg")
        
        print(f"\n✔️  VALIDATION:")
        print(f"  Valid:   {result.is_valid}")
        if result.validation_errors:
            print(f"  Errors:")
            for err in result.validation_errors:
                print(f"    - {err}")
        else:
            print(f"  No errors")
        
        print(f"\n💾 Result saved to sensor.last_result")
        
    else:
        print(f"❌ FAILED: {error}")
    
    print("="*60)


def print_status_bar(status):
    """Print progress bar for measurement"""
    phase = status['phase']
    pressure = status['pressure']
    progress = status['progress']
    
    # Progress bar
    bar_len = 30
    filled = int(bar_len * progress)
    bar = "█" * filled + "░" * (bar_len - filled)
    
    # Phase icon
    icons = {
        'idle': '⏸️ ',
        'safety_check': '🔍',
        'inflating': '⬆️ ',
        'deflating': '⬇️ ',
        'analyzing': '🧮',
        'complete': '✅',
        'error': '❌'
    }
    icon = icons.get(phase, '  ')
    
    print(f"\r{icon} [{bar}] {progress*100:3.0f}% | {phase:15s} | {pressure:5.1f} mmHg", end='', flush=True)


def test_measurement_interactive():
    """Interactive measurement test"""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("="*60)
    print("BLOOD PRESSURE SENSOR - INTERACTIVE TEST")
    print("="*60)
    
    # Load config
    print("\n📁 Loading configuration...")
    config = load_config()
    
    print(f"   Slope: {config['sensors']['hx710b']['calibration']['slope_mmhg_per_count']:.10f}")
    print(f"   Offset: {config['sensors']['hx710b']['calibration']['offset_counts']}")
    print(f"   Inflate target: {config['sensors']['blood_pressure']['inflate_target_mmhg']} mmHg")
    
    # Initialize sensor
    print("\n🔧 Initializing sensor...")
    sensor = BloodPressureSensor(config['sensors'])
    
    if not sensor.initialize():
        print("❌ Failed to initialize sensor")
        return
    
    print("✅ Sensor initialized")
    
    # Start sensor
    if not sensor.start():
        print("❌ Failed to start sensor")
        return
    
    print("✅ Sensor started")
    
    # Main loop
    try:
        while True:
            print("\n" + "="*60)
            print("MENU")
            print("="*60)
            print("1. Start BP measurement (with callback)")
            print("2. Start BP measurement (polling mode)")
            print("3. Check status")
            print("4. View last result")
            print("5. Exit")
            print()
            
            choice = input("Select option: ").strip()
            
            if choice == '1':
                # Measurement with callback
                print("\n🚀 Starting measurement (callback mode)...")
                print("   Progress will be displayed in real-time")
                print("   Press Ctrl+C to abort\n")
                
                try:
                    sensor.start_measurement(callback=on_measurement_complete)
                    
                    # Poll status until complete
                    while sensor.is_measuring:
                        status = sensor.get_measurement_status()
                        print_status_bar(status)
                        time.sleep(0.2)
                    
                    print()  # New line after progress bar
                    
                except KeyboardInterrupt:
                    print("\n\n⚠️  User abort - Emergency deflate")
                    sensor.stop_measurement()
                    print("✅ Measurement stopped")
            
            elif choice == '2':
                # Measurement polling mode (no callback)
                print("\n🚀 Starting measurement (polling mode)...")
                print("   No callback, manual polling")
                print("   Press Ctrl+C to abort\n")
                
                try:
                    sensor.start_measurement(callback=None)
                    
                    # Poll status
                    while sensor.is_measuring:
                        status = sensor.get_measurement_status()
                        print_status_bar(status)
                        time.sleep(0.2)
                    
                    print()  # New line
                    
                    # Get result manually
                    result = sensor.get_last_result()
                    if result:
                        on_measurement_complete(success=True, result=result)
                    else:
                        print("❌ No result available")
                    
                except KeyboardInterrupt:
                    print("\n\n⚠️  User abort - Emergency deflate")
                    sensor.stop_measurement()
                    print("✅ Measurement stopped")
            
            elif choice == '3':
                # Check status
                status = sensor.get_measurement_status()
                print(f"\n📊 Current Status:")
                print(f"   Measuring:  {status['is_measuring']}")
                print(f"   Phase:      {status['phase']}")
                print(f"   Pressure:   {status['pressure']:.1f} mmHg")
                print(f"   Progress:   {status['progress']*100:.0f}%")
            
            elif choice == '4':
                # View last result
                result = sensor.get_last_result()
                if result:
                    on_measurement_complete(success=True, result=result)
                else:
                    print("\n❌ No measurement result available")
                    print("   Run a measurement first (option 1 or 2)")
            
            elif choice == '5':
                # Exit
                break
            
            else:
                print("❌ Invalid option")
    
    finally:
        print("\n🛑 Stopping sensor...")
        sensor.stop()
        print("✅ Sensor stopped")
        print("\nGoodbye! 👋")


if __name__ == "__main__":
    test_measurement_interactive()
