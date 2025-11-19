"""
Main Kivy Application
Main application class cho IoT Health Monitoring GUI
"""

from typing import Dict, Any, Optional, List
import logging
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta
from contextlib import closing
import sqlite3
import yaml
from kivy.uix.screenmanager import ScreenManager
from kivy.clock import Clock
from kivy.config import Config
from kivymd.app import MDApp
from kivymd.uix.snackbar import Snackbar

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
from src.utils.health_validators import HealthDataValidator

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


class HealthMonitorApp(MDApp):
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

    # ------------------------------------------------------------------
    # Initialization & Lifecycle
    # ------------------------------------------------------------------

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

        # Configure KivyMD theme to align với palette y tế
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Blue"
        self.theme_cls.primary_hue = "500"
        self.theme_cls.accent_palette = "Teal"

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
            'window_fill': 0.0,
            'measurement_ready': False,
            'measurement_elapsed': 0.0,
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
            
            # Create Blood Pressure sensor if enabled and HX710B config ready
            bp_config = sensor_configs.get('blood_pressure', {})
            self.logger.debug(f"📊 BP Config check: enabled={bp_config.get('enabled')}, BloodPressureSensor={BloodPressureSensor is not None}")
            
            if bp_config.get('enabled', False) and BloodPressureSensor:
                # HX710B config is NESTED inside blood_pressure config
                hx710b_config = bp_config.get('hx710b', {})
                
                # DEBUG: Log config values
                self.logger.debug(f"BP config keys: {list(bp_config.keys())}")
                self.logger.debug(f"HX710B config exists: {bool(hx710b_config)}")
                self.logger.debug(f"HX710B enabled value: {hx710b_config.get('enabled', 'NOT_FOUND')}")
                
                if not hx710b_config:
                    self.logger.warning("HX710B config chưa được định nghĩa trong blood_pressure - bỏ qua khởi tạo")
                elif not hx710b_config.get('enabled', False):
                    self.logger.info(f"HX710B đang bị tắt (enabled={hx710b_config.get('enabled')}) - cảm biến huyết áp sẽ không khởi tạo")
                else:
                    try:
                        # BP config already contains hx710b nested inside
                        self.logger.info("🚀 Attempting to create BloodPressure sensor...")
                        sensor = BloodPressureSensor('BloodPressure', bp_config)
                        self.logger.info("🔧 BloodPressure sensor object created, calling initialize()...")
                        if sensor.initialize():
                            sensors['BloodPressure'] = sensor
                            self.logger.info("✅ BloodPressure sensor created and initialized successfully")
                        else:
                            self.logger.warning("⚠️  BloodPressure sensor.initialize() returned False")
                    except Exception as e:
                        self.logger.error(f"❌ Exception creating BloodPressure sensor: {type(e).__name__}: {e}", exc_info=True)
            else:
                if not bp_config.get('enabled', False):
                    self.logger.debug("BloodPressure disabled in config")
                if not BloodPressureSensor:
                    self.logger.error("❌ BloodPressureSensor class not imported!")
            
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

    # ------------------------------------------------------------------
    # TTS & Audio Management
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # UI Construction & Layout
    # ------------------------------------------------------------------

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

        self.logger.info("HealthMonitorApp initialized successfully")
        
        return self.screen_manager

    # ------------------------------------------------------------------
    # Sensor Management
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Data Callbacks & Event Handling
    # ------------------------------------------------------------------

    def on_max30102_data(self, sensor_name: str, data: Dict[str, Any]):
        """Handle MAX30102 sensor data updates"""
        try:
            # Get sensor instance for direct access to properties
            sensor = self.sensors.get('MAX30102')
            
            # Update heart rate and SpO2 with validation from MAX30102 logic
            if sensor:
                # Use sensor's current values directly - TRUY CẬP ĐÚNG SAU REFACTOR
                self.current_data['heart_rate'] = sensor.measurement.heart_rate
                self.current_data['spo2'] = sensor.measurement.spo2
                self.current_data['hr_valid'] = sensor.measurement.hr_valid
                self.current_data['spo2_valid'] = sensor.measurement.spo2_valid
                self.current_data['finger_detected'] = sensor.finger.detected
                self.current_data['window_fill'] = sensor.measurement.window_fill
                self.current_data['measurement_ready'] = sensor.measurement.ready
                self.current_data['measurement_elapsed'] = sensor.session.elapsed
                
                # Get signal quality metrics (including new metadata from refactor)
                self.current_data['signal_quality_ir'] = sensor.measurement.signal_quality_ir
                self.current_data['signal_quality_red'] = sensor.measurement.signal_quality_red
                self.current_data['signal_quality_index'] = sensor.measurement.signal_quality_index  # NEW: SQI 0-100
                self.current_data['spo2_cv'] = sensor.measurement.spo2_cv  # NEW: Coefficient of variation
                self.current_data['peak_count'] = sensor.measurement.peak_count  # NEW: Number of peaks
                
                # Get measurement status from sensor methods
                hr_status = sensor.get_heart_rate_status() if hasattr(sensor, 'get_heart_rate_status') else 'unknown'
                spo2_status = sensor.get_spo2_status() if hasattr(sensor, 'get_spo2_status') else 'unknown'

                window = getattr(sensor, 'window', None)
                buffer_fill = len(window.ir) if window and hasattr(window, 'ir') else 0
                
                # Store comprehensive sensor status
                self.current_data['sensor_status']['MAX30102'] = {
                    'status': sensor.measurement.status,
                    'hr_status': hr_status,
                    'spo2_status': spo2_status,
                    'finger_detected': sensor.finger.detected,
                    'signal_quality_ir': sensor.measurement.signal_quality_ir,
                    'signal_quality_red': sensor.measurement.signal_quality_red,
                    'signal_quality_index': sensor.measurement.signal_quality_index,  # NEW: SQI
                    'buffer_fill': buffer_fill,
                    'readings_count': sensor.measurement.readings_count,
                    'measurement_valid': sensor.measurement.hr_valid and sensor.measurement.spo2_valid,
                    'window_fill': sensor.measurement.window_fill,
                    'measurement_ready': sensor.measurement.ready,
                    'session_active': sensor.session.active,
                    'measurement_elapsed': sensor.session.elapsed,
                    'measurement_duration': sensor.measurement_window_seconds,
                    'finger_detection_score': sensor.finger.detection_score,
                    'finger_signal_amplitude': sensor.finger.signal_amplitude,
                    'finger_signal_ratio': sensor.finger.signal_ratio,
                    'finger_signal_quality': sensor.finger.signal_quality,
                    'spo2_cv': sensor.measurement.spo2_cv,  # NEW: CV for quality tracking
                    'peak_count': sensor.measurement.peak_count,  # NEW: Peak count
                }
            else:
                # Fallback to data from callback if sensor not available
                self.current_data['heart_rate'] = data.get('heart_rate', 0)
                self.current_data['spo2'] = data.get('spo2', 0)
                self.current_data['hr_valid'] = data.get('hr_valid', False)
                self.current_data['spo2_valid'] = data.get('spo2_valid', False)
                self.current_data['finger_detected'] = data.get('finger_detected', False)
                self.current_data['window_fill'] = data.get('window_fill', 0.0)
                self.current_data['measurement_ready'] = data.get('measurement_ready', False)
                self.current_data['measurement_elapsed'] = data.get('measurement_elapsed', 0.0)
                self.current_data['signal_quality_ir'] = data.get('signal_quality_ir', 0)
                self.current_data['signal_quality_red'] = data.get('signal_quality_red', 0)
                self.current_data['signal_quality_index'] = data.get('signal_quality_index', 0.0)  # NEW: SQI
                self.current_data['spo2_cv'] = data.get('spo2_cv', 0.0)  # NEW: CV
                self.current_data['peak_count'] = data.get('peak_count', 0)  # NEW: Peak count

                self.current_data['sensor_status']['MAX30102'] = {
                    'status': data.get('status', 'streaming'),
                    'hr_status': data.get('hr_status', 'unknown'),
                    'spo2_status': data.get('spo2_status', 'unknown'),
                    'finger_detected': self.current_data['finger_detected'],
                    'signal_quality_ir': data.get('signal_quality_ir', 0),
                    'signal_quality_red': data.get('signal_quality_red', 0),
                    'signal_quality_index': data.get('signal_quality_index', 0.0),  # NEW: SQI
                    'buffer_fill': data.get('buffer_fill', 0),
                    'measurement_valid': self.current_data['hr_valid'] and self.current_data['spo2_valid'],
                    'window_fill': self.current_data['window_fill'],
                    'measurement_ready': self.current_data['measurement_ready'],
                    'session_active': data.get('session_active', False),
                    'measurement_elapsed': self.current_data['measurement_elapsed'],
                    'measurement_duration': data.get('measurement_duration'),
                    'finger_detection_score': data.get('finger_detection_score', 0.0),
                    'spo2_cv': data.get('spo2_cv', 0.0),  # NEW: CV
                    'peak_count': data.get('peak_count', 0),  # NEW: Peak count
                    'finger_signal_amplitude': data.get('finger_signal_amplitude', 0.0),
                    'finger_signal_ratio': data.get('finger_signal_ratio', 0.0),
                    'finger_signal_quality': data.get('finger_signal_quality', 0.0),
                }

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
                    # TRUY CẬP ĐÚNG SAU REFACTOR - Bao gồm metadata mới
                    self.current_data['heart_rate'] = sensor.measurement.heart_rate
                    self.current_data['spo2'] = sensor.measurement.spo2
                    self.current_data['hr_valid'] = sensor.measurement.hr_valid
                    self.current_data['spo2_valid'] = sensor.measurement.spo2_valid
                    self.current_data['finger_detected'] = sensor.finger.detected
                    self.current_data['window_fill'] = sensor.measurement.window_fill
                    self.current_data['measurement_ready'] = sensor.measurement.ready
                    self.current_data['measurement_elapsed'] = sensor.session.elapsed
                    self.current_data['signal_quality_ir'] = sensor.measurement.signal_quality_ir
                    self.current_data['signal_quality_red'] = sensor.measurement.signal_quality_red
                    self.current_data['signal_quality_index'] = sensor.measurement.signal_quality_index  # NEW: SQI
                    self.current_data['spo2_cv'] = sensor.measurement.spo2_cv  # NEW: CV
                    self.current_data['peak_count'] = sensor.measurement.peak_count  # NEW: Peak count
                    
                    # Update status
                    if not sensor.finger.detected:
                        hr_status = 'no_finger'
                        spo2_status = 'no_finger'
                    else:
                        hr_status = sensor.get_heart_rate_status() if hasattr(sensor, 'get_heart_rate_status') else 'unknown'
                        spo2_status = sensor.get_spo2_status() if hasattr(sensor, 'get_spo2_status') else 'unknown'
                    
                    self.current_data['sensor_status']['MAX30102'] = {
                        'hr_status': hr_status,
                        'spo2_status': spo2_status,
                        'finger_detected': sensor.finger.detected,
                        'measurement_valid': sensor.measurement.hr_valid and sensor.measurement.spo2_valid,
                        'window_fill': sensor.measurement.window_fill,
                        'measurement_ready': sensor.measurement.ready,
                        'measurement_elapsed': sensor.session.elapsed,
                        'measurement_duration': sensor.measurement_window_seconds,
                        'session_active': sensor.session.active,
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

    # ------------------------------------------------------------------
    # Navigation & Screen Management
    # ------------------------------------------------------------------

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
        """
        Save measurement data to database using DatabaseManager
        
        Args:
            measurement_data: Dictionary containing measurement data
                Required: timestamp
                Optional: heart_rate, spo2, temperature, systolic, diastolic, 
                         signal_quality_index, spo2_cv, peak_count, measurement_elapsed
        """
        try:
            # ============================================================
            # VALIDATION: Check data validity before saving
            # ============================================================
            is_valid, validation_errors = HealthDataValidator.validate(measurement_data)
            
            if not is_valid:
                # Show validation errors to user
                error_message = "Dữ liệu không hợp lệ:\n" + "\n".join(validation_errors)
                self.logger.warning(f"Validation failed: {validation_errors}")
                self._show_error_notification(error_message)
                return None  # Don't save invalid data
            
            # ============================================================
            # Ưu tiên dùng DatabaseManager nếu có
            # ============================================================
            if self.database and hasattr(self.database, 'save_health_record'):
                try:
                    # Lấy patient_id từ config
                    patient_id = self.config_data.get('patient', {}).get('id', 'patient_001')
                    
                    # Chuẩn bị data theo format của DatabaseManager.save_health_record()
                    timestamp_value = measurement_data.get('timestamp', time.time())
                    # Convert timestamp to datetime object if needed
                    if isinstance(timestamp_value, (int, float)):
                        timestamp_dt = datetime.fromtimestamp(timestamp_value)
                    elif isinstance(timestamp_value, datetime):
                        timestamp_dt = timestamp_value
                    else:
                        timestamp_dt = datetime.now()
                    
                    health_data = {
                        'patient_id': patient_id,  # REQUIRED by save_health_record()
                        'device_id': self.config_data.get('cloud', {}).get('device', {}).get('device_id', 'rpi_bp_001'),  # REQUIRED after migration
                        'timestamp': timestamp_dt,  # Must be datetime object for SQLAlchemy
                        'heart_rate': measurement_data.get('heart_rate') or measurement_data.get('hr'),
                        'spo2': measurement_data.get('spo2'),
                        'temperature': (
                            measurement_data.get('temperature') 
                            or measurement_data.get('temp')
                            or measurement_data.get('object_temperature')
                        ),
                        'systolic_bp': measurement_data.get('systolic') or measurement_data.get('blood_pressure_systolic'),
                        'diastolic_bp': measurement_data.get('diastolic') or measurement_data.get('blood_pressure_diastolic'),
                        'mean_arterial_pressure': measurement_data.get('map') or measurement_data.get('map_bp'),
                    }
                    
                    # ============================================================
                    # PHASE 2: Lưu metadata mới (SQI, CV, peak_count, duration)
                    # ============================================================
                    metadata = {}
                    
                    # Signal Quality Index (0-100) cho HR measurement
                    if 'signal_quality_index' in measurement_data:
                        metadata['signal_quality_index'] = measurement_data['signal_quality_index']
                    
                    # Coefficient of Variation cho SpO2 measurement
                    if 'spo2_cv' in measurement_data:
                        metadata['spo2_cv'] = measurement_data['spo2_cv']
                    
                    # Peak count cho HR measurement
                    if 'peak_count' in measurement_data:
                        metadata['peak_count'] = measurement_data['peak_count']
                    
                    # Measurement duration (seconds)
                    if 'measurement_elapsed' in measurement_data or 'measurement_duration' in measurement_data:
                        metadata['measurement_duration'] = (
                            measurement_data.get('measurement_elapsed') 
                            or measurement_data.get('measurement_duration')
                        )
                    
                    # Measurement type để phân biệt nguồn data
                    if 'measurement_type' in measurement_data:
                        metadata['measurement_type'] = measurement_data['measurement_type']
                    
                    # Ambient temperature (nếu là MLX90614)
                    if 'ambient_temperature' in measurement_data:
                        metadata['ambient_temperature'] = measurement_data['ambient_temperature']
                    
                    # HR/SpO2 valid flags
                    if 'hr_valid' in measurement_data:
                        metadata['hr_valid'] = measurement_data['hr_valid']
                    if 'spo2_valid' in measurement_data:
                        metadata['spo2_valid'] = measurement_data['spo2_valid']
                    
                    # Thêm metadata vào health_data
                    if metadata:
                        health_data['sensor_data'] = metadata  # Lưu metadata vào sensor_data JSON column
                    
                    # Gọi DatabaseManager.save_health_record() - CHỈ 1 ARGUMENT
                    record_id = self.database.save_health_record(health_data)
                    
                    if record_id:
                        self.logger.info(
                            f"✅ Measurement saved to DatabaseManager (record_id={record_id}, patient={patient_id})"
                        )
                        
                        # ============================================================
                        # USER FEEDBACK: Show success notification
                        # ============================================================
                        self._show_success_notification(
                            f"Đã lưu kết quả (ID: {record_id})",
                            duration=2
                        )
                        
                        # Kiểm tra ngưỡng và tạo alert nếu cần
                        self._check_and_create_alert(patient_id, health_data, record_id)
                        return record_id
                    else:
                        self.logger.warning("DatabaseManager.save_health_record() returned None - falling back to local DB")
                        
                except Exception as exc:
                    self.logger.error(f"DatabaseManager save failed: {exc}", exc_info=True)
                    self.logger.warning("Falling back to local vitals.db")

            # Fallback về SQLite cục bộ nếu DatabaseManager fail hoặc không có
            if self._save_to_local_vitals(measurement_data):
                self.logger.info("Measurement saved to local vitals.db (fallback)")
                self._show_success_notification("Đã lưu kết quả (local)", duration=2)
            else:
                self.logger.error("Unable to persist measurement data to any database")
                self._show_error_notification("Không thể lưu dữ liệu vào database")
                
        except Exception as e:
            self.logger.error(f"Critical error in save_measurement_to_database: {e}", exc_info=True)
            self._show_error_notification(f"Lỗi khi lưu: {str(e)}")

    def _check_and_create_alert(self, patient_id: str, health_data: Dict[str, Any], record_id: int):
        """
        Kiểm tra ngưỡng và tạo alert tự động nếu vượt threshold
        
        Args:
            patient_id: Patient ID
            health_data: Health record data
            record_id: ID của health record vừa lưu
        """
        try:
            if not self.database or not hasattr(self.database, 'get_patient_thresholds'):
                return
            
            # Lấy ngưỡng của patient
            thresholds = self.database.get_patient_thresholds(patient_id)
            if not thresholds:
                self.logger.debug(f"No thresholds found for patient {patient_id}")
                return
            
            alerts = []
            
            # Kiểm tra Heart Rate
            hr = health_data.get('heart_rate')
            if hr and hr > 0:
                hr_min = thresholds.get('heart_rate_min', 60)
                hr_max = thresholds.get('heart_rate_max', 100)
                if hr < hr_min:
                    alerts.append({
                        'type': 'low_heart_rate',
                        'severity': 'medium',
                        'message': f'Nhịp tim thấp: {hr:.0f} BPM (ngưỡng: {hr_min}-{hr_max})',
                        'value': hr,
                        'vital_sign': 'heart_rate',
                        'threshold': hr_min
                    })
                elif hr > hr_max:
                    alerts.append({
                        'type': 'high_heart_rate',
                        'severity': 'high',
                        'message': f'Nhịp tim cao: {hr:.0f} BPM (ngưỡng: {hr_min}-{hr_max})',
                        'value': hr,
                        'vital_sign': 'heart_rate',
                        'threshold': hr_max
                    })
            
            # Kiểm tra SpO2
            spo2 = health_data.get('spo2')
            if spo2 and spo2 > 0:
                spo2_min = thresholds.get('spo2_min', 95)
                if spo2 < spo2_min:
                    severity = 'critical' if spo2 < 90 else 'high'
                    alerts.append({
                        'type': 'low_spo2',
                        'severity': severity,
                        'message': f'SpO2 thấp: {spo2:.0f}% (ngưỡng tối thiểu: {spo2_min}%)',
                        'value': spo2,
                        'vital_sign': 'spo2',
                        'threshold': spo2_min
                    })
            
            # Kiểm tra Temperature
            temp = health_data.get('temperature')
            if temp and temp > 0:
                temp_min = thresholds.get('temperature_min', 36.0)
                temp_max = thresholds.get('temperature_max', 37.5)
                if temp < temp_min:
                    severity = 'high' if temp < 35.0 else 'medium'
                    alerts.append({
                        'type': 'low_temperature',
                        'severity': severity,
                        'message': f'Nhiệt độ thấp: {temp:.1f}°C (ngưỡng: {temp_min}-{temp_max})',
                        'value': temp,
                        'vital_sign': 'temperature',
                        'threshold': temp_min
                    })
                elif temp > temp_max:
                    severity = 'critical' if temp > 39.0 else 'high'
                    alerts.append({
                        'type': 'high_temperature',
                        'severity': severity,
                        'message': f'Nhiệt độ cao: {temp:.1f}°C (ngưỡng: {temp_min}-{temp_max})',
                        'value': temp,
                        'vital_sign': 'temperature',
                        'threshold': temp_max
                    })
            
            # Kiểm tra Blood Pressure
            systolic = health_data.get('systolic_bp')
            diastolic = health_data.get('diastolic_bp')
            if systolic and systolic > 0 and diastolic and diastolic > 0:
                sys_min = thresholds.get('systolic_bp_min', 90)
                sys_max = thresholds.get('systolic_bp_max', 140)
                dia_min = thresholds.get('diastolic_bp_min', 60)
                dia_max = thresholds.get('diastolic_bp_max', 90)
                
                if systolic < sys_min or diastolic < dia_min:
                    alerts.append({
                        'type': 'low_blood_pressure',
                        'severity': 'medium',
                        'message': f'Huyết áp thấp: {systolic:.0f}/{diastolic:.0f} mmHg',
                        'value': f'{systolic}/{diastolic}',
                        'vital_sign': 'blood_pressure',
                        'threshold': f'{sys_min}/{dia_min}'
                    })
                elif systolic > sys_max or diastolic > dia_max:
                    severity = 'critical' if systolic > 180 or diastolic > 120 else 'high'
                    alerts.append({
                        'type': 'high_blood_pressure',
                        'severity': severity,
                        'message': f'Huyết áp cao: {systolic:.0f}/{diastolic:.0f} mmHg',
                        'value': f'{systolic}/{diastolic}',
                        'vital_sign': 'blood_pressure',
                        'threshold': f'{sys_max}/{dia_max}'
                    })
            
            # Lưu alerts vào database
            for alert_data in alerts:
                try:
                    # ============================================================
                    # ALERT DEDUPLICATION: Check for existing unresolved alert
                    # ============================================================
                    if hasattr(self.database, 'get_active_alerts'):
                        # Check if similar alert exists within last hour
                        active_alerts = self.database.get_active_alerts(patient_id)
                        
                        # Filter for same type and not resolved
                        duplicate_found = False
                        for existing in active_alerts:
                            if existing.get('alert_type') == alert_data['type']:
                                # Check timestamp (within 1 hour)
                                try:
                                    alert_time = datetime.fromisoformat(existing.get('timestamp', ''))
                                    time_diff = datetime.now() - alert_time
                                    
                                    if time_diff < timedelta(hours=1):
                                        duplicate_found = True
                                        self.logger.debug(
                                            f"Skipping duplicate alert: {alert_data['type']} "
                                            f"(existing alert_id={existing.get('id')}, "
                                            f"age={time_diff.total_seconds() / 60:.1f} minutes)"
                                        )
                                        break
                                except:
                                    pass
                        
                        if duplicate_found:
                            continue  # Skip this alert, don't create duplicate
                    
                    # Create new alert (no duplicate found)
                    if hasattr(self.database, 'save_alert'):
                        # Prepare alert_data dict for save_alert()
                        alert_dict = {
                            'patient_id': patient_id,
                            'alert_type': alert_data['type'],
                            'severity': alert_data['severity'],
                            'message': alert_data['message'],
                            'vital_sign': alert_data.get('vital_sign'),
                            'current_value': alert_data.get('value'),
                            'threshold_value': alert_data.get('threshold'),
                            'timestamp': datetime.now()
                        }
                        
                        alert_id = self.database.save_alert(alert_dict)
                        self.logger.info(
                            f"⚠️  Alert created: {alert_data['type']} (severity={alert_data['severity']}, alert_id={alert_id})"
                        )
                        
                        # Gửi TTS warning nếu severity cao
                        if alert_data['severity'] in ('high', 'critical'):
                            self.speak_text(alert_data['message'], force=True)
                            
                except Exception as alert_exc:
                    self.logger.error(f"Failed to create alert: {alert_exc}")
                    
        except Exception as e:
            self.logger.error(f"Error checking thresholds and creating alerts: {e}", exc_info=True)

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
            
            # ============================================================
            # PHASE 2: Extract metadata for quality tracking
            # ============================================================
            hr_sqi = measurement_data.get('signal_quality_index')  # SQI 0-100
            spo2_cv = measurement_data.get('spo2_cv')  # Coefficient of variation
            peak_count = measurement_data.get('peak_count')  # Number of peaks
            measurement_duration = measurement_data.get('measurement_elapsed')  # Duration in seconds

            if measurement_type == 'blood_pressure':
                systolic = measurement_data.get('systolic') or measurement_data.get('blood_pressure_systolic')
                diastolic = measurement_data.get('diastolic') or measurement_data.get('blood_pressure_diastolic')
                if systolic and diastolic:
                    alert = f"BP {systolic:.0f}/{diastolic:.0f} mmHg"

            with closing(sqlite3.connect(db_path)) as conn:
                # Create/update table with Phase 2 metadata columns
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS vitals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts TEXT NOT NULL,
                        hr REAL,
                        spo2 REAL,
                        temp REAL,
                        alert TEXT,
                        hr_sqi REAL,
                        spo2_cv REAL,
                        peak_count INTEGER,
                        measurement_duration REAL
                    )
                    """
                )
                # PHASE 2: Insert with metadata
                conn.execute(
                    """
                    INSERT INTO vitals 
                    (ts, hr, spo2, temp, alert, hr_sqi, spo2_cv, peak_count, measurement_duration) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (ts_str, hr, spo2, temp, alert, hr_sqi, spo2_cv, peak_count, measurement_duration),
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

    # ------------------------------------------------------------------
    # User Feedback & Notifications
    # ------------------------------------------------------------------

    def _show_success_notification(self, message: str, duration: float = 2.0):
        """Show success notification using Snackbar"""
        try:
            Snackbar(
                text=f"✅ {message}",
                snackbar_x="10dp",
                snackbar_y="10dp",
                size_hint_x=0.9,
                duration=duration,
                bg_color=(0.0, 0.68, 0.57, 1),
            ).open()
        except Exception as e:
            self.logger.error(f"Failed to show success notification: {e}")

    def _show_error_notification(self, message: str, duration: float = 3.0):
        """Show error notification using Snackbar"""
        try:
            Snackbar(
                text=f"❌ {message}",
                snackbar_x="10dp",
                snackbar_y="10dp",
                size_hint_x=0.9,
                duration=duration,
                bg_color=(0.96, 0.4, 0.3, 1),
            ).open()
        except Exception as e:
            self.logger.error(f"Failed to show error notification: {e}")

    def _show_warning_notification(self, message: str, duration: float = 2.5):
        """Show warning notification using Snackbar"""
        try:
            Snackbar(
                text=f"⚠️ {message}",
                snackbar_x="10dp",
                snackbar_y="10dp",
                size_hint_x=0.9,
                duration=duration,
                bg_color=(1.0, 0.6, 0.0, 1),
            ).open()
        except Exception as e:
            self.logger.error(f"Failed to show warning notification: {e}")

    def _show_info_notification(self, message: str, duration: float = 2.0):
        """Show info notification using Snackbar"""
        try:
            Snackbar(
                text=f"ℹ️ {message}",
                snackbar_x="10dp",
                snackbar_y="10dp",
                size_hint_x=0.9,
                duration=duration,
                bg_color=(0.12, 0.55, 0.76, 1),
            ).open()
        except Exception as e:
            self.logger.error(f"Failed to show info notification: {e}")

    # ------------------------------------------------------------------
    # Application Lifecycle
    # ------------------------------------------------------------------

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
    from src.data.database import DatabaseManager
    from src.communication.cloud_sync_manager import CloudSyncManager
    from src.communication.sync_scheduler import SyncScheduler
    
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
    
    # ============================================================
    # CRITICAL FIX: Initialize DatabaseManager
    # ============================================================
    database = None
    try:
        database = DatabaseManager(config)
        logger.info("✅ DatabaseManager initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize DatabaseManager: {e}")
        logger.warning("App will run with fallback local database only")
    
    # ============================================================
    # CRITICAL FIX: Initialize CloudSyncManager and SyncScheduler
    # ============================================================
    cloud_sync = None
    sync_scheduler = None
    
    if database and config.get('cloud', {}).get('enabled', False):
        try:
            # Initialize CloudSyncManager
            cloud_sync = CloudSyncManager(database, config['cloud'])
            logger.info("✅ CloudSyncManager initialized successfully")
            
            # Initialize and start SyncScheduler for auto-sync
            sync_mode = config['cloud'].get('sync', {}).get('mode', 'auto')
            if sync_mode == 'auto':
                interval = config['cloud'].get('sync', {}).get('interval_seconds', 300)
                sync_scheduler = SyncScheduler(cloud_sync, interval_seconds=interval)
                sync_scheduler.start()
                logger.info(f"✅ SyncScheduler started (auto-sync every {interval}s)")
            else:
                logger.info(f"Sync mode is '{sync_mode}', auto-sync disabled")
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize CloudSync: {e}")
            logger.warning("App will run without cloud sync")
    else:
        if not database:
            logger.warning("CloudSync disabled: DatabaseManager not available")
        else:
            logger.info("CloudSync disabled in config")
    
    try:
        # Create and run app with real sensor integration
        app = HealthMonitorApp(
            config=config,
            sensors=None,  # Will create from config
            database=database,  # ✅ FIX: Pass DatabaseManager instance
            mqtt_client=None,
            alert_system=None
        )
        app.run()
    except Exception as e:
        logger.error(f"Error running app: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Cleanup: Stop sync scheduler
        if sync_scheduler:
            try:
                sync_scheduler.stop()
                logger.info("✅ SyncScheduler stopped")
            except Exception as e:
                logger.error(f"Error stopping SyncScheduler: {e}")


if __name__ == '__main__':
    main()