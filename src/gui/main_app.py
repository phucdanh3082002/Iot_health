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
from kivy.config import Config

# ============================================================
# IMPORTANT: Config MUST be set BEFORE importing MDApp
# ============================================================
Config.set('graphics', 'width', '480')
Config.set('graphics', 'height', '320')
Config.set('graphics', 'resizable', False)
Config.set('graphics', 'fullscreen', 'auto')
Config.set('graphics', 'show_cursor', False)

from kivy.uix.screenmanager import ScreenManager
from kivy.clock import Clock
from kivymd.app import MDApp
from kivymd.uix.snackbar import Snackbar

# GPIO for physical emergency button
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except (ImportError, RuntimeError):
    GPIO_AVAILABLE = False
    logging.warning("RPi.GPIO not available - physical emergency button disabled")

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
from src.gui.mqtt_integration import GUIMQTTIntegration

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
    # GPIO Emergency Button Setup
    # ------------------------------------------------------------------
    
    def _setup_gpio_emergency_button(self):
        """
        Setup GPIO interrupt for physical emergency button (Active-Low)
        
        Hardware:
        - BCM GPIO pin from config (app.emergency_button_gpio)
        - Button type: Active-Low (Normally Open to GND)
        - Nhả (RELEASED): GPIO = HIGH (1) - internal pull-up keeps it HIGH
        - Nhấn (PRESSED):  GPIO = LOW  (0) - button connects GPIO to GND
        - Debounce: 300ms
        
        Configuration:
        - GPIO.PUD_UP: Enable internal pull-up resistor (kéo GPIO HIGH)
        - GPIO.FALLING: Detect falling edge (HIGH → LOW) = button press
        - Fallback: Polling mode if edge detection fails
        """
        if not GPIO_AVAILABLE:
            self.logger.info("⚠️ GPIO not available - physical emergency button disabled")
            return
        
        try:
            # Set GPIO mode
            GPIO.setmode(GPIO.BCM)
            
            # Setup GPIO input with internal pull-up
            # This makes GPIO = HIGH when button is released
            GPIO.setup(self.EMERGENCY_BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            
            # Try edge detection first (preferred method)
            try:
                # Add interrupt on falling edge (button press = GPIO goes LOW)
                GPIO.add_event_detect(
                    self.EMERGENCY_BUTTON_GPIO,
                    GPIO.FALLING,  # Trigger on HIGH → LOW transition (button press)
                    callback=self._on_physical_emergency_pressed,
                    bouncetime=300  # 300ms debounce (prevent multiple triggers from noise)
                )
                
                self.gpio_emergency_enabled = True
                self.gpio_polling_mode = False
                self.logger.info(f"✅ GPIO emergency button setup on GPIO {self.EMERGENCY_BUTTON_GPIO} (edge detection)")
                
            except RuntimeError as e:
                # Edge detection failed - fallback to polling mode
                if "Failed to add edge detection" in str(e) or "Conflicting edge detection" in str(e):
                    self.logger.warning(f"Edge detection failed: {e}")
                    self.logger.info("🔄 Falling back to polling mode...")
                    
                    # Start polling thread
                    self.gpio_emergency_enabled = True
                    self.gpio_polling_mode = True
                    self.gpio_last_state = GPIO.input(self.EMERGENCY_BUTTON_GPIO)
                    self.gpio_polling_active = True
                    
                    # Schedule polling check every 100ms
                    Clock.schedule_interval(self._poll_gpio_button, 0.1)
                    
                    self.logger.info(f"✅ GPIO emergency button setup on GPIO {self.EMERGENCY_BUTTON_GPIO} (polling mode)")
                else:
                    raise
            
        except Exception as e:
            self.logger.error(f"Failed to setup GPIO emergency button: {e}")
            self.gpio_emergency_enabled = False
            self.gpio_polling_mode = False
    
    def _poll_gpio_button(self, dt):
        """
        Poll GPIO button state (fallback when edge detection fails)
        
        Args:
            dt: Delta time from Clock.schedule_interval
        
        Returns:
            True to keep polling, False to stop (only on critical error)
        """
        # Skip polling if temporarily disabled (during debounce)
        # but DON'T stop the polling loop
        if not self.gpio_polling_active:
            return True  # Keep polling loop alive, just skip this iteration
        
        try:
            current_state = GPIO.input(self.EMERGENCY_BUTTON_GPIO)
            
            # Detect falling edge (button press: HIGH → LOW)
            if self.gpio_last_state == 1 and current_state == 0:
                self.logger.critical(f"🚨 PHYSICAL EMERGENCY BUTTON PRESSED (GPIO {self.EMERGENCY_BUTTON_GPIO}) [polling]")
                
                # Trigger emergency handler on main thread
                Clock.schedule_once(lambda dt: self._trigger_emergency_from_gpio(), 0)
                
                # Temporarily disable polling to prevent multiple triggers
                # This simulates hardware debounce
                self.gpio_polling_active = False
                Clock.schedule_once(self._reset_gpio_polling, 0.3)  # 300ms debounce
            
            # Always update last state (even when polling is disabled)
            self.gpio_last_state = current_state
            
        except Exception as e:
            self.logger.error(f"Error polling GPIO: {e}")
            return False  # Only stop polling on critical error
        
        return True  # Keep polling loop running
    
    def _reset_gpio_polling(self, dt):
        """Re-enable polling after debounce period.
        
        Args:
            dt: Delta time from Clock.schedule_once (required by Kivy)
        """
        self.gpio_polling_active = True
        self.gpio_last_state = GPIO.input(self.EMERGENCY_BUTTON_GPIO)
    
    def _on_physical_emergency_pressed(self, channel):
        """
        GPIO interrupt callback - physical emergency button pressed
        
        Args:
            channel: GPIO channel number (configured in app.emergency_button_gpio)
        """
        self.logger.critical(f"🚨 PHYSICAL EMERGENCY BUTTON PRESSED (GPIO {channel})")
        
        # Schedule on main thread (GPIO callback runs in separate thread)
        Clock.schedule_once(lambda dt: self._trigger_emergency_from_gpio(), 0)
    
    def _trigger_emergency_from_gpio(self):
        """
        Trigger emergency from GPIO button (runs on main Kivy thread)
        
        Logic:
        1. Get emergency button from dashboard screen
        2. Trigger same flow as GUI button
        3. If dashboard not available, fallback to direct MQTT alert
        """
        try:
            # Try to get dashboard screen's emergency button
            if self.screen_manager and hasattr(self.screen_manager, 'get_screen'):
                try:
                    dashboard = self.screen_manager.get_screen('dashboard')
                    if hasattr(dashboard, 'emergency_button'):
                        # Trigger GUI emergency button
                        dashboard.emergency_button._on_emergency_pressed(None)
                        self.logger.info("✅ Triggered GUI emergency button from GPIO")
                        return
                except Exception as e:
                    self.logger.warning(f"Could not access dashboard emergency button: {e}")
            
            # Fallback: Direct emergency handling
            self.logger.warning("Dashboard unavailable - using fallback emergency handling")
            self._speak_scenario(ScenarioID.EMERGENCY_BUTTON_PRESSED)
            
            # Send MQTT emergency alert directly
            if self.mqtt_integration:
                alert_data = {
                    'timestamp': time.time(),
                    'device_id': self.device_id,
                    'patient_id': self.patient_id,
                    'alert_type': 'emergency_button_physical',
                    'severity': 'critical',
                    'message': f'Physical emergency button pressed (GPIO {self.EMERGENCY_BUTTON_GPIO})',
                    'vital_sign': None,
                    'current_value': None,
                    'threshold_value': None,
                }
                self.mqtt_integration.mqtt_client.publish_alert(alert_data)
                self.logger.info("📡 Emergency MQTT alert sent from fallback")
            
        except Exception as e:
            self.logger.error(f"Error handling GPIO emergency: {e}", exc_info=True)
    
    def _cleanup_gpio(self):
        """
        Cleanup GPIO on app shutdown
        """
        if self.gpio_emergency_enabled and GPIO_AVAILABLE:
            try:
                # Stop polling if active
                if self.gpio_polling_mode:
                    self.gpio_polling_active = False
                    self.logger.info("🛑 GPIO polling stopped")
                
                GPIO.cleanup(self.EMERGENCY_BUTTON_GPIO)
                self.logger.info(f"✅ GPIO {self.EMERGENCY_BUTTON_GPIO} cleaned up")
            except Exception as e:
                self.logger.error(f"Error cleaning up GPIO: {e}")
    
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
        
        # Device identification (device-centric approach)
        self.device_id = (
            config.get('cloud', {}).get('device', {}).get('device_id')
            or config.get('communication', {}).get('mqtt', {}).get('device_id', 'rpi_bp_001')
        )
        
        # Cached patient_id (resolved from cloud via device_id)
        self._cached_patient_id: Optional[str] = None
        self._patient_id_resolved_at: Optional[float] = None
        
        # Initialize MQTT integration helper
        # Device-centric: patient_id will be resolved from cloud database
        self.mqtt_integration = None
        if self.mqtt_client:
            from src.gui.mqtt_integration import GUIMQTTIntegration
            self.mqtt_integration = GUIMQTTIntegration(
                mqtt_client=self.mqtt_client,
                device_id=self.device_id,
                patient_id=None,  # Resolved dynamically from cloud
                logger=logging.getLogger('mqtt_integration')
            )
        
        # Initialize sensors from config or use provided ones
        if sensors is None:
            self.sensors = self._create_sensors_from_config()
        else:
            self.sensors = self._normalize_sensor_keys(sensors)

        self.tts_manager = self._init_tts_manager()
        self._hr_finger_present: Optional[bool] = None
        self._hr_last_announced: Optional[tuple[int, int]] = None
        self._hr_result_announced_this_session: bool = False  # Track nếu đã đọc kết quả trong session
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
        
        # GPIO Emergency Button (Physical)
        self.gpio_emergency_enabled = False
        self.gpio_polling_mode = False  # True if using polling instead of edge detection
        self.gpio_polling_active = False  # Polling state (paused during debounce)
        self.gpio_last_state = 1  # Track last GPIO state for polling
        gpio_cfg = self.config_data.get('app', {}).get('emergency_button_gpio', 25)
        try:
            self.EMERGENCY_BUTTON_GPIO = int(gpio_cfg)
        except (TypeError, ValueError):
            self.logger.warning(
                "Invalid app.emergency_button_gpio=%r, defaulting to 25", gpio_cfg
            )
            self.EMERGENCY_BUTTON_GPIO = 25
        self._setup_gpio_emergency_button()

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
                        # Truyền speak_callback vào BloodPressureSensor
                        sensor = BloodPressureSensor('BloodPressure', bp_config, speak_callback=self._speak_scenario)
                        self.logger.info("🔧 BloodPressure sensor object created, calling initialize()...")
                        if sensor.initialize():
                            sensors['BloodPressure'] = sensor
                            self.logger.info("✅ BloodPressure sensor created and initialized successfully")
                        else:
                            self.logger.warning("⚠️  BloodPressure sensor.initialize() returned False")
                            # TTS cho lỗi khởi tạo cảm biến huyết áp (nếu không thể khởi tạo)
                            self._speak_scenario(ScenarioID.SENSOR_FAILURE, sensor="BloodPressure")
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
            
            # ============================================================
            # TTS LOGIC: KHÔNG đọc kết quả ở đây!
            # Kết quả sẽ được đọc trong on_measurement_complete() của HeartRateScreen
            # để đảm bảo đọc đúng giá trị cuối cùng sau khi controller kết thúc đo
            # ============================================================
            measurement_ready = bool(self.current_data.get('measurement_ready', False))
            session_active = bool(self.current_data.get('sensor_status', {}).get('MAX30102', {}).get('session_active', False))
            
            # Reset flag khi session mới bắt đầu
            if session_active and not measurement_ready:
                self._hr_result_announced_this_session = False
            
            # Reset khi finger rời
            if not finger_detected:
                self._hr_last_announced = None
                self._hr_result_announced_this_session = False
                
            # Cảnh báo tín hiệu yếu (chỉ khi đang đo, chưa ready)
            if finger_detected and not hr_valid and session_active and not measurement_ready:
                signal_quality = self.current_data.get('signal_quality_ir')
                if isinstance(signal_quality, (int, float)) and signal_quality < 40:
                    self._speak_scenario(ScenarioID.HR_SIGNAL_WEAK)
            
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
        # Device-centric: resolve patient_id from cloud database
        patient_id = self._resolve_patient_id_from_device()
        
        self.logger.debug(f"get_history_records called: patient_id={patient_id}, device_id={self.device_id}, start_time={start_time}")

        if self.database and hasattr(self.database, 'get_health_records'):
            try:
                # Device-centric: pass device_id as PRIMARY, patient_id as secondary
                records = self.database.get_health_records(
                    patient_id=patient_id,
                    device_id=self.device_id,
                    start_time=start_time,
                    end_time=end_time,
                    limit=limit,
                )
                self.logger.debug(f"DatabaseManager returned {len(records) if records else 0} records")
                if records:
                    return records
                else:
                    self.logger.warning("DatabaseManager returned 0 records, trying fallback...")
            except Exception as exc:
                self.logger.error("Database history retrieval failed: %s", exc, exc_info=True)

        db_path = project_root / "data" / "health_monitor.db"
        if not db_path.exists():
            return []

        # Query schema health_records (không phải vitals cũ)
        query = "SELECT id, timestamp, heart_rate, spo2, temperature, systolic_bp, diastolic_bp FROM health_records"
        filters: List[str] = []
        params: List[Any] = []
        
        # Device-centric: filter by device_id if patient_id is None
        if patient_id:
            filters.append("patient_id = ?")
            params.append(patient_id)
        elif self.device_id:
            filters.append("device_id = ?")
            params.append(self.device_id)
            
        if start_time:
            filters.append("timestamp >= ?")
            params.append(start_time.isoformat())
        if end_time:
            filters.append("timestamp <= ?")
            params.append(end_time.isoformat())
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(int(limit))

        results: List[Dict[str, Any]] = []
        try:
            with closing(sqlite3.connect(db_path)) as conn:
                conn.row_factory = sqlite3.Row
                with closing(conn.cursor()) as cursor:
                    cursor.execute(query, params)
                    for row in cursor.fetchall():
                        try:
                            ts = datetime.fromisoformat(row["timestamp"].strip()) if row["timestamp"] else None
                        except (ValueError, AttributeError):
                            ts = None
                        results.append(
                            {
                                'id': row['id'],
                                'timestamp': ts,
                                'heart_rate': row['heart_rate'],
                                'spo2': row['spo2'],
                                'temperature': row['temperature'],
                                'blood_pressure_systolic': row['systolic_bp'],
                                'blood_pressure_diastolic': row['diastolic_bp'],
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
            # ============================================================
            # Ưu tiên dùng DatabaseManager nếu có
            # ============================================================
            if self.database and hasattr(self.database, 'save_health_record'):
                try:
                    # Device-centric approach: patient_id sẽ được auto-resolve từ cloud
                    # Không đọc từ config nữa, để NULL và cloud sync sẽ xử lý
                    patient_id = None
                    
                    # Chuẩn bị data theo format của DatabaseManager.save_health_record()
                    timestamp_value = measurement_data.get('timestamp', time.time())
                    # Convert timestamp to datetime object if needed
                    # IMPORTANT: Use naive datetime (no timezone) for consistency with queries
                    if isinstance(timestamp_value, (int, float)):
                        timestamp_dt = datetime.fromtimestamp(timestamp_value)
                    elif isinstance(timestamp_value, datetime):
                        # Remove timezone info if present to keep naive datetime
                        timestamp_dt = timestamp_value.replace(tzinfo=None) if timestamp_value.tzinfo else timestamp_value
                    else:
                        timestamp_dt = datetime.now()
                    
                    self.logger.debug(f"Saving with timestamp: {timestamp_dt} (type: {type(timestamp_dt)})")
                    
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
                        
                        # ============================================================
                        # MQTT PUBLISHING: Publish vitals to MQTT broker
                        # ============================================================
                        if self.mqtt_integration:
                            # Determine measurement type
                            measurement_type = 'heart_rate'
                            if health_data.get('temperature'):
                                measurement_type = 'temperature'
                            elif health_data.get('systolic_bp'):
                                measurement_type = 'blood_pressure'
                            
                            # Publish vitals
                            self.mqtt_integration.publish_vitals_from_measurement(
                                measurement_data=measurement_data,
                                measurement_type=measurement_type
                            )
                        
                        return record_id
                    else:
                        self.logger.warning("DatabaseManager.save_health_record() returned None - falling back to local DB")
                        
                except Exception as exc:
                    self.logger.error(f"DatabaseManager save failed: {exc}", exc_info=True)
                    self.logger.warning("Falling back to local health_monitor.db")

            # Fallback về SQLite cục bộ nếu DatabaseManager fail hoặc không có
            if self._save_to_local_vitals(measurement_data):
                self.logger.info("Measurement saved to local health_monitor.db (fallback)")
                self._show_success_notification("Đã lưu kết quả (local)", duration=2)
            else:
                self.logger.error("Unable to persist measurement data to any database")
                self._show_error_notification("Không thể lưu dữ liệu vào database")
                
        except Exception as e:
            self.logger.error(f"Critical error in save_measurement_to_database: {e}", exc_info=True)
            self._show_error_notification(f"Lỗi khi lưu: {str(e)}")

    def _resolve_patient_id_from_device(self) -> Optional[str]:
        """
        Resolve patient_id từ device_id thông qua cloud database
        Cache kết quả trong 5 phút để giảm query
        
        Returns:
            patient_id nếu tìm được, None nếu không
        """
        try:
            # Check cache (valid for 5 minutes)
            if self._cached_patient_id and self._patient_id_resolved_at:
                cache_age = time.time() - self._patient_id_resolved_at
                if cache_age < 300:  # 5 minutes
                    return self._cached_patient_id
            
            # ============================================================
            # PRIORITY 1: Query from cloud database (source of truth)
            # ============================================================
            try:
                from src.communication.cloud_sync_manager import CloudSyncManager
                from sqlalchemy import text
                
                # Try to get CloudSyncManager from main.py global context
                # or create a temporary connection
                cloud_config = self.config_data.get('cloud', {})
                if cloud_config.get('enabled', False):
                    mysql_config = cloud_config.get('mysql', {})
                    if mysql_config:
                        from sqlalchemy import create_engine
                        
                        # Build connection string
                        host = mysql_config.get('host')
                        port = mysql_config.get('port', 3306)
                        database = mysql_config.get('database')
                        user = mysql_config.get('user')
                        
                        # Get password from environment or config
                        import os
                        password = os.environ.get('MYSQL_PASSWORD') or mysql_config.get('password', '')
                        
                        if host and database and user and password:
                            connection_string = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
                            engine = create_engine(connection_string, pool_pre_ping=True)
                            
                            with engine.connect() as conn:
                                result = conn.execute(
                                    text("SELECT patient_id FROM patients WHERE device_id = :device_id AND is_active = 1 LIMIT 1"),
                                    {'device_id': self.device_id}
                                )
                                row = result.fetchone()
                                if row:
                                    self._cached_patient_id = row[0]
                                    self._patient_id_resolved_at = time.time()
                                    self.logger.debug(f"[Resolved patient_id from CLOUD] {self._cached_patient_id}")
                                    engine.dispose()
                                    return self._cached_patient_id
                            
                            engine.dispose()
                            
            except Exception as cloud_err:
                self.logger.debug(f"Cloud patient resolution failed: {cloud_err}")
            
            # ============================================================
            # PRIORITY 2: Fallback to local database
            # ============================================================
            if self.database and hasattr(self.database, 'get_session'):
                try:
                    with self.database.get_session() as session:
                        from src.data.models import Patient
                        patient = session.query(Patient).filter(
                            Patient.device_id == self.device_id,
                            Patient.is_active == True
                        ).first()
                        
                        if patient:
                            self._cached_patient_id = patient.patient_id
                            self._patient_id_resolved_at = time.time()
                            self.logger.debug(f"[Resolved patient_id from LOCAL] {self._cached_patient_id}")
                            return self._cached_patient_id
                except Exception as local_err:
                    self.logger.debug(f"Local patient resolution failed: {local_err}")
            
            return None
            
        except Exception as e:
            self.logger.warning(f"Could not resolve patient_id from device: {e}")
            return None
    
    def _get_default_thresholds_from_config(self) -> Dict[str, Dict[str, float]]:
        """
        Lấy ngưỡng mặc định từ app_config.yaml
        
        Returns:
            Dictionary thresholds theo format của get_patient_thresholds()
        """
        # Đọc từ threshold_management.baseline (format mới)
        baseline = self.config_data.get('threshold_management', {}).get('baseline', {})
        
        result = {}
        
        # Heart rate thresholds
        if 'heart_rate' in baseline:
            result['heart_rate'] = baseline['heart_rate']
        else:
            result['heart_rate'] = {
                'min_normal': 60,
                'max_normal': 100,
                'min_critical': 40,
                'max_critical': 120
            }
        
        # SpO2 thresholds
        if 'spo2' in baseline:
            result['spo2'] = baseline['spo2']
        else:
            result['spo2'] = {
                'min_normal': 95,
                'max_normal': 100,
                'min_critical': 85,
                'max_critical': 100
            }
        
        # Temperature thresholds
        if 'temperature' in baseline:
            result['temperature'] = baseline['temperature']
        else:
            result['temperature'] = {
                'min_normal': 36.1,
                'max_normal': 37.2,
                'min_critical': 35.0,
                'max_critical': 39.0
            }
        
        # Blood pressure thresholds
        if 'systolic_bp' in baseline:
            result['systolic_bp'] = baseline['systolic_bp']
        else:
            result['systolic_bp'] = {
                'min_normal': 90,
                'max_normal': 120,
                'min_critical': 80,
                'max_critical': 180
            }
            result['diastolic_bp'] = {
                'min_normal': 60,
                'max_normal': 90,
                'min_critical': 40,
                'max_critical': 110
            }
        
        return result
    
    def _check_and_create_alert_immediate(self, health_data: Dict[str, Any]):
        """
        Kiểm tra ngưỡng và phát TTS cảnh báo NGAY LẬP TỨC (không chờ lưu DB)
        
        Gọi từ on_measurement_complete() để TTS đọc cảnh báo ngay sau khi đo xong
        Cảnh báo thực sự sẽ được lưu vào DB khi user nhấn "Lưu"
        
        Args:
            health_data: Health record data với heart_rate, spo2, etc.
        """
        try:
            # ============================================================
            # IMMEDIATE CHECK: Chỉ lấy default thresholds từ config
            # Không query database (để speed up)
            # ============================================================
            thresholds = self._get_default_thresholds_from_config()
            if not thresholds:
                self.logger.debug("No thresholds available for immediate alert check")
                return
            
            # Helper function để lấy threshold value
            def get_threshold(vital_sign: str, bound: str, default: float) -> float:
                if vital_sign in thresholds and isinstance(thresholds[vital_sign], dict):
                    return thresholds[vital_sign].get(bound, default)
                return thresholds.get(f"{vital_sign}_{bound}", default)
            
            alerts_to_announce = []
            
            # ============================================================
            # Kiểm tra Heart Rate
            # ============================================================
            hr = health_data.get('heart_rate')
            if hr and hr > 0:
                hr_min = get_threshold('heart_rate', 'min_normal', 60)
                hr_max = get_threshold('heart_rate', 'max_normal', 100)
                hr_critical_min = get_threshold('heart_rate', 'min_critical', 40)
                hr_critical_max = get_threshold('heart_rate', 'max_critical', 150)
                
                if hr < hr_min:
                    severity = 'critical' if hr < hr_critical_min else 'medium'
                    alerts_to_announce.append({
                        'message': f'Cảnh báo: Nhịp tim thấp {hr:.0f} BPM',
                        'severity': severity
                    })
                elif hr > hr_max:
                    severity = 'critical' if hr > hr_critical_max else 'high'
                    alerts_to_announce.append({
                        'message': f'Cảnh báo: Nhịp tim cao {hr:.0f} BPM',
                        'severity': severity
                    })
            
            # ============================================================
            # Kiểm tra SpO2
            # ============================================================
            spo2 = health_data.get('spo2')
            if spo2 and spo2 > 0:
                spo2_min = get_threshold('spo2', 'min_normal', 95)
                spo2_critical_min = get_threshold('spo2', 'min_critical', 90)
                
                if spo2 < spo2_min:
                    severity = 'critical' if spo2 < spo2_critical_min else 'high'
                    alerts_to_announce.append({
                        'message': f'Cảnh báo: SpO2 thấp {spo2:.0f}%',
                        'severity': severity
                    })
            
            # ============================================================
            # TTS: Phát cảnh báo nếu có
            # ============================================================
            for alert in alerts_to_announce:
                self.logger.warning(f"Alert (immediate): {alert['message']} (severity={alert['severity']})")
                # Phát TTS cảnh báo
                self.speak_text(alert['message'], force=True)
                
        except Exception as e:
            self.logger.error(f"Error in immediate alert check: {e}")
    
    def _check_and_create_alert(self, patient_id: str, health_data: Dict[str, Any], record_id: int):
        """
        Kiểm tra ngưỡng và tạo alert tự động nếu vượt threshold
        
        Device-centric approach:
        1. Resolve patient_id từ device_id nếu patient_id = None
        2. Lấy thresholds từ patient_thresholds (cloud/local)
        3. Fallback về thresholds từ config nếu không có
        
        Args:
            patient_id: Patient ID (có thể None với device-centric)
            health_data: Health record data
            record_id: ID của health record vừa lưu
        """
        try:
            # ============================================================
            # STEP 1: Resolve patient_id từ device_id nếu cần
            # ============================================================
            resolved_patient_id = patient_id
            if not resolved_patient_id:
                resolved_patient_id = self._resolve_patient_id_from_device()
                if resolved_patient_id:
                    self.logger.info(f"[Alert] Resolved patient_id: {resolved_patient_id} for device {self.device_id}")
                    # Update MQTT integration with resolved patient_id
                    if self.mqtt_integration:
                        self.mqtt_integration.patient_id = resolved_patient_id
            
            # ============================================================
            # STEP 2: Lấy thresholds từ database hoặc config
            # ============================================================
            thresholds = {}
            
            # Try patient-specific thresholds first
            if resolved_patient_id and self.database and hasattr(self.database, 'get_patient_thresholds'):
                thresholds = self.database.get_patient_thresholds(resolved_patient_id)
                if thresholds:
                    self.logger.debug(f"Using patient thresholds for {resolved_patient_id}")
            
            # Fallback to config thresholds
            if not thresholds:
                thresholds = self._get_default_thresholds_from_config()
                self.logger.debug(f"Using default thresholds from config (patient={resolved_patient_id})")
            
            if not thresholds:
                self.logger.warning("No thresholds available (neither patient nor config)")
                return
            
            alerts = []
            
            # ============================================================
            # Helper function để lấy threshold value (hỗ trợ cả 2 formats)
            # Format 1 (database): {'heart_rate': {'min_normal': 60, 'max_normal': 100}}
            # Format 2 (legacy): {'heart_rate_min': 60, 'heart_rate_max': 100}
            # ============================================================
            def get_threshold(vital_sign: str, bound: str, default: float) -> float:
                """Get threshold value, supporting both nested and flat formats"""
                # Try nested format first (from database/config)
                if vital_sign in thresholds and isinstance(thresholds[vital_sign], dict):
                    return thresholds[vital_sign].get(bound, default)
                # Try flat format (legacy)
                flat_key = f"{vital_sign}_{bound.replace('_normal', '').replace('_critical', '_critical')}"
                if bound == 'min_normal':
                    flat_key = f"{vital_sign}_min"
                elif bound == 'max_normal':
                    flat_key = f"{vital_sign}_max"
                return thresholds.get(flat_key, default)
            
            # Kiểm tra Heart Rate
            hr = health_data.get('heart_rate')
            if hr and hr > 0:
                hr_min = get_threshold('heart_rate', 'min_normal', 60)
                hr_max = get_threshold('heart_rate', 'max_normal', 100)
                hr_critical_min = get_threshold('heart_rate', 'min_critical', 40)
                hr_critical_max = get_threshold('heart_rate', 'max_critical', 150)
                
                if hr < hr_min:
                    severity = 'critical' if hr < hr_critical_min else 'medium'
                    alerts.append({
                        'type': 'low_heart_rate',
                        'severity': severity,
                        'message': f'Nhịp tim thấp: {hr:.0f} BPM (ngưỡng: {hr_min}-{hr_max})',
                        'value': hr,
                        'vital_sign': 'heart_rate',
                        'threshold': hr_min
                    })
                elif hr > hr_max:
                    severity = 'critical' if hr > hr_critical_max else 'high'
                    alerts.append({
                        'type': 'high_heart_rate',
                        'severity': severity,
                        'message': f'Nhịp tim cao: {hr:.0f} BPM (ngưỡng: {hr_min}-{hr_max})',
                        'value': hr,
                        'vital_sign': 'heart_rate',
                        'threshold': hr_max
                    })
            
            # Kiểm tra SpO2
            spo2 = health_data.get('spo2')
            if spo2 and spo2 > 0:
                spo2_min = get_threshold('spo2', 'min_normal', 95)
                spo2_critical_min = get_threshold('spo2', 'min_critical', 90)
                
                if spo2 < spo2_min:
                    severity = 'critical' if spo2 < spo2_critical_min else 'high'
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
                temp_min = get_threshold('temperature', 'min_normal', 36.0)
                temp_max = get_threshold('temperature', 'max_normal', 37.5)
                temp_critical_min = get_threshold('temperature', 'min_critical', 35.0)
                temp_critical_max = get_threshold('temperature', 'max_critical', 39.0)
                
                if temp < temp_min:
                    severity = 'critical' if temp < temp_critical_min else 'medium'
                    alerts.append({
                        'type': 'low_temperature',
                        'severity': severity,
                        'message': f'Nhiệt độ thấp: {temp:.1f}°C (ngưỡng: {temp_min}-{temp_max})',
                        'value': temp,
                        'vital_sign': 'temperature',
                        'threshold': temp_min
                    })
                elif temp > temp_max:
                    severity = 'critical' if temp > temp_critical_max else 'high'
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
                sys_min = get_threshold('systolic_bp', 'min_normal', 90)
                sys_max = get_threshold('systolic_bp', 'max_normal', 140)
                sys_critical_max = get_threshold('systolic_bp', 'max_critical', 180)
                dia_min = get_threshold('diastolic_bp', 'min_normal', 60)
                dia_max = get_threshold('diastolic_bp', 'max_normal', 90)
                dia_critical_max = get_threshold('diastolic_bp', 'max_critical', 110)
                
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
                    severity = 'critical' if systolic > sys_critical_max or diastolic > dia_critical_max else 'high'
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
                        # Device-centric: use device_id if patient_id is None
                        active_alerts = self.database.get_active_alerts(
                            patient_id=resolved_patient_id,
                            device_id=self.device_id
                        )
                        
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
                        # Device-centric approach: use resolved_patient_id (can still be None)
                        alert_dict = {
                            'patient_id': resolved_patient_id,  # Use resolved patient_id
                            'device_id': self.device_id,  # Add device_id
                            'health_record_id': record_id,  # Link to health record
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
                            f"⚠️  Alert created: {alert_data['type']} (severity={alert_data['severity']}, "
                            f"alert_id={alert_id}, patient={resolved_patient_id}, device={self.device_id})"
                        )
                        
                        # ============================================================
                        # MQTT PUBLISHING: Publish alert to MQTT broker
                        # ============================================================
                        if self.mqtt_integration and alert_id:
                            # Get threshold range
                            threshold_val = alert_data.get('threshold')
                            if isinstance(threshold_val, str) and '/' in threshold_val:
                                # Blood pressure format "120/80"
                                parts = threshold_val.split('/')
                                threshold_min = float(parts[0]) if alert_data['type'].startswith('low') else 0
                                threshold_max = float(parts[0]) if alert_data['type'].startswith('high') else 999
                            else:
                                threshold_min = float(threshold_val) if alert_data['type'].startswith('low') else 0
                                threshold_max = float(threshold_val) if alert_data['type'].startswith('high') else 999
                            
                            # Convert value to float
                            value = alert_data.get('value')
                            if isinstance(value, str) and '/' in value:
                                # Blood pressure "120/80" -> use systolic
                                value = float(value.split('/')[0])
                            else:
                                value = float(value) if value else 0
                            
                            self.mqtt_integration.publish_alert_from_threshold_check(
                                alert_type=alert_data['type'],
                                severity=alert_data['severity'],
                                vital_sign=alert_data.get('vital_sign', 'unknown'),
                                current_value=value,
                                threshold_min=threshold_min,
                                threshold_max=threshold_max,
                                message=alert_data['message']
                            )
                        
                        # Gửi TTS warning nếu severity cao
                        if alert_data['severity'] in ('high', 'critical'):
                            self.speak_text(alert_data['message'], force=True)
                            
                except Exception as alert_exc:
                    self.logger.error(f"Failed to create alert: {alert_exc}")
                    
        except Exception as e:
            self.logger.error(f"Error checking thresholds and creating alerts: {e}", exc_info=True)

    def _save_to_local_vitals(self, measurement_data: Dict[str, Any]) -> bool:
        db_path = project_root / "data" / "health_monitor.db"
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
        
        # Cleanup GPIO emergency button
        self._cleanup_gpio()
        
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
        
        Publish device online status to MQTT
        """
        # Publish device online status
        if self.mqtt_integration:
            self.mqtt_integration.publish_device_status(
                online=True,
                sensors_status={'max30102': 'ready', 'mlx90614': 'ready', 'hx710b': 'ready'},
                system_info={'uptime': 0, 'memory_usage': 50.0}
            )
            self.logger.info("📡 Published device online status to MQTT")
    


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
    # Initialize MQTT Client
    # ============================================================
    mqtt_client = None
    try:
        from src.communication.mqtt_client import IoTHealthMQTTClient
        mqtt_client = IoTHealthMQTTClient(config)
        
        if not mqtt_client.connect():
            logger.error("❌ Failed to connect MQTT client")
            mqtt_client = None
        else:
            logger.info("✅ MQTT Client initialized and connected")
            logger.info("MQTT Client will resolve patient_id dynamically from cloud.")
            
    except Exception as e:
        logger.error(f"❌ Failed to initialize MQTT Client: {e}", exc_info=True)
        logger.warning("App will run without real-time MQTT communication")

    database = None
    try:
        database = DatabaseManager(config)
        logger.info("✅ DatabaseManager initialized successfully")
        
        # Initialize database and cloud sync
        if not database.initialize():
            logger.error("❌ Database initialization failed")
            database = None
        else:
            logger.info("✅ Database initialization completed")
    except Exception as e:
        logger.error(f"❌ Failed to initialize DatabaseManager: {e}")
        logger.warning("App will run with fallback local database only")
    
    # ============================================================
    # CRITICAL FIX: Initialize CloudSyncManager and SyncScheduler
    # ============================================================
    cloud_sync = None
    sync_scheduler = None
    
    # CloudSyncManager should already be initialized in database.initialize()
    # But explicitly set it here for clarity
    if database and database.cloud_sync_manager:
        cloud_sync = database.cloud_sync_manager
        logger.info("✅ CloudSyncManager ready (initialized via database)")
        
        # SyncScheduler should already be started
        if database.sync_scheduler:
            sync_scheduler = database.sync_scheduler
            logger.info("✅ SyncScheduler ready (started via database)")
    
    if not cloud_sync and database and config.get('cloud', {}).get('enabled', False):
        # Fallback: Try to initialize cloud sync manually
        try:
            cloud_sync = CloudSyncManager(database, config['cloud'])
            logger.info("✅ CloudSyncManager initialized (fallback)")
            
            # Initialize and start SyncScheduler for auto-sync
            sync_mode = config['cloud'].get('sync', {}).get('mode', 'auto')
            if sync_mode == 'auto':
                interval = config['cloud'].get('sync', {}).get('interval_seconds', 300)
                sync_scheduler = SyncScheduler(cloud_sync, interval_seconds=interval)
                sync_scheduler.start()
                logger.info(f"✅ SyncScheduler started (fallback, auto-sync every {interval}s)")
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize CloudSync (fallback): {e}")
            logger.warning("App will run without cloud sync")
    else:
        if not database:
            logger.warning("CloudSync disabled: DatabaseManager not available")
        else:
            logger.info("CloudSync already initialized or disabled in config")
    
    try:
        # Create and run app with real sensor integration
        app = HealthMonitorApp(
            config=config,
            sensors=None,  # Will create from config
            database=database,  # ✅ FIX: Pass DatabaseManager instance
            mqtt_client=mqtt_client, # Pass MQTT client instance
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
        
        # Cleanup: Disconnect MQTT client
        if mqtt_client:
            try:
                mqtt_client.disconnect()
                logger.info("✅ MQTT Client disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting MQTT Client: {e}")


if __name__ == '__main__':
    main()
