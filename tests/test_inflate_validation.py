#!/usr/bin/env python3
"""
Test Inflate Pressure Validation
=================================

Kiểm tra áp suất thực tế khi inflate vs áp suất đọc được.

Steps:
1. Inflate đến target (190 mmHg theo system)
2. Dừng bơm
3. Đọc áp với máy thương mại (nếu có pressure gauge)
4. So sánh

Author: IoT Health Monitor Team
Date: 2026-01-05
"""

import logging
import time
import sys
sys.path.append('/home/pi/Desktop/IoT_health')

from src.sensors.blood_pressure_sensor import BloodPressureSensor
import yaml

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

def test_inflate_pressure():
    """Test inflate pressure accuracy"""
    
    # Load config
    with open('/home/pi/Desktop/IoT_health/config/app_config.yaml') as f:
        config = yaml.safe_load(f)
    
    bp_config = config['sensors']['blood_pressure']
    
    # Create sensor
    sensor = BloodPressureSensor("BP_Test", bp_config)
    
    if not sensor.initialize():
        print("❌ Failed to initialize sensor")
        return
    
    print("\n" + "="*60)
    print("INFLATE PRESSURE VALIDATION TEST")
    print("="*60)
    print("\nInstructions:")
    print("1. System sẽ inflate đến 190 mmHg (theo reading)")
    print("2. Khi inflate xong, đọc áp trên máy thương mại (nếu có)")
    print("3. Nhập áp đọc được từ máy thương mại")
    print("4. System sẽ tính sai số\n")
    
    input("Press ENTER to start inflate test...")
    
    try:
        # Initialize hardware
        sensor.hardware.initialize()
        sensor.adc_sensor.start()
        
        # Inflate
        print("\n🔵 Starting inflate to 190 mmHg...")
        sensor.hardware.valve_close()
        sensor.hardware.pump_on()
        
        target = 190.0
        start_time = time.time()
        
        while True:
            pressure_data = sensor.adc_sensor.get_latest_data()
            
            if pressure_data:
                pressure = pressure_data['pressure_mmhg']
                elapsed = time.time() - start_time
                
                print(f"\r⏱️  {elapsed:.1f}s | Pressure: {pressure:.1f} mmHg", end='', flush=True)
                
                if pressure >= target:
                    print(f"\n✅ Target reached: {pressure:.1f} mmHg")
                    break
                
                if elapsed > 30:
                    print("\n⏰ Timeout (30s)")
                    break
            
            time.sleep(0.1)
        
        # Stop pump
        sensor.hardware.pump_off()
        print("\n🛑 Pump stopped")
        
        # Wait for pressure to stabilize
        print("\n⏳ Waiting 3s for stabilization...")
        time.sleep(3)
        
        # Read final pressure
        final_data = sensor.adc_sensor.get_latest_data()
        if final_data:
            system_pressure = final_data['pressure_mmhg']
            print(f"\n📊 System reading: {system_pressure:.1f} mmHg")
            
            # Get ground truth
            print("\n" + "-"*60)
            print("Bây giờ, đọc áp suất trên máy thương mại (nếu có pressure gauge)")
            ground_truth_str = input("Nhập áp suất thực tế (mmHg) hoặc ENTER để skip: ")
            
            if ground_truth_str.strip():
                try:
                    ground_truth = float(ground_truth_str)
                    error = system_pressure - ground_truth
                    error_pct = (error / ground_truth) * 100
                    
                    print("\n" + "="*60)
                    print("RESULTS:")
                    print("="*60)
                    print(f"System reading:  {system_pressure:.1f} mmHg")
                    print(f"Ground truth:    {ground_truth:.1f} mmHg")
                    print(f"Error:           {error:+.1f} mmHg ({error_pct:+.1f}%)")
                    
                    if abs(error_pct) > 10:
                        print("\n⚠️  WARNING: Error > 10% - Slope calibration needed!")
                    else:
                        print("\n✅ Error acceptable (<10%)")
                    
                except ValueError:
                    print("❌ Invalid input")
        
        # Deflate
        print("\n🔽 Deflating...")
        sensor.hardware.valve_open()
        time.sleep(5)
        sensor.hardware.valve_close()
        
    finally:
        sensor.cleanup()
        print("\n✅ Test complete")

if __name__ == "__main__":
    test_inflate_pressure()
