#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Complete Blood Pressure Measurement Script
==========================================
Sử dụng BloodPressureSensor class (production-ready)

Features:
- Passive deflation (van đóng, rò tự nhiên)
- Professional signal processing (Butterworth + Hilbert)
- Safety monitoring (limits, leak, timeout)
- Quality assessment (SNR-based)
- AAMI validation

Hardware:
- HX710B ADC (GPIO 6=DOUT, 5=SCK)
- MPS20N0040D pressure sensor (0-300 mmHg)
- Pump: GPIO 26 (via optocoupler)
- Valve: GPIO 16 (via optocoupler, NO type)

Usage:
    python tests/test_full_bp_measurement.py
"""

import time
import logging
import sys
import RPi.GPIO as GPIO
import pathlib

# Setup path
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import BloodPressureSensor
from src.sensors.blood_pressure_sensor import (
    BloodPressureSensor,
    BloodPressureMeasurement,
    BPState,
    create_blood_pressure_sensor_from_config
)

# ============================================================================
# CẤU HÌNH CHUNG
# ============================================================================
GPIO_PUMP = 26          # Bơm (active HIGH)
GPIO_VALVE = 20         # Van NO (LOW = mở, HIGH = đóng)

# Blood Pressure Sensor Configuration
BP_CONFIG = {
    'enabled': True,
    'inflate_target_mmhg': 190.0,
    'deflate_rate_mmhg_s': 3.0,
    'max_pressure_mmhg': 220.0,
    'pump_gpio': GPIO_PUMP,
    'valve_gpio': GPIO_VALVE,
    'hx710b': {
        'enabled': True,
        'gpio_dout': 6,
        'gpio_sck': 5,
        'mode': '10sps',
        'read_timeout_ms': 1000,
        'calibration': {
            'offset_counts': 1078893,
            'slope_mmhg_per_count': 3.5765743256e-05,
            'adc_inverted': False
        }
    },
    'algorithm': {
        'sample_rate': 10.0,
        'bandpass_low': 0.5,
        'bandpass_high': 5.0,
        'filter_order': 4,
        'sys_ratio': 0.55,
        'dia_ratio': 0.80
    }
}

# ============================================================================
# LOGGING
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger("BP_Measurement_Test")


# ============================================================================
# CALLBACK HANDLER
# ============================================================================
def on_measurement_complete(measurement: BloodPressureMeasurement):
    """
    Callback khi đo xong - hiển thị kết quả
    
    Args:
        measurement: BloodPressureMeasurement object
    """
    print("\n" + "="*60)
    print("MEASUREMENT RESULT")
    print("="*60)
    print(f"Systolic (SYS):  {measurement.systolic:6.1f} mmHg")
    print(f"Diastolic (DIA): {measurement.diastolic:6.1f} mmHg")
    print(f"Mean (MAP):      {measurement.map_value:6.1f} mmHg")
    print(f"Heart Rate:      {measurement.heart_rate:6.1f} BPM")
    print(f"Pulse Pressure:  {measurement.pulse_pressure:6.1f} mmHg")
    print("="*60)
    print(f"Quality:         {measurement.quality.upper()}")
    print(f"Confidence:      {measurement.confidence:.2%}")
    print("="*60)
    
    # AHA Classification
    sys_bp = measurement.systolic
    dia_bp = measurement.diastolic
    
    if sys_bp < 120 and dia_bp < 80:
        category = "✓ Normal"
        emoji = "😊"
    elif sys_bp < 130 and dia_bp < 80:
        category = "⚠ Elevated"
        emoji = "😐"
    elif sys_bp < 140 or dia_bp < 90:
        category = "⚠ High BP Stage 1"
        emoji = "😟"
    elif sys_bp < 180 or dia_bp < 120:
        category = "⚠⚠ High BP Stage 2"
        emoji = "😨"
    else:
        category = "🚨 Hypertensive Crisis"
        emoji = "🚑"
    
    print(f"Category:        {category} {emoji}")
    print("="*60)
    
    # Validation flags
    print("\nValidation (AAMI):")
    for key, value in measurement.validation_flags.items():
        status = "✓" if value else "✗"
        print(f"  {status} {key.replace('_', ' ').title()}")
    
    # Metadata
    print("\nMeasurement Details:")
    print(f"  Timestamp:     {measurement.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Data points:   {measurement.metadata.get('data_points', 'N/A')}")
    print(f"  MAP amplitude: {measurement.metadata.get('map_amplitude', 0):.3f}")
    print(f"  Sample rate:   {measurement.metadata.get('sample_rate', 0):.1f} Hz")
    print("="*60 + "\n")


# ============================================================================
# MAIN MEASUREMENT FLOW
# ============================================================================
def measure_blood_pressure():
    """
    Quy trình đo huyết áp sử dụng BloodPressureSensor class
    
    Workflow:
    1. Create sensor từ config
    2. Start sensor (initialize hardware)
    3. Start measurement (non-blocking)
    4. Monitor state và hiển thị tiến trình
    5. Callback hiển thị kết quả
    6. Cleanup
    """
    print("\n" + "="*60)
    print("BLOOD PRESSURE MEASUREMENT")
    print("Using BloodPressureSensor (Production-Ready)")
    print("="*60)
    
    # Tạo sensor từ config
    log.info("Creating BloodPressureSensor...")
    sensor = create_blood_pressure_sensor_from_config(BP_CONFIG)
    
    if not sensor:
        log.error("Failed to create BloodPressureSensor!")
        print("\n❌ Sensor creation failed. Check logs.\n")
        return
    
    print(f"\n✓ Sensor created: {sensor.name}")
    print(f"  Inflate target: {sensor.inflate_target:.0f} mmHg")
    print(f"  Deflate rate:   {sensor.deflate_rate:.1f} mmHg/s")
    print(f"  Max pressure:   {sensor.max_pressure:.0f} mmHg")
    
    try:
        # ========== START SENSOR ==========
        print("\n[1/4] Starting sensor (initializing hardware)...")
        
        if not sensor.start():
            log.error("Failed to start sensor!")
            print("\n❌ Sensor start failed. Check hardware connections.\n")
            return
        
        print("✓ Sensor started (ADC + Pump + Valve ready)")
        time.sleep(1.0)
        
        # ========== START MEASUREMENT ==========
        print("\n[2/4] Starting measurement...")
        print("  (non-blocking mode - runs in background thread)")
        
        if not sensor.start_measurement(callback=on_measurement_complete):
            log.error("Failed to start measurement!")
            print("\n❌ Measurement start failed.\n")
            return
        
        print("✓ Measurement started")
        
        # ========== MONITOR PROGRESS ==========
        print("\n[3/4] Monitoring progress...")
        print("  (Press Ctrl+C to abort)\n")
        
        last_state = None
        
        while True:
            current_state = sensor.get_state()
            
            # Hiển thị state changes
            if current_state != last_state:
                timestamp = time.strftime("%H:%M:%S")
                
                if current_state == BPState.INITIALIZING:
                    print(f"[{timestamp}] 🔧 Initializing: Checking cuff deflation...")
                elif current_state == BPState.INFLATING:
                    print(f"[{timestamp}] ⬆️  Inflating: Pumping to {sensor.inflate_target:.0f} mmHg...")
                elif current_state == BPState.DEFLATING:
                    print(f"[{timestamp}] ⬇️  Deflating: Passive deflation (~2-3 mmHg/s)...")
                elif current_state == BPState.ANALYZING:
                    print(f"[{timestamp}] 🔬 Analyzing: Processing signal (Butterworth + Hilbert)...")
                elif current_state == BPState.COMPLETED:
                    print(f"[{timestamp}] ✅ Completed: Measurement successful!")
                elif current_state == BPState.ERROR:
                    print(f"[{timestamp}] ❌ Error: Measurement failed!")
                elif current_state == BPState.IDLE:
                    print(f"[{timestamp}] 💤 Idle: Waiting for next command...")
                    break  # Exit loop
                
                last_state = current_state
            
            # Check if completed or error
            if current_state in [BPState.COMPLETED, BPState.ERROR]:
                time.sleep(2.0)  # Wait for cleanup
                if sensor.get_state() == BPState.IDLE:
                    break
            
            time.sleep(0.5)
        
        # ========== GET RESULT ==========
        print("\n[4/4] Retrieving result...")
        
        result = sensor.get_last_measurement()
        
        if result:
            print("✓ Result retrieved successfully")
            # Note: Callback đã hiển thị kết quả rồi
        else:
            print("❌ No measurement result available")
            log.error("Measurement failed - no result")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Measurement interrupted by user!")
        log.info("User requested abort")
        
        # Emergency stop
        print("  Executing emergency deflate...")
        sensor.stop_measurement(emergency=True)
        time.sleep(2.0)
        
    except Exception as e:
        log.error(f"Measurement error: {e}", exc_info=True)
        print(f"\n❌ Error: {e}\n")
        sensor.stop_measurement(emergency=True)
        
    finally:
        # ========== CLEANUP ==========
        print("\nCleaning up...")
        
        # Stop sensor
        sensor.stop()
        time.sleep(0.5)
        
        print("✓ Cleanup complete\n")


# ============================================================================
# ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print("BLOOD PRESSURE MEASUREMENT SYSTEM")
    print("="*60)
    print("\nFeatures:")
    print("  ✓ Passive deflation (no PWM)")
    print("  ✓ Professional signal processing (Butterworth + Hilbert)")
    print("  ✓ Safety monitoring (leak detection, limits, timeout)")
    print("  ✓ AAMI validation")
    print("  ✓ Quality assessment (SNR-based)")
    print("\nPress Ctrl+C anytime to abort safely.\n")
    
    try:
        input("Press ENTER to start measurement...")
        measure_blood_pressure()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Cancelled by user\n")
