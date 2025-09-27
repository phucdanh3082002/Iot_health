#!/usr/bin/env python3
"""
Enhanced GUI Demo
Demo cho giao diện GUI cải tiến với 3 khối cảm biến chính
"""

import sys
import os
import logging
import time
import random
from pathlib import Path
from threading import Thread

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure Kivy before importing
from kivy.config import Config
Config.set('graphics', 'width', '480')
Config.set('graphics', 'height', '320')
Config.set('graphics', 'resizable', True)  # Allow resizing for desktop testing
Config.set('graphics', 'fullscreen', False)
Config.set('graphics', 'show_cursor', True)

from kivy.clock import Clock
from src.gui.main_app import HealthMonitorApp


class MockSensor:
    """Enhanced mock sensor with realistic data simulation"""
    
    def __init__(self, name: str):
        self.name = name
        self.enabled = True
        self.data_callback = None
        self.logger = logging.getLogger(f"MockSensor_{name}")
        self.running = False
        self.thread = None
        
        # Sensor-specific properties
        if name == 'MAX30102':
            self.base_hr = random.randint(65, 85)
            self.base_spo2 = random.randint(96, 99)
            self.finger_detected = False
        elif name == 'MLX90614':
            self.base_temp = 36.0 + random.random() * 1.5
        elif name == 'BloodPressure':
            self.base_systolic = random.randint(110, 130)
            self.base_diastolic = random.randint(70, 85)
    
    def set_data_callback(self, callback):
        """Set data callback"""
        self.data_callback = callback
        self.logger.info(f"Data callback set for {self.name}")
    
    def start(self):
        """Start sensor simulation"""
        self.logger.info(f"Mock {self.name} sensor started")
        self.running = True
        
        if self.name in ['MAX30102', 'MLX90614']:
            self.thread = Thread(target=self._simulate_data, daemon=True)
            self.thread.start()
        
        return True
    
    def stop(self):
        """Stop sensor simulation"""
        self.logger.info(f"Mock {self.name} sensor stopped")
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
        return True
    
    def _simulate_data(self):
        """Simulate realistic sensor data"""
        while self.running:
            try:
                if self.name == 'MAX30102':
                    self._simulate_max30102_data()
                elif self.name == 'MLX90614':
                    self._simulate_temperature_data()
                    
                time.sleep(0.5)  # Update every 500ms
                
            except Exception as e:
                self.logger.error(f"Error simulating data: {e}")
    
    def _simulate_max30102_data(self):
        """Simulate MAX30102 heart rate and SpO2 data"""
        # Simulate finger detection (randomly place/remove finger)
        if random.random() < 0.05:  # 5% chance to change finger state
            self.finger_detected = not self.finger_detected
        
        if self.finger_detected:
            # Add some realistic variation
            hr_variation = random.randint(-5, 5)
            spo2_variation = random.randint(-2, 2)
            
            hr = max(50, min(150, self.base_hr + hr_variation))
            spo2 = max(90, min(100, self.base_spo2 + spo2_variation))
            
            # Simulate signal quality
            signal_quality = random.randint(70, 95)
            
            data = {
                'heart_rate': hr,
                'spo2': spo2,
                'finger_detected': True,
                'hr_valid': True,
                'spo2_valid': True,
                'signal_quality_ir': signal_quality,
                'status': 'good',
                'timestamp': time.time()
            }
        else:
            data = {
                'heart_rate': 0,
                'spo2': 0,
                'finger_detected': False,
                'hr_valid': False,
                'spo2_valid': False,
                'signal_quality_ir': 0,
                'status': 'no_finger',
                'timestamp': time.time()
            }
        
        if self.data_callback:
            # Schedule callback on main thread
            Clock.schedule_once(lambda dt: self.data_callback(self.name, data), 0)
    
    def _simulate_temperature_data(self):
        """Simulate MLX90614 temperature data"""
        # Add small random variation
        temp_variation = (random.random() - 0.5) * 0.5  # ±0.25°C
        temp = self.base_temp + temp_variation
        
        # Simulate ambient temperature
        ambient_temp = 22.0 + random.random() * 6  # 22-28°C
        
        data = {
            'temperature': round(temp, 1),
            'ambient_temperature': round(ambient_temp, 1),
            'object_temperature': round(temp, 1),
            'status': 'normal',
            'measurement_type': 'object',
            'timestamp': time.time()
        }
        
        if self.data_callback:
            Clock.schedule_once(lambda dt: self.data_callback(self.name, data), 0)


def create_demo_config():
    """Create demo configuration"""
    return {
        'app': {
            'name': 'IoT Health Monitor - Enhanced Demo',
            'version': '2.0.0',
            'debug': True
        },
        'patient': {
            'id': 'demo_patient',
            'name': 'Bệnh nhân Demo',
            'age': 65,
            'gender': 'M'
        },
        'sensors': {
            'max30102': {
                'enabled': True,
                'sample_rate': 50,
                'led_mode': 3
            },
            'mlx90614': {
                'enabled': True,
                'sample_rate': 0.5,
                'use_object_temp': True
            },
            'blood_pressure': {
                'enabled': True,
                'max_pressure': 180
            }
        },
        'display': {
            'width': 480,
            'height': 320,
            'fullscreen': False,
            'theme': 'dark'
        }
    }


def setup_logging():
    """Setup logging for demo"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('demo_gui.log')
        ]
    )


def main():
    """Main demo function"""
    print("=== IoT Health Monitor - Enhanced GUI Demo ===")
    print("Khởi động giao diện demo với 3 khối cảm biến...")
    
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # Create demo configuration
        config = create_demo_config()
        
        # Create mock sensors
        sensors = {
            'MAX30102': MockSensor('MAX30102'),
            'MLX90614': MockSensor('MLX90614'),
            'BloodPressure': MockSensor('BloodPressure')
        }
        
        # Create and run the app
        app = HealthMonitorApp(
            config=config,
            sensors=sensors,
            database=None,
            mqtt_client=None,
            alert_system=None
        )
        
        logger.info("Starting Enhanced Kivy app...")
        print("✓ Đã tạo cấu hình demo")
        print("✓ Đã tạo mock sensors")
        print("✓ Khởi tạo ứng dụng Kivy")
        print("\nChức năng demo:")
        print("• Dashboard với 3 khối cảm biến lớn")
        print("• Nhấn vào khối cảm biến để đo chi tiết")
        print("• MAX30102: Nhịp tim & SpO2 với animation")
        print("• MLX90614: Nhiệt độ với gauge display")
        print("• Huyết áp: Quy trình đo tự động")
        print("• Lịch sử và cài đặt đầy đủ")
        print("\nẤn Ctrl+C để thoát")
        
        app.run()
        
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
        print("\n✓ Demo đã được dừng bởi người dùng")
    except Exception as e:
        logger.error(f"Error running demo: {e}")
        print(f"\n✗ Lỗi chạy demo: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Stop all sensors
        try:
            for sensor in sensors.values():
                sensor.stop()
        except:
            pass
        logger.info("Demo finished")
        print("✓ Demo kết thúc")


if __name__ == '__main__':
    main()