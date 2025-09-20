#!/usr/bin/env python3
"""
IoT Health Monitoring System
Main application entry point

Author: IoT Health Team
Version: 1.0.0
"""

import sys
import os
import signal
import logging
from pathlib import Path

# Add src directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from src.utils.logger import setup_logger
from src.utils.config_loader import ConfigLoader
from src.gui.main_app import HealthMonitorApp
from src.data.database import DatabaseManager
from src.communication.mqtt_client import MQTTClient
from src.sensors.max30102_sensor import MAX30102Sensor
from src.sensors.mlx90614_sensor import MLX90614Sensor
from src.sensors.blood_pressure_sensor import BloodPressureSensor
from src.ai.alert_system import AlertSystem


class HealthMonitorSystem:
    """Main system controller for IoT Health Monitoring"""
    
    def __init__(self):
        self.logger = None
        self.config = None
        self.database = None
        self.mqtt_client = None
        self.sensors = {}
        self.alert_system = None
        self.gui_app = None
        self.running = False
        
    def initialize(self):
        """Initialize all system components"""
        try:
            # Setup logging
            self.logger = setup_logger()
            self.logger.info("Starting IoT Health Monitoring System...")
            
            # Load configuration
            self.config = ConfigLoader()
            self.logger.info("Configuration loaded successfully")
            
            # Initialize database
            self.database = DatabaseManager(self.config)
            self.database.initialize()
            self.logger.info("Database initialized")
            
            # Initialize MQTT client
            self.mqtt_client = MQTTClient(self.config)
            
            # Initialize sensors
            self._initialize_sensors()
            
            # Initialize alert system
            self.alert_system = AlertSystem(self.config, self.mqtt_client)
            
            # Initialize GUI
            self.gui_app = HealthMonitorApp(
                config=self.config,
                sensors=self.sensors,
                database=self.database,
                mqtt_client=self.mqtt_client,
                alert_system=self.alert_system
            )
            
            self.logger.info("System initialization completed successfully")
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"System initialization failed: {e}")
            else:
                print(f"System initialization failed: {e}")
            return False
    
    def _initialize_sensors(self):
        """Initialize all enabled sensors"""
        sensor_config = self.config.get('sensors', {})
        
        # Initialize MAX30102 (Heart Rate/SpO2)
        if sensor_config.get('max30102', {}).get('enabled', False):
            try:
                self.sensors['max30102'] = MAX30102Sensor(sensor_config['max30102'])
                self.logger.info("MAX30102 sensor initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize MAX30102: {e}")
        
        # Initialize MLX90614 Temperature sensor
        if sensor_config.get('mlx90614', {}).get('enabled', False):
            try:
                self.sensors['mlx90614'] = MLX90614Sensor(sensor_config['mlx90614'])
                self.logger.info("MLX90614 temperature sensor initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize MLX90614 sensor: {e}")
        
        # Initialize Blood Pressure sensor
        if sensor_config.get('blood_pressure', {}).get('enabled', False):
            try:
                self.sensors['blood_pressure'] = BloodPressureSensor(sensor_config['blood_pressure'])
                self.logger.info("Blood Pressure sensor initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize Blood Pressure sensor: {e}")
    
    def start(self):
        """Start the health monitoring system"""
        if not self.initialize():
            return False
            
        try:
            self.running = True
            self.logger.info("Starting health monitoring system...")
            
            # Connect MQTT client
            self.mqtt_client.connect()
            
            # Start sensors
            for sensor_name, sensor in self.sensors.items():
                sensor.start()
                self.logger.info(f"Started {sensor_name} sensor")
            
            # Start alert system
            self.alert_system.start()
            
            # Start GUI (this will block)
            self.gui_app.run()
            
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal")
        except Exception as e:
            self.logger.error(f"System error: {e}")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Gracefully shutdown the system"""
        self.logger.info("Shutting down health monitoring system...")
        self.running = False
        
        # Stop sensors
        for sensor_name, sensor in self.sensors.items():
            try:
                sensor.stop()
                self.logger.info(f"Stopped {sensor_name} sensor")
            except Exception as e:
                self.logger.error(f"Error stopping {sensor_name}: {e}")
        
        # Stop alert system
        if self.alert_system:
            self.alert_system.stop()
        
        # Disconnect MQTT
        if self.mqtt_client:
            self.mqtt_client.disconnect()
        
        # Close database
        if self.database:
            self.database.close()
        
        self.logger.info("System shutdown completed")

    def signal_handler(self, signum, frame):
        """Handle system signals for graceful shutdown"""
        self.logger.info(f"Received signal {signum}")
        self.shutdown()
        sys.exit(0)


def main():
    """Main entry point"""
    # Create system instance
    health_system = HealthMonitorSystem()
    
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, health_system.signal_handler)
    signal.signal(signal.SIGTERM, health_system.signal_handler)
    
    # Start the system
    try:
        health_system.start()
    except Exception as e:
        print(f"Failed to start health monitoring system: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
