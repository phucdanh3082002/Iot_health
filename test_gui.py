#!/usr/bin/env python3
"""
Test GUI Application
Chương trình test GUI với dữ liệu mô phỏng từ sensor logic
"""

import sys
import time
import threading
import random
from pathlib import Path
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import GUI components
from src.gui.main_app import HealthMonitorApp
from src.sensors.max30102_sensor import MAX30102Sensor
from src.sensors.mlx90614_sensor import MLX90614Sensor

# Import config
import yaml


class MockSensor:
    """Mock sensor for testing"""
    
    def __init__(self, name: str):
        self.name = name
        self.is_running = False
        self.data_callback = None
        
        # MAX30102 specific attributes
        if name == "MAX30102":
            self.heart_rate = 0.0
            self.spo2 = 0.0
            self.hr_valid = False
            self.spo2_valid = False
            self.finger_detected = False
            self.signal_quality_ir = 0.0
            self.signal_quality_red = 0.0
            self.readings_count = 0
            self.ir_buffer = []
            
        # MLX90614 specific attributes
        elif name == "MLX90614":
            self.object_temperature = 36.5
            self.ambient_temperature = 25.0
            self.use_object_temp = True
            self.temperature_offset = 0.0
            self.smooth_factor = 0.1
    
    def initialize(self) -> bool:
        """Initialize mock sensor"""
        print(f"Mock {self.name} initialized")
        return True
    
    def start(self) -> bool:
        """Start mock sensor"""
        self.is_running = True
        print(f"Mock {self.name} started")
        
        # Start simulation thread
        if self.name == "MAX30102":
            threading.Thread(target=self._simulate_max30102, daemon=True).start()
        elif self.name == "MLX90614":
            threading.Thread(target=self._simulate_mlx90614, daemon=True).start()
        
        return True
    
    def stop(self) -> bool:
        """Stop mock sensor"""
        self.is_running = False
        print(f"Mock {self.name} stopped")
        return True
    
    def set_data_callback(self, callback):
        """Set data callback"""
        self.data_callback = callback
        print(f"Mock {self.name} callback set")
    
    def _simulate_max30102(self):
        """Simulate MAX30102 data"""
        finger_on = False
        finger_timer = 0
        
        while self.is_running:
            try:
                # Simulate finger on/off
                finger_timer += 1
                if finger_timer > 20:  # Change finger status every 20 seconds
                    finger_on = not finger_on
                    finger_timer = 0
                
                self.finger_detected = finger_on
                
                if finger_on:
                    # Simulate realistic HR and SpO2
                    base_hr = 75 + random.uniform(-5, 5)
                    base_spo2 = 98 + random.uniform(-2, 2)
                    
                    self.heart_rate = max(60, min(100, base_hr))
                    self.spo2 = max(95, min(100, base_spo2))
                    self.hr_valid = True
                    self.spo2_valid = True
                    self.signal_quality_ir = random.uniform(70, 95)
                    self.signal_quality_red = random.uniform(70, 95)
                    self.readings_count += 1
                else:
                    # No finger detected
                    self.heart_rate = 0.0
                    self.spo2 = 0.0
                    self.hr_valid = False
                    self.spo2_valid = False
                    self.signal_quality_ir = 0.0
                    self.signal_quality_red = 0.0
                
                # Call callback if set
                if self.data_callback:
                    data = {
                        'heart_rate': self.heart_rate,
                        'spo2': self.spo2,
                        'hr_valid': self.hr_valid,
                        'spo2_valid': self.spo2_valid,
                        'finger_detected': self.finger_detected,
                        'signal_quality_ir': self.signal_quality_ir,
                        'signal_quality_red': self.signal_quality_red,
                        'timestamp': time.time()
                    }
                    self.data_callback("MAX30102", data)
                
                time.sleep(1)
                
            except Exception as e:
                print(f"Error in MAX30102 simulation: {e}")
                break
    
    def _simulate_mlx90614(self):
        """Simulate MLX90614 data"""
        while self.is_running:
            try:
                # Simulate realistic temperature variations
                base_temp = 36.5 + random.uniform(-0.5, 0.5)
                ambient_temp = 25.0 + random.uniform(-2, 2)
                
                self.object_temperature = base_temp
                self.ambient_temperature = ambient_temp
                
                # Call callback if set
                if self.data_callback:
                    data = {
                        'temperature': self.object_temperature,
                        'object_temperature': self.object_temperature,
                        'ambient_temperature': self.ambient_temperature,
                        'temperature_unit': 'celsius',
                        'status': 'normal',
                        'measurement_type': 'object',
                        'timestamp': time.time()
                    }
                    self.data_callback("MLX90614", data)
                
                time.sleep(2)  # Update every 2 seconds
                
            except Exception as e:
                print(f"Error in MLX90614 simulation: {e}")
                break
    
    def get_heart_rate_status(self) -> str:
        """Get heart rate status for MAX30102"""
        if not self.hr_valid:
            return 'invalid'
        
        hr = self.heart_rate
        if hr < 40:
            return 'critical'
        elif hr < 60:
            return 'low'
        elif hr <= 100:
            return 'normal'
        elif hr <= 150:
            return 'high'
        else:
            return 'critical'
    
    def get_spo2_status(self) -> str:
        """Get SpO2 status for MAX30102"""
        if not self.spo2_valid:
            return 'invalid'
        
        spo2 = self.spo2
        if spo2 < 90:
            return 'critical'
        elif spo2 < 95:
            return 'low'
        else:
            return 'normal'
    
    def get_celsius(self) -> float:
        """Get temperature in Celsius for MLX90614"""
        return self.object_temperature if self.use_object_temp else self.ambient_temperature
    
    def get_fahrenheit(self) -> float:
        """Get temperature in Fahrenheit for MLX90614"""
        celsius = self.get_celsius()
        return (celsius * 9/5) + 32


def load_config() -> Dict[str, Any]:
    """Load application configuration"""
    try:
        config_path = project_root / "config" / "app_config.yaml"
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        print(f"Error loading config: {e}")
        return {
            'app': {'name': 'IoT Health Monitor Test', 'debug': True},
            'patient': {'name': 'Test Patient', 'age': 65}
        }


def main():
    """Main test function"""
    print("🚀 Starting GUI Test with Mock Sensors...")
    
    # Load configuration
    config = load_config()
    
    # Create mock sensors
    sensors = {
        'MAX30102': MockSensor('MAX30102'),
        'MLX90614': MockSensor('MLX90614'),
        'BloodPressure': MockSensor('BloodPressure')
    }
    
    # Initialize and start sensors
    for name, sensor in sensors.items():
        if sensor.initialize():
            sensor.start()
            print(f"✅ {name} mock sensor started")
        else:
            print(f"❌ {name} mock sensor failed to start")
    
    try:
        # Create and run GUI application
        app = HealthMonitorApp(
            config=config,
            sensors=sensors,
            database=None,
            mqtt_client=None,
            alert_system=None
        )
        
        print("🖥️  Starting GUI application...")
        app.run()
        
    except Exception as e:
        print(f"❌ Error running GUI: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Stop all sensors
        for sensor in sensors.values():
            sensor.stop()
        print("👋 GUI test finished")


if __name__ == '__main__':
    main()