"""
Main Kivy Application
Main application class cho IoT Health Monitoring GUI
"""

from typing import Dict, Any, Optional, List
import logging
import sys
import time
from pathlib import Path
from datetime import datetime
from contextlib import closing
import sqlite3
import yaml
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager
from kivy.clock import Clock
from kivy.config import Config

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import sensor classes for direct integration
try:
    # Import sensor logic directly
    from src.sensors.max30102_sensor import MAX30102Sensor
    from src.sensors.mlx90614_sensor import MLX90614Sensor
    from src.sensors.blood_pressure_sensor import BloodPressureSensor
    from src.sensors.base_sensor import BaseSensor
except ImportError as e:
    logging.warning(f"Could not import sensor classes: {e}")
    MAX30102Sensor = None
    MLX90614Sensor = None
    BloodPressureSensor = None
    BaseSensor = None

from src.utils.tts_manager import (
    DEFAULT_PIPER_CONFIG,
    DEFAULT_PIPER_MODEL,
    ScenarioID,
    TTSManager,
)

# Import screens - handle both relative and absolute imports
try:
    # Try relative imports (when run as module)
    from .dashboard_screen import DashboardScreen
    from .heart_rate_screen import HeartRateScreen
    from .temperature_screen import TemperatureScreen
    from .bp_measurement_screen import BPMeasurementScreen
    from .settings_screen import SettingsScreen
    from .history_screen import HistoryScreen
except ImportError:
    # Fall back to absolute imports (when run directly)
    from src.gui.dashboard_screen import DashboardScreen
    from src.gui.heart_rate_screen import HeartRateScreen
    from src.gui.temperature_screen import TemperatureScreen
    from src.gui.bp_measurement_screen import BPMeasurementScreen
    from src.gui.settings_screen import SettingsScreen
    from src.gui.history_screen import HistoryScreen

# Configure for touchscreen
Config.set('graphics', 'width', '480')
Config.set('graphics', 'height', '320')
Config.set('graphics', 'resizable', False)
Config.set('graphics', 'fullscreen', 'auto')
Config.set('graphics', 'show_cursor', False)


