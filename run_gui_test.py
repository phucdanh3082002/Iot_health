#!/usr/bin/env python3
"""
GUI Test Runner
Script để test và chạy GUI một cách độc lập
"""

import sys
import os
import logging
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def create_mock_sensors():
    """Create mock sensors for testing"""
    class MockSensor:
        def __init__(self, name):
            self.name = name
            self.enabled = True
            self.data_callback = None
            self.logger = logging.getLogger(f"MockSensor_{name}")
        
        def set_data_callback(self, callback):
            self.data_callback = callback
            self.logger.info(f"Data callback set for {self.name}")
        
        def start(self):
            self.logger.info(f"Mock {self.name} sensor started")
            return True
        
        def stop(self):
            self.logger.info(f"Mock {self.name} sensor stopped")
            return True
    
    return {
        'MAX30102': MockSensor('MAX30102'),
        'MLX90614': MockSensor('MLX90614'),
        'BloodPressure': MockSensor('BloodPressure')
    }

def create_test_config():
    """Create test configuration"""
    return {
        'app': {
            'name': 'IoT Health Monitor Test',
            'version': '1.0.0',
            'debug': True
        },
        'patient': {
            'id': 'test_patient',
            'name': 'Bệnh nhân Test',
            'age': 65
        },
        'sensors': {
            'max30102': {
                'enabled': True,
                'sample_rate': 50
            },
            'mlx90614': {
                'enabled': True,
                'sample_rate': 0.5
            },
            'blood_pressure': {
                'enabled': True
            }
        }
    }

def main():
    """Main function to run GUI test"""
    print("=== IoT Health Monitor GUI Test ===")
    
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # Import GUI components
        from src.gui.main_app import HealthMonitorApp
        
        # Create test configuration and mock sensors
        config = create_test_config()
        sensors = create_mock_sensors()
        
        # Create and run the app
        logger.info("Starting Health Monitor GUI...")
        app = HealthMonitorApp(
            config=config,
            sensors=sensors,
            database=None,
            mqtt_client=None,
            alert_system=None
        )
        
        logger.info("GUI started successfully")
        app.run()
        
    except ImportError as e:
        logger.error(f"Import error: {e}")
        print("Lỗi import. Đảm bảo đã cài đặt Kivy và các dependencies cần thiết.")
        return 1
    except Exception as e:
        logger.error(f"Error running GUI: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        logger.info("GUI test finished")
    
    return 0

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)