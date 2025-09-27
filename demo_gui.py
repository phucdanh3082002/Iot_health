#!/usr/bin/env python3
"""
GUI Demo Script
Script demo để test giao diện GUI cho hệ thống IoT Health Monitoring
"""

import sys
import os
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import GUI components
from src.gui.main_app import HealthMonitorApp

# Mock sensor classes for demo
class MockSensor:
    """Mock sensor class for demo purposes"""
    
    def __init__(self, name: str):
        self.name = name
        self.enabled = True
        self.data_callback = None
        self.logger = logging.getLogger(f"MockSensor_{name}")
    
    def set_data_callback(self, callback):
        """Set data callback"""
        self.data_callback = callback
        self.logger.info(f"Data callback set for {self.name}")
    
    def start(self):
        """Start sensor (mock)"""
        self.logger.info(f"Mock {self.name} sensor started")
        return True
    
    def stop(self):
        """Stop sensor (mock)"""
        self.logger.info(f"Mock {self.name} sensor stopped")
        return True


def create_mock_sensors():
    """Create mock sensors for demo"""
    return {
        'MAX30102': MockSensor('MAX30102'),
        'MLX90614': MockSensor('MLX90614'),
        'BloodPressure': MockSensor('BloodPressure')
    }


def create_demo_config():
    """Create demo configuration"""
    return {
        'app': {
            'name': 'IoT Health Monitor Demo',
            'version': '1.0.0',
            'debug': True
        },
        'patient': {
            'id': 'demo_patient',
            'name': 'Bệnh nhân Demo',
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
        },
        'display': {
            'width': 480,
            'height': 320,
            'fullscreen': False
        }
    }


def setup_logging():
    """Setup logging for demo"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def main():
    """Main demo function"""
    print("=== IoT Health Monitor GUI Demo ===")
    print("Starting GUI demo...")
    
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # Create demo configuration
        config = create_demo_config()
        
        # Create mock sensors
        sensors = create_mock_sensors()
        
        # Create and run the app
        app = HealthMonitorApp(
            config=config,
            sensors=sensors,
            database=None,  # No database for demo
            mqtt_client=None,  # No MQTT for demo
            alert_system=None  # No alert system for demo
        )
        
        logger.info("Starting Kivy app...")
        app.run()
        
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
    except Exception as e:
        logger.error(f"Error running demo: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logger.info("Demo finished")


if __name__ == '__main__':
    main()