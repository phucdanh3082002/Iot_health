#!/usr/bin/env python3
"""
IoT Health Monitoring System - Main Application
Entry point cho hệ thống giám sát sức khỏe IoT

Features:
- MQTT real-time data publishing (vitals/alerts/status)
- Cloud sync to MySQL (batch every 5 mins)
- Multi-sensor support (MAX30102, MLX90614, HX710B)
- Kivy GUI (480x320 touchscreen)
- TTS alerts (PiperTTS)
- Store-and-forward for offline resilience

Author: IoT Health Team
Version: 2.0.0
"""

import sys
import os
import signal
import logging
import yaml
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Add src directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.utils.logger import setup_logger
from src.gui.main_app import HealthMonitorApp
from src.data.database import DatabaseManager
from src.communication.mqtt_client import IoTHealthMQTTClient
from src.communication.cloud_sync_manager import CloudSyncManager
from src.sensors.max30102_sensor import MAX30102Sensor
from src.sensors.mlx90614_sensor import MLX90614Sensor
from src.sensors.blood_pressure_sensor import BloodPressureSensor
from src.ai.alert_system import AlertSystem
from src.utils.tts_manager import TTSManager, ScenarioID


class HealthMonitorSystem:
    """
    Main system controller for IoT Health Monitoring
    
    Architecture:
    - Sensors: MAX30102 (HR/SpO2), MLX90614 (Temp), BloodPressure (HX710B)
    - Database: SQLite local + MySQL cloud (auto-sync)
    - Communication: MQTT (real-time) + REST API (historical)
    - GUI: Kivy/KivyMD (480x320)
    - TTS: PiperTTS for Vietnamese audio feedback
    """
    
    def __init__(self):
        """Initialize system components"""
        self.logger: Optional[logging.Logger] = None
        self.config: Dict[str, Any] = {}
        self.database: Optional[DatabaseManager] = None
        self.mqtt_client: Optional[IoTHealthMQTTClient] = None
        self.cloud_sync: Optional[CloudSyncManager] = None
        self.sensors: Dict[str, Any] = {}
        self.alert_system: Optional[AlertSystem] = None
        self.tts_manager: Optional[TTSManager] = None
        self.gui_app: Optional[HealthMonitorApp] = None
        self.running: bool = False
        
        # Device & patient info (from config)
        self.device_id: str = ""
        self.patient_id: str = ""
    
    # ═══════════════════════════════════════════════════════════════════
    # INITIALIZATION
    # ═══════════════════════════════════════════════════════════════════
    
    def load_config(self) -> bool:
        """
        Load configuration from app_config.yaml
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            config_path = project_root / "config" / "app_config.yaml"
            
            if not config_path.exists():
                print(f"❌ Configuration file not found: {config_path}")
                return False
            
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            
            # Extract device info (device-centric approach)
            mqtt_config = self.config.get('communication', {}).get('mqtt', {})
            cloud_config = self.config.get('cloud', {}).get('device', {})
            self.device_id = cloud_config.get('device_id') or mqtt_config.get('device_id', 'rpi_bp_001')
            # patient_id is resolved from cloud database, not from config
            self.patient_id = None  # Will be resolved from cloud based on device_id
            
            print(f"✅ Configuration loaded: {config_path}")
            print(f"   Device ID: {self.device_id}")
            print(f"   Patient ID: (resolved from cloud database)")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to load configuration: {e}")
            return False
    
    def initialize(self) -> bool:
        """
        Initialize all system components
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            print("\n" + "="*70)
            print("🚀 IoT Health Monitoring System - Initialization")
            print("="*70)
            
            # 1. Load configuration
            if not self.load_config():
                return False
            
            # 2. Setup logging
            log_level = self.config.get('app', {}).get('log_level', 'INFO')
            self.logger = setup_logger(
                name="health_monitor",
                config_path=str(project_root / "config" / "app_config.yaml"),
                log_level=log_level
            )
            self.logger.info("="*70)
            self.logger.info("Starting IoT Health Monitoring System v2.0.0")
            self.logger.info("="*70)
            
            # 3. Initialize database (SQLite local)
            self.logger.info("📦 Initializing local database...")
            self.database = DatabaseManager(self.config)
            
            # Initialize tables and cloud sync
            if not self.database.initialize():
                self.logger.error("❌ Database initialization failed")
                return False
            
            self.logger.info("✅ Local database initialized")
            
            # 4. Initialize MQTT client
            self.logger.info("📡 Initializing MQTT client...")
            self.mqtt_client = IoTHealthMQTTClient(config=self.config)
            self.logger.info("✅ MQTT client initialized")
            
            # 5. Initialize TTS manager
            if self.config.get('audio', {}).get('voice_enabled', True):
                self.logger.info("🔊 Initializing TTS manager...")
                try:
                    audio_config = self.config.get('audio', {})
                    piper_config = audio_config.get('piper', {})
                    
                    self.tts_manager = TTSManager.create_default(
                        model_path=Path(piper_config.get('model_path', '/home/pi/piper_models/vi_VN-vais1000-medium.onnx')),
                        config_path=Path(piper_config.get('config_path', '/home/pi/piper_models/vi_VN-vais1000-medium.onnx.json')),
                        speaker=piper_config.get('speaker', ''),
                        default_locale=audio_config.get('locale', 'vi'),
                        default_volume=audio_config.get('volume', 80),
                        cache_dir=Path(piper_config.get('assets_dir', 'asset/tts')),
                        strict_assets=piper_config.get('strict_assets', True)
                    )
                    self.logger.info("✅ TTS manager initialized (PiperTTS)")
                except Exception as e:
                    self.logger.warning(f"⚠️  TTS initialization failed: {e}")
                    self.tts_manager = None
            
            # 6. Initialize sensors (KHÔNG auto-start, chờ user bấm nút)
            self.logger.info("🔬 Initializing sensors...")
            self._initialize_sensors()
            
            # 7. Initialize alert system
            self.logger.info("🚨 Initializing alert system...")
            self.alert_system = AlertSystem(
                config=self.config,
                mqtt_client=self.mqtt_client
            )
            self.logger.info("✅ Alert system initialized")
            
            # 8. Initialize GUI
            self.logger.info("🖥️  Initializing GUI application...")
            self.gui_app = HealthMonitorApp(
                config=self.config,
                sensors=self.sensors,
                database=self.database,
                mqtt_client=self.mqtt_client,
                alert_system=self.alert_system
            )
            self.logger.info("✅ GUI application initialized")
            
            self.logger.info("="*70)
            self.logger.info("✅ System initialization completed successfully")
            self.logger.info("="*70)
            
            return True
            
        except Exception as e:
            error_msg = f"❌ System initialization failed: {e}"
            if self.logger:
                self.logger.error(error_msg, exc_info=True)
            else:
                print(error_msg)
            return False
    
    def _initialize_sensors(self):
        """
        Initialize all enabled sensors
        
        Note: Sensors are initialized but NOT started automatically.
        They will be started when user presses measurement button in GUI.
        """
        sensor_config = self.config.get('sensors', {})
        
        # Initialize MAX30102 (Heart Rate/SpO2)
        if sensor_config.get('max30102', {}).get('enabled', False):
            try:
                self.sensors['max30102'] = MAX30102Sensor(sensor_config['max30102'])
                self.logger.info("   ✅ MAX30102 sensor initialized (HR/SpO2)")
            except Exception as e:
                self.logger.error(f"   ❌ Failed to initialize MAX30102: {e}")
                # KHÔNG tiếp tục nếu sensor fail (theo yêu cầu #7)
                raise RuntimeError(f"Critical sensor initialization failed: MAX30102 - {e}")
        
        # Initialize MLX90614 Temperature sensor
        if sensor_config.get('mlx90614', {}).get('enabled', False):
            try:
                self.sensors['mlx90614'] = MLX90614Sensor(sensor_config['mlx90614'])
                self.logger.info("   ✅ MLX90614 temperature sensor initialized")
            except Exception as e:
                self.logger.error(f"   ❌ Failed to initialize MLX90614: {e}")
                raise RuntimeError(f"Critical sensor initialization failed: MLX90614 - {e}")
        
        # Initialize Blood Pressure sensor (HX710B)
        if sensor_config.get('blood_pressure', {}).get('enabled', False):
            try:
                self.sensors['blood_pressure'] = BloodPressureSensor(
                    name='BloodPressure',
                    config=sensor_config['blood_pressure']
                )
                self.logger.info("   ✅ Blood Pressure sensor initialized (HX710B)")
            except Exception as e:
                self.logger.error(f"   ❌ Failed to initialize Blood Pressure sensor: {e}")
                raise RuntimeError(f"Critical sensor initialization failed: BloodPressure - {e}")
        
        if not self.sensors:
            raise RuntimeError("No sensors initialized - system cannot function")
    
    # ═══════════════════════════════════════════════════════════════════
    # START & LIFECYCLE
    # ═══════════════════════════════════════════════════════════════════
    
    def start(self) -> bool:
        """
        Start the health monitoring system
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.initialize():
            return False
        
        try:
            self.running = True
            self.logger.info("\n" + "="*70)
            self.logger.info("▶️  Starting health monitoring system...")
            self.logger.info("="*70)
            
            # 1. Connect MQTT client
            try:
                self.logger.info("📡 Connecting to MQTT broker...")
                self.mqtt_client.connect()
                self.logger.info("✅ MQTT connected")
                
                # Publish initial status (online)
                from src.communication.mqtt_payloads import DeviceStatusPayload
                status_payload = DeviceStatusPayload(
                    timestamp=time.time(),
                    device_id=self.mqtt_client.device_id,
                    online=True,
                    battery={'level': 100, 'charging': False},
                    sensors={'max30102': 'ready', 'mlx90614': 'ready', 'hx710b': 'ready'},
                    actuators={'pump': 'idle', 'valve': 'closed'},
                    system={'uptime': 0, 'memory_usage': 50.0},
                    network={'wifi_signal': -50, 'mqtt_connected': True}
                )
                self.mqtt_client.publish_status(status_payload)
                
            except Exception as e:
                self.logger.warning(f"⚠️  MQTT connection failed: {e}")
                self.logger.info("   System will continue without MQTT")
            
            # 2. Start alert system
            try:
                self.alert_system.start()
                self.logger.info("✅ Alert system started")
            except Exception as e:
                self.logger.error(f"❌ Alert system failed to start: {e}")
            
            # 3. Play startup voice notification
            if self.tts_manager:
                try:
                    self.tts_manager.speak_scenario(ScenarioID.SYSTEM_START)
                except Exception as e:
                    self.logger.warning(f"⚠️  TTS startup message failed: {e}")
            
            self.logger.info("="*70)
            self.logger.info("✅ System started successfully")
            self.logger.info("🖥️  Launching GUI application...")
            self.logger.info("="*70)
            
            # 4. Start GUI (this will block until GUI closes)
            self.gui_app.run()
            
            self.logger.info("GUI application closed")
            
        except KeyboardInterrupt:
            self.logger.info("⚠️  Received keyboard interrupt (Ctrl+C)")
        except Exception as e:
            self.logger.error(f"❌ System error: {e}", exc_info=True)
            return False
        finally:
            self.shutdown()
        
        return True
    
    def shutdown(self):
        """
        Gracefully shutdown the system
        
        Cleanup order:
        1. Stop sensors
        2. Stop alert system
        3. Publish offline status to MQTT
        4. Disconnect MQTT
        5. Stop cloud sync scheduler
        6. Close database
        7. Stop TTS manager
        """
        if not self.running:
            return
        
        self.logger.info("\n" + "="*70)
        self.logger.info("⏹️  Shutting down health monitoring system...")
        self.logger.info("="*70)
        
        self.running = False
        
        # 1. Stop sensors
        for sensor_name, sensor in self.sensors.items():
            try:
                if hasattr(sensor, 'stop'):
                    sensor.stop()
                self.logger.info(f"✅ Stopped {sensor_name} sensor")
            except Exception as e:
                self.logger.error(f"❌ Error stopping {sensor_name}: {e}")
        
        # 2. Stop alert system
        if self.alert_system:
            try:
                self.alert_system.stop()
                self.logger.info("✅ Alert system stopped")
            except Exception as e:
                self.logger.error(f"❌ Error stopping alert system: {e}")
        
        # 3. Publish offline status to MQTT
        if self.mqtt_client and self.mqtt_client.is_connected:
            try:
                from src.communication.mqtt_payloads import DeviceStatusPayload
                status_payload = DeviceStatusPayload(
                    timestamp=time.time(),
                    device_id=self.mqtt_client.device_id,
                    online=False,
                    battery={'level': 0, 'charging': False},
                    sensors={'max30102': 'offline', 'mlx90614': 'offline', 'hx710b': 'offline'},
                    actuators={'pump': 'idle', 'valve': 'closed'},
                    system={'uptime': 0, 'memory_usage': 0.0},
                    network={'wifi_signal': 0, 'mqtt_connected': False}
                )
                self.mqtt_client.publish_status(status_payload)
                self.logger.info("✅ Published offline status to MQTT")
            except Exception as e:
                self.logger.error(f"❌ Error publishing offline status: {e}")
        
        # 4. Disconnect MQTT
        if self.mqtt_client:
            try:
                self.mqtt_client.disconnect()
                self.logger.info("✅ MQTT disconnected")
            except Exception as e:
                self.logger.error(f"❌ Error disconnecting MQTT: {e}")
        
        # 5. Stop cloud sync scheduler
        if self.database and hasattr(self.database, 'stop_auto_sync'):
            try:
                self.database.stop_auto_sync()
                self.logger.info("✅ Cloud sync scheduler stopped")
            except Exception as e:
                self.logger.error(f"❌ Error stopping sync scheduler: {e}")
        
        # 6. Close database
        if self.database:
            try:
                self.database.close()
                self.logger.info("✅ Database closed")
            except Exception as e:
                self.logger.error(f"❌ Error closing database: {e}")
        
        # 7. Stop TTS manager
        if self.tts_manager:
            try:
                self.tts_manager.stop()
                self.logger.info("✅ TTS manager stopped")
            except Exception as e:
                self.logger.error(f"❌ Error stopping TTS: {e}")
        
        self.logger.info("="*70)
        self.logger.info("✅ System shutdown completed")
        self.logger.info(f"📅 Shutdown time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("="*70)
    
    def signal_handler(self, signum, frame):
        """
        Handle system signals for graceful shutdown
        
        Args:
            signum: Signal number
            frame: Current stack frame
        """
        signal_names = {
            signal.SIGINT: "SIGINT (Ctrl+C)",
            signal.SIGTERM: "SIGTERM"
        }
        signal_name = signal_names.get(signum, f"Signal {signum}")
        
        self.logger.info(f"⚠️  Received {signal_name}")
        self.shutdown()
        sys.exit(0)


# ═══════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

def main():
    """
    Main entry point for IoT Health Monitoring System
    
    Usage:
        python main.py
        
    Environment Variables:
        MQTT_PASSWORD: HiveMQ Cloud password (required)
        MYSQL_CLOUD_PASSWORD: MySQL cloud password (required if cloud sync enabled)
    """
    # Print banner
    print("\n" + "="*70)
    print("   IoT Health Monitoring System v2.0.0")
    print("   Raspberry Pi Blood Pressure Monitor with Cloud Integration")
    print("="*70)
    print(f"   Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70 + "\n")
    
    # Create system instance
    health_system = HealthMonitorSystem()
    
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, health_system.signal_handler)
    signal.signal(signal.SIGTERM, health_system.signal_handler)
    
    # Start the system
    try:
        success = health_system.start()
        exit_code = 0 if success else 1
        
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: Failed to start health monitoring system")
        print(f"   Error: {e}")
        print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70 + "\n")
        exit_code = 1
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
