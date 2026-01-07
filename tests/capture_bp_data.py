#!/usr/bin/env python3
"""
Capture BP Data for Analysis
=============================

Đo BP và lưu raw data để phân tích offline.

Output:
- pressures.npy: Array of pressure values
- timestamps.npy: Array of timestamps
- metadata.json: Measurement metadata

Author: IoT Health Monitor Team
Date: 2026-01-05
"""

import logging
import time
import sys
import numpy as np
import json
from pathlib import Path

sys.path.append('/home/pi/Desktop/IoT_health')

from src.sensors.blood_pressure_sensor import BloodPressureSensor
import yaml

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

def capture_bp_measurement():
    """Capture full BP measurement with raw data"""
    
    # Load config
    with open('/home/pi/Desktop/IoT_health/config/app_config.yaml') as f:
        config = yaml.safe_load(f)
    
    bp_config = config['sensors']['blood_pressure']
    
    # Create sensor
    sensor = BloodPressureSensor("BP_Capture", bp_config)
    
    if not sensor.initialize():
        print("❌ Failed to initialize sensor")
        return
    
    print("\n" + "="*60)
    print("BP DATA CAPTURE")
    print("="*60)
    print("\nThis will perform a full BP measurement and save raw data.")
    print("Data will be saved to: /home/pi/Desktop/IoT_health/bp_data/")
    print()
    
    # Create output directory
    output_dir = Path('/home/pi/Desktop/IoT_health/bp_data')
    output_dir.mkdir(exist_ok=True)
    
    # Prepare to capture
    captured_pressures = []
    captured_timestamps = []
    
    # Monkey-patch to capture data during deflate
    original_deflate = sensor._deflate_phase
    
    def capture_deflate_phase():
        result = original_deflate()
        
        # Copy captured data
        captured_pressures.extend(sensor.pressure_buffer)
        captured_timestamps.extend(sensor.timestamp_buffer)
        
        return result
    
    sensor._deflate_phase = capture_deflate_phase
    
    # Start measurement
    input("Press ENTER to start measurement...")
    
    measurement_complete = False
    result = None
    
    def on_complete(measurement):
        nonlocal measurement_complete, result
        measurement_complete = True
        result = measurement
        print(f"\n✅ Measurement complete: {measurement.systolic:.0f}/{measurement.diastolic:.0f} mmHg")
    
    sensor.start_measurement(callback=on_complete)
    
    # Wait for completion
    print("\n⏳ Measuring (this will take ~60-90 seconds)...")
    
    while not measurement_complete:
        time.sleep(1)
        print(".", end="", flush=True)
    
    print("\n")
    
    # Save data
    if len(captured_pressures) > 0:
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        
        # Save numpy arrays
        np.save(output_dir / f'pressures_{timestamp_str}.npy', np.array(captured_pressures))
        np.save(output_dir / f'timestamps_{timestamp_str}.npy', np.array(captured_timestamps))
        
        # Save metadata
        metadata = {
            'timestamp': timestamp_str,
            'samples': len(captured_pressures),
            'duration': captured_timestamps[-1] - captured_timestamps[0] if len(captured_timestamps) > 1 else 0,
            'sample_rate': len(captured_pressures) / (captured_timestamps[-1] - captured_timestamps[0]) if len(captured_timestamps) > 1 else 0,
            'result': {
                'systolic': float(result.systolic) if result else None,
                'diastolic': float(result.diastolic) if result else None,
                'map': float(result.map_value) if result else None,
                'heart_rate': float(result.heart_rate) if result else None,
                'quality': result.quality if result else None,
                'confidence': float(result.confidence) if result else None
            },
            'config': {
                'offset_counts': bp_config['hx710b']['calibration']['offset_counts'],
                'slope_mmhg_per_count': bp_config['hx710b']['calibration']['slope_mmhg_per_count'],
                'inflate_target': bp_config['inflate_target_mmhg'],
                'deflate_rate': bp_config['deflate_rate_mmhg_s']
            }
        }
        
        with open(output_dir / f'metadata_{timestamp_str}.json', 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print("="*60)
        print("DATA SAVED:")
        print("="*60)
        print(f"Pressures:  {output_dir}/pressures_{timestamp_str}.npy")
        print(f"Timestamps: {output_dir}/timestamps_{timestamp_str}.npy")
        print(f"Metadata:   {output_dir}/metadata_{timestamp_str}.json")
        print(f"\nSamples: {len(captured_pressures)}")
        print(f"Duration: {metadata['duration']:.1f}s")
        print(f"Sample rate: {metadata['sample_rate']:.1f} SPS")
        print()
        print("To analyze this data, run:")
        print(f"  python tests/analyze_envelope.py {timestamp_str}")
        
    else:
        print("❌ No data captured")
    
    # Cleanup
    sensor.stop_measurement()
    sensor.cleanup()

if __name__ == "__main__":
    capture_bp_measurement()