class HealthMonitorApp(App):
    """
    Main Kivy application cho IoT Health Monitoring System
    
    Attributes:
        config (Dict): Application configuration
        sensors (Dict): Dictionary of sensor instances
        database: Database manager instance
        mqtt_client: MQTT client instance
        alert_system: Alert system instance
        screen_manager (ScreenManager): Screen manager for navigation
        data_update_event: Clock event for data updates
        current_data (Dict): Latest sensor data
    """
    
    def __init__(self, config: Dict[str, Any], sensors: Dict = None, database=None, 
                 mqtt_client=None, alert_system=None, **kwargs):
        """
        Initialize HealthMonitorApp
        
        Args:
            config: Application configuration
            sensors: Dictionary of sensor instances (optional - will create from config)
            database: Database manager
            mqtt_client: MQTT client
            alert_system: Alert system
        """
        super().__init__(**kwargs)

        # Setup logging early for downstream helper usage
        self.logger = logging.getLogger(__name__)

        self.config_data = config
        self.database = database
        self.mqtt_client = mqtt_client
        self.alert_system = alert_system
        self.audio_config = self.config_data.get('audio', {}) or {}
        
        # Initialize sensors from config or use provided ones
        if sensors is None:
            self.sensors = self._create_sensors_from_config()
        else:
            self.sensors = self._normalize_sensor_keys(sensors)

        self.tts_manager = self._init_tts_manager()
        self._hr_finger_present: Optional[bool] = None
        self._hr_last_announced: Optional[tuple[int, int]] = None
        self._temp_last_status: Optional[str] = None

        # Default sensor status map aligns with available sensors
        default_status = {name: {'status': 'idle'} for name in self.sensors.keys()}
        
        # Current sensor data
        self.current_data = {
            'heart_rate': 0,
            'spo2': 0,
            'temperature': 0,
            'blood_pressure_systolic': 0,
            'blood_pressure_diastolic': 0,
            'sensor_status': default_status,
            'timestamp': None
        }
        
        # Screen manager
        self.screen_manager = None
        self.data_update_event = None

        # Pre-register callbacks for sensors
        self.sensor_callbacks = {
            'MAX30102': self.on_max30102_data,
            'MLX90614': self.on_temperature_data,
            'BloodPressure': self.on_blood_pressure_data,
        }
    
    def _create_sensors_from_config(self) -> Dict[str, Any]:
        """
        Create sensor instances from configuration
        
        Returns:
            Dictionary of sensor instances
        """
        sensors = {}
        
        try:
            sensor_configs = self.config_data.get('sensors', {})
            
            # Create MAX30102 sensor if enabled
            if sensor_configs.get('max30102', {}).get('enabled', False) and MAX30102Sensor:
                try:
                    max30102_config = sensor_configs['max30102']
                    sensor = MAX30102Sensor(max30102_config)
                    if sensor.initialize():
                        sensors['MAX30102'] = sensor
                        self.logger.info("MAX30102 sensor created and initialized")
                    else:
                        self.logger.warning("MAX30102 sensor failed to initialize")
                except Exception as e:
                    self.logger.error(f"Error creating MAX30102 sensor: {e}")
            
            # Create MLX90614 sensor if enabled
            if sensor_configs.get('mlx90614', {}).get('enabled', False) and MLX90614Sensor:
                try:
                    mlx90614_config = sensor_configs['mlx90614']
                    sensor = MLX90614Sensor(mlx90614_config)
                    if sensor.initialize():
                        sensors['MLX90614'] = sensor
                        self.logger.info("MLX90614 sensor created and initialized")
                    else:
                        self.logger.warning("MLX90614 sensor failed to initialize")
                except Exception as e:
                    self.logger.error(f"Error creating MLX90614 sensor: {e}")
            
            # Create Blood Pressure sensor if enabled
            if sensor_configs.get('blood_pressure', {}).get('enabled', False) and BloodPressureSensor:
                try:
                    bp_config = sensor_configs['blood_pressure']
                    sensor = BloodPressureSensor(bp_config)
                    if sensor.initialize():
                        sensors['BloodPressure'] = sensor
                        self.logger.info("BloodPressure sensor created and initialized")
                    else:
                        self.logger.warning("BloodPressure sensor failed to initialize")
                except Exception as e:
                    self.logger.error(f"Error creating BloodPressure sensor: {e}")
            
        except Exception as e:
            self.logger.error(f"Error creating sensors from config: {e}")
        
        return sensors

    @staticmethod
    def _normalize_sensor_keys(sensors: Dict[str, Any]) -> Dict[str, Any]:
        mapping = {
            'max30102': 'MAX30102',
            'mlx90614': 'MLX90614',
            'blood_pressure': 'BloodPressure',
            'bloodpressure': 'BloodPressure',
        }
        normalized: Dict[str, Any] = {}
        for key, sensor in sensors.items():
            if not isinstance(key, str):
                normalized[key] = sensor
                continue
            lookup = mapping.get(key)
            if lookup:
                normalized[lookup] = sensor
            else:
                normalized[key] = sensor
        return normalized

    def _init_tts_manager(self) -> Optional[TTSManager]:
        """Khởi tạo bộ quản lý TTS dựa theo cấu hình."""
        try:
            if not self.audio_config.get('enabled', True):
                return None
            if not self.audio_config.get('voice_enabled', True):
                self.logger.info("Voice alerts disabled in configuration")
                return None

            engine_name = (self.audio_config.get('tts_engine') or 'piper').lower()
            if engine_name != 'piper':
                self.logger.warning("TTS engine '%s' chưa được hỗ trợ, tạm thời bỏ qua.", engine_name)
                return None

            piper_cfg = self.audio_config.get('piper', {}) or {}
            model_path_value = piper_cfg.get('model_path')
            config_path_value = piper_cfg.get('config_path')

            model_path = Path(model_path_value) if model_path_value else DEFAULT_PIPER_MODEL
            config_path = (
                Path(config_path_value)
                if config_path_value
                else DEFAULT_PIPER_CONFIG if DEFAULT_PIPER_CONFIG.exists() else None
            )
            speaker = piper_cfg.get('speaker') or None
            assets_dir_value = piper_cfg.get('assets_dir')
            if assets_dir_value:
                assets_path = Path(assets_dir_value).expanduser()
                if not assets_path.is_absolute():
                    assets_path = (project_root / assets_dir_value).resolve()
            else:
                assets_path = (project_root / "asset" / "tts").resolve()

            strict_assets = bool(piper_cfg.get('strict_assets', False))

            default_locale = self.audio_config.get('locale', 'vi')
            default_volume = int(self.audio_config.get('volume', 100))

            tts = TTSManager.create_default(
                model_path=model_path,
                config_path=config_path,
                speaker=speaker,
                default_locale=default_locale,
                default_volume=default_volume,
                cache_dir=assets_path,
                strict_assets=strict_assets,
            )
            self.logger.info("TTSManager khởi tạo thành công")

            try:
                preload_ids = (
                    ScenarioID.NAVIGATE_DASHBOARD,
                    ScenarioID.HR_PROMPT_FINGER,
                    ScenarioID.HR_NO_FINGER,
                    ScenarioID.HR_MEASURING,
                    ScenarioID.HR_SIGNAL_WEAK,
                    ScenarioID.TEMP_PREP,
                    ScenarioID.TEMP_MEASURING,
                    ScenarioID.TEMP_HIGH_ALERT,
                    ScenarioID.TEMP_RESULT_CRITICAL_LOW,
                    ScenarioID.TEMP_RESULT_LOW,
                    ScenarioID.TEMP_RESULT_NORMAL,
                    ScenarioID.TEMP_RESULT_FEVER,
                    ScenarioID.TEMP_RESULT_HIGH_FEVER,
                    ScenarioID.TEMP_RESULT_CRITICAL_HIGH,
                )
                tts.preload_scenarios(preload_ids)
            except Exception as preload_exc:
                self.logger.debug("Không thể preload TTS: %s", preload_exc)
            return tts
        except Exception as exc:  # pragma: no cover
            self.logger.error(f"Không khởi tạo được TTSManager: {exc}")
            return None

    def _speak_scenario(self, scenario: ScenarioID, **kwargs) -> bool:
        if not self.tts_manager:
            return False
        return self.tts_manager.speak_scenario(scenario, **kwargs)

    def speak_text(self, message: str, *, volume: Optional[int] = None, force: bool = True) -> bool:
        """Queue a free-form TTS message using the Piper backend."""
        if not self.tts_manager or not message:
            return False
        try:
            return self.tts_manager.speak_scenario(
                ScenarioID.CHATBOT_PROMPT,
                override_message=message,
                volume=volume,
                force=force,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.error("Không thể phát thông điệp tuỳ chỉnh: %s", exc)
            return False

    def _handle_navigation_tts(self, screen_name: str):
        mapping = {
            'dashboard': ScenarioID.NAVIGATE_DASHBOARD,
            'heart_rate': ScenarioID.HR_PROMPT_FINGER,
            'temperature': ScenarioID.TEMP_PREP,
            'history': ScenarioID.HISTORY_OPEN,
        }
        scenario = mapping.get(screen_name)
        if scenario:
            self._speak_scenario(scenario)
    
    def build(self):
        """
        Build the main application
        
        Returns:
            Root widget (ScreenManager)
        """
        # Create screen manager with transition for clear navigation
        from kivy.uix.screenmanager import FadeTransition
        self.screen_manager = ScreenManager(transition=FadeTransition(duration=0.3))
        
        # Create screens
        dashboard = DashboardScreen(app_instance=self, name='dashboard')
        heart_rate = HeartRateScreen(app_instance=self, name='heart_rate')
        temperature = TemperatureScreen(app_instance=self, name='temperature')
        bp_measurement = BPMeasurementScreen(app_instance=self, name='bp_measurement')
        settings = SettingsScreen(app_instance=self, name='settings')
        history = HistoryScreen(app_instance=self, name='history')
        
        # Add screens to manager
        self.screen_manager.add_widget(dashboard)
        self.screen_manager.add_widget(heart_rate)
        self.screen_manager.add_widget(temperature)
        self.screen_manager.add_widget(bp_measurement)
        self.screen_manager.add_widget(settings)
        self.screen_manager.add_widget(history)
        
        # Set default screen
        self.screen_manager.current = 'dashboard'
        
        # Start data update timer
        self.start_data_updates()
        
        # Setup sensor callbacks
        self.setup_sensor_callbacks()

        # Push an immediate UI refresh so dashboard has latest state
        self.update_displays(0)

        self.logger.info("Health Monitor App initialized successfully")
        
        return self.screen_manager
    
    def setup_sensor_callbacks(self):
        """Setup callbacks for sensor data updates"""
        try:
            for key, callback in self.sensor_callbacks.items():
                sensor = self.sensors.get(key)
                if not sensor:
                    status_entry = self.current_data['sensor_status'].setdefault(key, {})
                    status_entry['status'] = 'unavailable'
                    continue

                if hasattr(sensor, 'set_data_callback'):
                    sensor.set_data_callback(callback)

                # Không tự động start cảm biến khi đang ở dashboard
                if getattr(sensor, 'is_running', False):
                    self.logger.info(f"{key} sensor already running; callback refreshed")
                else:
                    self.logger.debug(f"{key} sensor is idle; sẽ khởi động khi người dùng yêu cầu đo")
        
        except Exception as e:
            self.logger.error(f"Error setting up sensor callbacks: {e}")

    def ensure_sensor_started(self, sensor_key: str) -> bool:
        """Đảm bảo cảm biến được khởi động trước khi đo theo yêu cầu người dùng"""
        sensor = self.sensors.get(sensor_key)
        if not sensor:
            self.logger.error(f"Sensor {sensor_key} không tồn tại")
            return False

        callback = self.sensor_callbacks.get(sensor_key)
        if hasattr(sensor, 'set_data_callback') and callback:
            sensor.set_data_callback(callback)

        if getattr(sensor, 'is_running', False):
            self.logger.debug(f"Sensor {sensor_key} đã chạy sẵn")
            return True

        if hasattr(sensor, 'start'):
            started = sensor.start()
            if started:
                self.logger.info(f"Sensor {sensor_key} được khởi động theo yêu cầu")
                status_entry = self.current_data['sensor_status'].setdefault(sensor_key, {})
                status_entry['status'] = 'running'
            else:
                self.logger.error(f"Không thể khởi động sensor {sensor_key}")
                status_entry = self.current_data['sensor_status'].setdefault(sensor_key, {})
                status_entry['status'] = 'error'
            return bool(started)

        self.logger.error(f"Sensor {sensor_key} không hỗ trợ start()")
        return False

    def stop_sensor(self, sensor_key: str) -> bool:
        """Dừng cảm biến khi không còn dùng tới để tiết kiệm năng lượng"""
        sensor = self.sensors.get(sensor_key)
        if not sensor:
            return False

        if getattr(sensor, 'is_running', False) and hasattr(sensor, 'stop'):
            stopped = sensor.stop()
            if stopped:
                self.logger.info(f"Sensor {sensor_key} đã dừng sau khi đo")
                status_entry = self.current_data['sensor_status'].setdefault(sensor_key, {})
                status_entry['status'] = 'idle'
            else:
                self.logger.warning(f"Sensor {sensor_key} stop() trả về False")
            return bool(stopped)

        return True
    
    def on_max30102_data(self, sensor_name: str, data: Dict[str, Any]):
        """Handle MAX30102 sensor data updates"""
        try:
            # Get sensor instance for direct access to properties
            sensor = self.sensors.get('MAX30102')
            
            # Update heart rate and SpO2 with validation from MAX30102 logic
            if sensor:
                # Use sensor's current values directly
                self.current_data['heart_rate'] = getattr(sensor, 'heart_rate', 0)
                self.current_data['spo2'] = getattr(sensor, 'spo2', 0)
                self.current_data['hr_valid'] = getattr(sensor, 'hr_valid', False)
                self.current_data['spo2_valid'] = getattr(sensor, 'spo2_valid', False)
                self.current_data['finger_detected'] = getattr(sensor, 'finger_detected', False)
                
                # Get signal quality metrics
                self.current_data['signal_quality_ir'] = getattr(sensor, 'signal_quality_ir', 0)
                self.current_data['signal_quality_red'] = getattr(sensor, 'signal_quality_red', 0)
                
                # Get measurement status from sensor methods
                hr_status = sensor.get_heart_rate_status() if hasattr(sensor, 'get_heart_rate_status') else 'unknown'
                spo2_status = sensor.get_spo2_status() if hasattr(sensor, 'get_spo2_status') else 'unknown'
                
                # Store comprehensive sensor status
                self.current_data['sensor_status']['MAX30102'] = {
                    'status': 'streaming',
                    'hr_status': hr_status,
                    'spo2_status': spo2_status,
                    'finger_detected': self.current_data['finger_detected'],
                    'signal_quality_ir': self.current_data['signal_quality_ir'],
                    'signal_quality_red': self.current_data['signal_quality_red'],
                    'buffer_fill': len(getattr(sensor, 'ir_buffer', [])),
                    'readings_count': getattr(sensor, 'readings_count', 0),
                    'measurement_valid': self.current_data['hr_valid'] and self.current_data['spo2_valid']
                }
            else:
                # Fallback to data from callback if sensor not available
                self.current_data['heart_rate'] = data.get('heart_rate', 0)
                self.current_data['spo2'] = data.get('spo2', 0)
                self.current_data['hr_valid'] = data.get('hr_valid', False)
                self.current_data['spo2_valid'] = data.get('spo2_valid', False)
                self.current_data['finger_detected'] = data.get('finger_detected', False)

            finger_detected = bool(self.current_data.get('finger_detected'))
            previous_finger = self._hr_finger_present
            self._hr_finger_present = finger_detected

            if finger_detected:
                if previous_finger is False or previous_finger is None:
                    self._speak_scenario(ScenarioID.HR_MEASURING)
            else:
                if previous_finger:
                    self._speak_scenario(ScenarioID.HR_NO_FINGER)
                self._hr_last_announced = None

            hr_valid = bool(self.current_data.get('hr_valid'))
            spo2_valid = bool(self.current_data.get('spo2_valid'))
            heart_rate_value = self.current_data.get('heart_rate')
            spo2_value = self.current_data.get('spo2')

            if hr_valid and spo2_valid and finger_detected:
                if heart_rate_value is not None and spo2_value is not None:
                    hr_int = int(round(heart_rate_value))
                    spo2_int = int(round(spo2_value))
                    if self._hr_last_announced != (hr_int, spo2_int):
                        self._speak_scenario(ScenarioID.HR_RESULT, bpm=hr_int, spo2=spo2_int)
                        self._hr_last_announced = (hr_int, spo2_int)
            else:
                if finger_detected and not hr_valid:
                    signal_quality = self.current_data.get('signal_quality_ir')
                    if isinstance(signal_quality, (int, float)) and signal_quality < 40:
                        self._speak_scenario(ScenarioID.HR_SIGNAL_WEAK)
                if not hr_valid or not spo2_valid:
                    self._hr_last_announced = None
            
            # Update timestamp
            self.current_data['timestamp'] = data.get('timestamp', time.time())
            
            # Trigger immediate UI update
            Clock.schedule_once(lambda dt: self.update_displays(dt), 0)
            
        except Exception as e:
            self.logger.error(f"Error processing MAX30102 data: {e}")
    
    def on_temperature_data(self, sensor_name: str, data: Dict[str, Any]):
        """Handle MLX90614 temperature sensor data updates"""
        try:
            # Get sensor instance for direct access to properties
            sensor = self.sensors.get('MLX90614')
            
            if sensor:
                # Use sensor's current values directly from MLX90614 logic
                self.current_data['temperature'] = getattr(sensor, 'object_temperature', 0)
                self.current_data['ambient_temperature'] = getattr(sensor, 'ambient_temperature', 0)
                self.current_data['object_temperature'] = getattr(sensor, 'object_temperature', 0)
                
                # Get temperature in both units
                self.current_data['temperature_celsius'] = sensor.get_celsius() if hasattr(sensor, 'get_celsius') else self.current_data['temperature']
                self.current_data['temperature_fahrenheit'] = sensor.get_fahrenheit() if hasattr(sensor, 'get_fahrenheit') else (self.current_data['temperature'] * 9/5) + 32
                
                # Store MLX90614 sensor status with actual sensor data
                self.current_data['sensor_status']['MLX90614'] = {
                    'status': 'streaming',
                    'measurement_type': 'object' if getattr(sensor, 'use_object_temp', True) else 'ambient',
                    'temperature_unit': 'celsius',
                    'temperature_offset': getattr(sensor, 'temperature_offset', 0),
                    'smooth_factor': getattr(sensor, 'smooth_factor', 0.1),
                    'ambient_temp': self.current_data['ambient_temperature'],
                    'object_temp': self.current_data['object_temperature']
                }
            else:
                # Fallback to data from callback if sensor not available
                self.current_data['temperature'] = data.get('temperature', 0)
                self.current_data['ambient_temperature'] = data.get('ambient_temperature', 0)
                self.current_data['object_temperature'] = data.get('object_temperature', 0)
                self.current_data['temperature_celsius'] = self.current_data['temperature']
                self.current_data['temperature_fahrenheit'] = (self.current_data['temperature'] * 9/5) + 32
                
                self.current_data['sensor_status']['MLX90614'] = {
                    'status': data.get('status', 'normal'),
                    'measurement_type': data.get('measurement_type', 'object'),
                    'temperature_unit': data.get('temperature_unit', 'celsius')
                }

            temp_status = data.get('status', 'normal')
            temp_value = self.current_data.get('temperature_celsius')

            if temp_status in ('normal',) and temp_value is not None:
                if self._temp_last_status != 'normal':
                    self._speak_scenario(ScenarioID.TEMP_NORMAL, temp=temp_value)
                    self._temp_last_status = 'normal'
            elif temp_status in ('high', 'critical_high'):
                if self._temp_last_status != 'high':
                    self._speak_scenario(ScenarioID.TEMP_HIGH_ALERT)
                    self._temp_last_status = 'high'
            else:
                self._temp_last_status = temp_status
            
            # Update timestamp
            self.current_data['timestamp'] = time.time()
            
            # Trigger immediate UI update
            Clock.schedule_once(lambda dt: self.update_displays(dt), 0)
            
        except Exception as e:
            self.logger.error(f"Error processing MLX90614 temperature data: {e}")
    
    def on_blood_pressure_data(self, sensor_name: str, data: Dict[str, Any]):
        """Handle blood pressure sensor data updates"""
        try:
            self.current_data['blood_pressure_systolic'] = data.get('systolic', 0)
            self.current_data['blood_pressure_diastolic'] = data.get('diastolic', 0)
            self.current_data['sensor_status']['BloodPressure'] = {
                'status': data.get('status', 'unknown'),
                'measurement_complete': data.get('measurement_complete', False)
            }
            
        except Exception as e:
            self.logger.error(f"Error processing blood pressure data: {e}")
    
    def start_data_updates(self):
        """Start periodic data updates"""
        if self.data_update_event:
            self.data_update_event.cancel()
            
        # Update UI every 1 second
        self.data_update_event = Clock.schedule_interval(self.update_displays, 1.0)
    
    def stop_data_updates(self):
        """Stop periodic data updates"""
        if self.data_update_event:
            self.data_update_event.cancel()
            self.data_update_event = None
    
    def update_displays(self, dt):
        """Update all screen displays with current data"""
        try:
            # Get real-time data from sensors if available
            self._update_sensor_data_direct()
            
            # Update current screen
            current_screen = self.screen_manager.current_screen
            if hasattr(current_screen, 'update_data'):
                should_update = (
                    current_screen.name == 'dashboard'
                    or getattr(current_screen, 'accepts_realtime_data', False)
                )
                if should_update:
                    current_screen.update_data(self.current_data)
                    
        except Exception as e:
            self.logger.error(f"Error updating displays: {e}")
    
    def _update_sensor_data_direct(self):
        """Update sensor data directly from sensor instances"""
        try:
            # Update MAX30102 data directly
            if 'MAX30102' in self.sensors and self.sensors['MAX30102']:
                sensor = self.sensors['MAX30102']
                if hasattr(sensor, 'is_running') and sensor.is_running:
                    self.current_data['heart_rate'] = getattr(sensor, 'heart_rate', 0)
                    self.current_data['spo2'] = getattr(sensor, 'spo2', 0)
                    self.current_data['hr_valid'] = getattr(sensor, 'hr_valid', False)
                    self.current_data['spo2_valid'] = getattr(sensor, 'spo2_valid', False)
                    self.current_data['finger_detected'] = getattr(sensor, 'finger_detected', False)
                    
                    # Update status
                    if not self.current_data['finger_detected']:
                        hr_status = 'no_finger'
                        spo2_status = 'no_finger'
                    else:
                        hr_status = sensor.get_heart_rate_status() if hasattr(sensor, 'get_heart_rate_status') else 'unknown'
                        spo2_status = sensor.get_spo2_status() if hasattr(sensor, 'get_spo2_status') else 'unknown'
                    
                    self.current_data['sensor_status']['MAX30102'] = {
                        'hr_status': hr_status,
                        'spo2_status': spo2_status,
                        'finger_detected': self.current_data['finger_detected'],
                        'measurement_valid': self.current_data['hr_valid'] and self.current_data['spo2_valid']
                    }
            
            # Update MLX90614 data directly
            if 'MLX90614' in self.sensors and self.sensors['MLX90614']:
                sensor = self.sensors['MLX90614']
                if hasattr(sensor, 'is_running') and sensor.is_running:
                    self.current_data['temperature'] = getattr(sensor, 'object_temperature', 0)
                    self.current_data['ambient_temperature'] = getattr(sensor, 'ambient_temperature', 0)
                    self.current_data['object_temperature'] = getattr(sensor, 'object_temperature', 0)
                    
                    # Determine temperature status
                    temp = self.current_data['temperature']
                    if temp < 35.0:
                        temp_status = 'critical_low'
                    elif temp < 36.0:
                        temp_status = 'low'
                    elif temp <= 37.5:
                        temp_status = 'normal'
                    elif temp <= 39.0:
                        temp_status = 'high'
                    else:
                        temp_status = 'critical_high'
                    
                    self.current_data['sensor_status']['MLX90614'] = {
                        'status': temp_status,
                        'measurement_type': 'object' if getattr(sensor, 'use_object_temp', True) else 'ambient',
                        'temperature_unit': 'celsius'
                    }
            
        except Exception as e:
            self.logger.error(f"Error updating sensor data directly: {e}")
    
    def navigate_to_screen(self, screen_name: str):
        """Navigate to specified screen"""
        try:
            available_screens = [screen.name for screen in self.screen_manager.screens]
            self.logger.info(f"Available screens: {available_screens}")
            self.logger.info(f"Attempting to navigate to: {screen_name}")
            
            if screen_name in available_screens:
                self.screen_manager.current = screen_name
                self.logger.info(f"Successfully navigated to {screen_name} screen")
                self._handle_navigation_tts(screen_name)
                # Force update current screen
                current_screen = self.screen_manager.current_screen
                if hasattr(current_screen, 'on_enter'):
                    current_screen.on_enter()
            else:
                self.logger.warning(f"Screen {screen_name} not found in available screens: {available_screens}")
                
        except Exception as e:
            self.logger.error(f"Error navigating to screen {screen_name}: {e}")
    
    def get_sensor_data(self) -> Dict[str, Any]:
        """Get current sensor data"""
        return self.current_data.copy()

    def get_history_records(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """Fetch historical measurement records from database or fallback storage."""
        patient_id = (self.config_data.get('patient') or {}).get('id', 'patient_001')

        if self.database and hasattr(self.database, 'get_health_records'):
            try:
                records = self.database.get_health_records(
                    patient_id,
                    start_time=start_time,
                    end_time=end_time,
                    limit=limit,
                )
                if records:
                    return records
            except Exception as exc:
                self.logger.error("Database history retrieval failed: %s", exc)

        db_path = project_root / "data" / "vitals.db"
        if not db_path.exists():
            return []

        query = "SELECT ts, hr, spo2, temp, alert FROM vitals"
        filters: List[str] = []
        params: List[Any] = []
        if start_time:
            filters.append("ts >= ?")
            params.append(start_time.isoformat())
        if end_time:
            filters.append("ts <= ?")
            params.append(end_time.isoformat())
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY ts DESC LIMIT ?"
        params.append(int(limit))

        results: List[Dict[str, Any]] = []
        try:
            with closing(sqlite3.connect(db_path)) as conn:
                conn.row_factory = sqlite3.Row
                with closing(conn.cursor()) as cursor:
                    cursor.execute(query, params)
                    for row in cursor.fetchall():
                        try:
                            ts = datetime.fromisoformat(row["ts"].strip()) if row["ts"] else None
                        except ValueError:
                            ts = None
                        results.append(
                            {
                                'timestamp': ts,
                                'heart_rate': row['hr'],
                                'spo2': row['spo2'],
                                'temperature': row['temp'],
                                'alert': row['alert'],
                            }
                        )
        except Exception as exc:
            self.logger.error("Failed to read fallback history: %s", exc)
            return []

        return results
    
    def save_measurement_to_database(self, measurement_data: Dict[str, Any]):
        """Save measurement data to database"""
        try:
            if self.database:
                inserted = False
                insert_vitals = getattr(self.database, 'insert_vital_signs', None)
                save_record = getattr(self.database, 'save_health_record', None)
                try:
                    if callable(insert_vitals):
                        insert_vitals(measurement_data)
                        inserted = True
                    elif callable(save_record):
                        save_record(measurement_data)
                        inserted = True
                except Exception as exc:
                    self.logger.error("Primary database save failed: %s", exc)

                if inserted:
                    self.logger.info("Measurement saved to database")
                    return

                self.logger.warning("Database handler missing insert method; using local fallback")

            if self._save_to_local_vitals(measurement_data):
                self.logger.info("Measurement saved to local vitals.db")
            else:
                self.logger.warning("Unable to persist measurement data")
                
        except Exception as e:
            self.logger.error(f"Error saving to database: {e}")

    def _save_to_local_vitals(self, measurement_data: Dict[str, Any]) -> bool:
        db_path = project_root / "data" / "vitals.db"
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            timestamp = measurement_data.get('timestamp')
            if isinstance(timestamp, (int, float)):
                ts_str = datetime.fromtimestamp(timestamp).isoformat()
            elif isinstance(timestamp, str):
                ts_str = timestamp
            else:
                ts_str = datetime.now().isoformat()

            hr = measurement_data.get('heart_rate') or measurement_data.get('hr')
            spo2 = measurement_data.get('spo2')
            temp = (
                measurement_data.get('temperature')
                or measurement_data.get('temp')
                or measurement_data.get('object_temperature')
            )

            measurement_type = measurement_data.get('measurement_type', '')
            alert = measurement_data.get('alert') or ''

            if measurement_type == 'blood_pressure':
                systolic = measurement_data.get('systolic') or measurement_data.get('blood_pressure_systolic')
                diastolic = measurement_data.get('diastolic') or measurement_data.get('blood_pressure_diastolic')
                if systolic and diastolic:
                    alert = f"BP {systolic:.0f}/{diastolic:.0f} mmHg"

            with closing(sqlite3.connect(db_path)) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS vitals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts TEXT NOT NULL,
                        hr REAL,
                        spo2 REAL,
                        temp REAL,
                        alert TEXT
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO vitals (ts, hr, spo2, temp, alert) VALUES (?, ?, ?, ?, ?)",
                    (ts_str, hr, spo2, temp, alert),
                )
                conn.commit()
            return True
        except Exception as exc:
            self.logger.error("Local vitals save failed: %s", exc)
            return False

    def persist_config(self) -> None:
        """Persist current configuration back to YAML file."""
        config_path = project_root / "config" / "app_config.yaml"
        try:
            with config_path.open('w', encoding='utf-8') as handle:
                yaml.safe_dump(self.config_data, handle, allow_unicode=True, sort_keys=False)
            self.audio_config = self.config_data.get('audio', {}) or {}
            self.logger.info("Configuration persisted to %s", config_path)
        except Exception as exc:
            self.logger.error("Không thể lưu cấu hình: %s", exc)
    
    def on_stop(self):
        """Called when app is stopping"""
        self.logger.info("Stopping Health Monitor App")
        
        # Stop data updates
        self.stop_data_updates()
        
        if self.tts_manager:
            try:
                self.tts_manager.shutdown()
            except Exception as exc:
                self.logger.error(f"Error shutting down TTS manager: {exc}")

        # Stop sensors
        for sensor_name, sensor in self.sensors.items():
            try:
                if hasattr(sensor, 'stop'):
                    sensor.stop()
            except Exception as e:
                self.logger.error(f"Error stopping sensor {sensor_name}: {e}")
        
        # Close database
        if self.database:
            try:
                self.database.close()
            except Exception as e:
                self.logger.error(f"Error closing database: {e}")
    
    def on_start(self):
        """
        Called when application starts
        """
        self._speak_scenario(ScenarioID.SYSTEM_START)
    


def main():
    """Main function for running the app directly"""
    import sys
    import logging
    import yaml
    
    # Setup basic logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    # Load configuration from app_config.yaml
    config = {}
    try:
        config_path = project_root / "config" / "app_config.yaml"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from {config_path}")
        else:
            logger.warning(f"Config file not found at {config_path}, using defaults")
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
    
    # Set default config if empty
    if not config:
        config = {
            'app': {'name': 'IoT Health Monitor', 'debug': True},
            'patient': {'name': 'Test Patient', 'age': 65},
            'sensors': {
                'max30102': {'enabled': True},
                'mlx90614': {'enabled': True},
                'blood_pressure': {'enabled': False}
            }
        }
    
    try:
        # Create and run app with real sensor integration
        app = HealthMonitorApp(
            config=config,
            sensors=None,  # Will create from config
            database=None,
            mqtt_client=None,
            alert_system=None
        )
        app.run()
    except Exception as e:
        logger.error(f"Error running app: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()