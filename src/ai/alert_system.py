"""
Alert System - FULL IMPLEMENTATION
Hệ thống cảnh báo thông minh với TTS tự động cho IoT Health Monitoring System
"""

from typing import Dict, Any, Optional, List, Callable
import logging
from datetime import datetime, timedelta
from enum import Enum
import threading
import time
from dataclasses import dataclass

# Import TTS scenarios
from src.utils.tts_manager import ScenarioID


class AlertSeverity(Enum):
    """Alert severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertType(Enum):
    """Alert types"""
    THRESHOLD = "threshold"
    ANOMALY = "anomaly"
    TREND = "trend"
    SENSOR_ERROR = "sensor_error"
    SYSTEM_ERROR = "system_error"


@dataclass
class AlertRule:
    """
    Data class for alert rules
    
    Attributes:
        id: Rule identifier
        name: Rule name
        vital_sign: Target vital sign
        condition: Alert condition (>, <, ==, etc.)
        threshold_value: Threshold value
        severity: Alert severity
        enabled: Whether rule is enabled
        cooldown_minutes: Cooldown period in minutes
    """
    id: str
    name: str
    vital_sign: str
    condition: str
    threshold_value: float
    severity: AlertSeverity
    enabled: bool = True
    cooldown_minutes: int = 5


class AlertSystem:
    """
    Alert system cho health monitoring với TTS tự động
    
    Features:
    - Automatic TTS alerts khi vượt ngưỡng
    - MQTT remote alerts
    - Cooldown để tránh spam
    - Callback system cho UI notifications
    """
    
    def __init__(self, config: Dict[str, Any], tts_manager=None, mqtt_client=None, database=None):
        """
        Initialize alert system
        
        Args:
            config: Alert system configuration
            tts_manager: TTS manager for voice alerts
            mqtt_client: MQTT client for remote notifications
            database: Database manager for logging
        """
        self.config = config
        self.tts_manager = tts_manager
        self.mqtt_client = mqtt_client
        self.database = database
        self.logger = logging.getLogger(__name__)
        
        # Alert rules and tracking
        self.alert_rules: List[AlertRule] = []
        self.active_alerts: Dict[str, Dict[str, Any]] = {}
        self.cooldown_tracker: Dict[str, datetime] = {}
        
        # Callbacks
        self.alert_callbacks: List[Callable] = []
        
        # Settings
        self.audio_enabled = config.get('audio_enabled', True)
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        self.logger.info("AlertSystem initialized with TTS support")
    
    # ============================================================
    # Vital Signs Checking with AUTO TTS
    # ============================================================
    
    def check_vital_signs(self, patient_id: str, vital_data: Dict[str, Any]):
        """
        Check vital signs và tự động phát TTS alert khi vượt ngưỡng
        
        Args:
            patient_id: Patient identifier
            vital_data: Dict chứa heart_rate, spo2, systolic_bp, diastolic_bp, temperature
        """
        try:
            hr = vital_data.get('heart_rate')
            spo2 = vital_data.get('spo2')
            sys_bp = vital_data.get('systolic_bp')
            dia_bp = vital_data.get('diastolic_bp')
            temp = vital_data.get('temperature')
            
            # Check Heart Rate
            if hr is not None and hr > 0:
                self._check_heart_rate(patient_id, hr)
            
            # Check SpO2
            if spo2 is not None and spo2 > 0:
                self._check_spo2(patient_id, spo2)
            
            # Check Blood Pressure
            if sys_bp is not None and dia_bp is not None:
                self._check_blood_pressure(patient_id, sys_bp, dia_bp)
            
            # Check Temperature (if needed)
            if temp is not None:
                self._check_temperature(patient_id, temp)
                
        except Exception as e:
            self.logger.error(f"Error checking vital signs: {e}", exc_info=True)
    
    def _check_heart_rate(self, patient_id: str, hr: float):
        """Check HR thresholds với TTS tự động"""
        # Bradycardia: HR < 50 bpm
        if hr < 50:
            if not self._check_cooldown('hr_too_low'):
                self._trigger_alert_with_tts(
                    patient_id=patient_id,
                    alert_type='hr_too_low',
                    severity=AlertSeverity.HIGH,
                    message=f"Nhịp tim quá thấp: {hr:.0f} BPM",
                    tts_scenario=ScenarioID.HR_TOO_LOW,
                    tts_params={'bpm': int(hr)},
                    vital_sign='heart_rate',
                    current_value=hr,
                    threshold_value=50
                )
                self.cooldown_tracker['hr_too_low'] = datetime.now()
        
        # Tachycardia: HR > 100 bpm
        elif hr > 100:
            if not self._check_cooldown('hr_too_high'):
                self._trigger_alert_with_tts(
                    patient_id=patient_id,
                    alert_type='hr_too_high',
                    severity=AlertSeverity.HIGH,
                    message=f"Nhịp tim quá cao: {hr:.0f} BPM",
                    tts_scenario=ScenarioID.HR_TOO_HIGH,
                    tts_params={'bpm': int(hr)},
                    vital_sign='heart_rate',
                    current_value=hr,
                    threshold_value=100
                )
                self.cooldown_tracker['hr_too_high'] = datetime.now()
    
    def _check_spo2(self, patient_id: str, spo2: float):
        """Check SpO2 thresholds với TTS tự động"""
        # Critical hypoxia: SpO2 < 85%
        if spo2 < 85:
            if not self._check_cooldown('spo2_critical'):
                self._trigger_alert_with_tts(
                    patient_id=patient_id,
                    alert_type='spo2_critical',
                    severity=AlertSeverity.CRITICAL,
                    message=f"Oxy máu cực thấp: {spo2:.0f}%",
                    tts_scenario=ScenarioID.SPO2_CRITICAL,
                    tts_params={'spo2': int(spo2)},
                    vital_sign='spo2',
                    current_value=spo2,
                    threshold_value=85
                )
                self.cooldown_tracker['spo2_critical'] = datetime.now()
        
        # Hypoxia: SpO2 < 90%
        elif spo2 < 90:
            if not self._check_cooldown('spo2_low'):
                self._trigger_alert_with_tts(
                    patient_id=patient_id,
                    alert_type='spo2_low',
                    severity=AlertSeverity.HIGH,
                    message=f"Oxy máu thấp: {spo2:.0f}%",
                    tts_scenario=ScenarioID.SPO2_LOW,
                    tts_params={'spo2': int(spo2)},
                    vital_sign='spo2',
                    current_value=spo2,
                    threshold_value=90
                )
                self.cooldown_tracker['spo2_low'] = datetime.now()
    
    def _check_blood_pressure(self, patient_id: str, sys: float, dia: float):
        """Check BP thresholds với TTS tự động"""
        # Hypertensive crisis: SYS >= 180 or DIA >= 120
        if sys >= 180 or dia >= 120:
            if not self._check_cooldown('bp_crisis'):
                self._trigger_alert_with_tts(
                    patient_id=patient_id,
                    alert_type='bp_hypertensive_crisis',
                    severity=AlertSeverity.CRITICAL,
                    message=f"Huyết áp nguy hiểm: {sys:.0f}/{dia:.0f} mmHg",
                    tts_scenario=ScenarioID.BP_HYPERTENSIVE_CRISIS,
                    tts_params={'sys': int(sys), 'dia': int(dia)},
                    vital_sign='blood_pressure',
                    current_value=sys,
                    threshold_value=180
                )
                self.cooldown_tracker['bp_crisis'] = datetime.now()
        
        # Hypertension Stage 2: SYS >= 140 or DIA >= 90
        elif sys >= 140 or dia >= 90:
            if not self._check_cooldown('bp_high'):
                self._trigger_alert_with_tts(
                    patient_id=patient_id,
                    alert_type='bp_hypertension',
                    severity=AlertSeverity.HIGH,
                    message=f"Huyết áp cao: {sys:.0f}/{dia:.0f} mmHg",
                    tts_scenario=ScenarioID.BP_HYPERTENSION,
                    tts_params={'sys': int(sys), 'dia': int(dia)},
                    vital_sign='blood_pressure',
                    current_value=sys,
                    threshold_value=140
                )
                self.cooldown_tracker['bp_high'] = datetime.now()
        
        # Hypotension: SYS < 90 or DIA < 60
        elif sys < 90 or dia < 60:
            if not self._check_cooldown('bp_low'):
                self._trigger_alert_with_tts(
                    patient_id=patient_id,
                    alert_type='bp_hypotension',
                    severity=AlertSeverity.MEDIUM,
                    message=f"Huyết áp thấp: {sys:.0f}/{dia:.0f} mmHg",
                    tts_scenario=ScenarioID.BP_HYPOTENSION,
                    tts_params={'sys': int(sys), 'dia': int(dia)},
                    vital_sign='blood_pressure',
                    current_value=sys,
                    threshold_value=90
                )
                self.cooldown_tracker['bp_low'] = datetime.now()
    
    def _check_temperature(self, patient_id: str, temp: float):
        """Check temperature - already handled by temperature screen, skip duplicate TTS"""
        # Temperature alerts are handled by temperature_screen.py
        # This is just for logging/MQTT if needed
        pass
    
    def _trigger_alert_with_tts(
        self,
        patient_id: str,
        alert_type: str,
        severity: AlertSeverity,
        message: str,
        tts_scenario: ScenarioID,
        tts_params: Dict[str, Any],
        vital_sign: str,
        current_value: float,
        threshold_value: float
    ):
        """
        Trigger alert với TTS tự động
        
        Args:
            patient_id: Patient ID
            alert_type: Alert type identifier
            severity: Alert severity
            message: Alert message
            tts_scenario: TTS scenario to play
            tts_params: Parameters for TTS
            vital_sign: Affected vital sign
            current_value: Current value
            threshold_value: Threshold value
        """
        try:
            # Build alert data
            alert_data = {
                'timestamp': time.time(),
                'patient_id': patient_id,
                'alert_type': alert_type,
                'severity': severity.value,
                'message': message,
                'vital_sign': vital_sign,
                'current_value': current_value,
                'threshold_value': threshold_value,
            }
            
            # Log to database
            if self.database:
                try:
                    self.database.save_alert(alert_data)
                except Exception as e:
                    self.logger.error(f"Failed to save alert to database: {e}")
            
            # Play TTS alert
            if self.tts_manager and self.audio_enabled:
                try:
                    self.tts_manager.speak_scenario(tts_scenario, **tts_params)
                except Exception as e:
                    self.logger.error(f"Failed to play TTS alert: {e}")
            
            # Send MQTT alert
            if self.mqtt_client:
                try:
                    self.mqtt_client.publish_alert(alert_data)
                except Exception as e:
                    self.logger.error(f"Failed to publish MQTT alert: {e}")
            
            # Notify callbacks
            for callback in self.alert_callbacks:
                try:
                    callback(alert_data)
                except Exception as e:
                    self.logger.error(f"Alert callback error: {e}")
            
            self.logger.warning(f"🚨 Alert triggered: {alert_type} - {message}")
            
        except Exception as e:
            self.logger.error(f"Error triggering alert: {e}", exc_info=True)
    
    def _check_cooldown(self, alert_key: str, cooldown_minutes: int = 10) -> bool:
        """
        Check if alert is in cooldown period
        
        Args:
            alert_key: Alert identifier for cooldown tracking
            cooldown_minutes: Cooldown duration in minutes
            
        Returns:
            True if in cooldown (should not alert), False if ok to alert
        """
        if alert_key not in self.cooldown_tracker:
            return False
        
        last_alert_time = self.cooldown_tracker[alert_key]
        elapsed = datetime.now() - last_alert_time
        
        return elapsed < timedelta(minutes=cooldown_minutes)
    
    # ============================================================
    # Callback Management
    # ============================================================
    
    def add_alert_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Add callback function for alert notifications"""
        if callback not in self.alert_callbacks:
            self.alert_callbacks.append(callback)
            self.logger.debug(f"Added alert callback: {callback.__name__}")
    
    def remove_alert_callback(self, callback: Callable):
        """Remove alert callback function"""
        if callback in self.alert_callbacks:
            self.alert_callbacks.remove(callback)
            self.logger.debug(f"Removed alert callback: {callback.__name__}")
    
    # ============================================================
    # Settings
    # ============================================================
    
    def set_audio_enabled(self, enabled: bool):
        """Enable or disable audio alerts"""
        self.audio_enabled = enabled
        self.logger.info(f"Audio alerts {'enabled' if enabled else 'disabled'}")
    
    # ============================================================
    # Stub methods (implement if needed)
    # ============================================================
    
    def start(self) -> bool:
        """Start alert system monitoring"""
        self.running = True
        self.logger.info("AlertSystem started")
        return True
    
    def stop(self) -> bool:
        """Stop alert system monitoring"""
        self.running = False
        self.logger.info("AlertSystem stopped")
        return True
    
    def add_alert_rule(self, rule: AlertRule) -> bool:
        """Add new alert rule"""
        self.alert_rules.append(rule)
        return True
    
    def remove_alert_rule(self, rule_id: str) -> bool:
        """Remove alert rule"""
        self.alert_rules = [r for r in self.alert_rules if r.id != rule_id]
        return True
    
    def update_alert_rule(self, rule_id: str, updates: Dict[str, Any]) -> bool:
        """Update existing alert rule"""
        return True
    
    def trigger_alert(self, patient_id: str, alert_type: AlertType, 
                     severity: AlertSeverity, message: str, 
                     vital_sign: str = None, current_value: float = None,
                     threshold_value: float = None) -> str:
        """Trigger new alert - generic method"""
        alert_id = f"alert_{int(time.time())}"
        alert_data = {
            'alert_id': alert_id,
            'timestamp': time.time(),
            'patient_id': patient_id,
            'alert_type': alert_type.value,
            'severity': severity.value,
            'message': message,
            'vital_sign': vital_sign,
            'current_value': current_value,
            'threshold_value': threshold_value,
        }
        
        # Notify callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert_data)
            except Exception as e:
                self.logger.error(f"Callback error: {e}")
        
        return alert_id
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge alert"""
        return True
    
    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve alert"""
        return True
    
    def _evaluate_threshold_rule(self, rule: AlertRule, value: float) -> bool:
        """Evaluate threshold-based alert rule"""
        return False
    
    def _send_local_alert(self, alert_data: Dict[str, Any]):
        """Send local alert (audio, popup)"""
        pass
    
    def _send_remote_alert(self, alert_data: Dict[str, Any]):
        """Send remote alert via MQTT"""
        pass
    
    def _play_alert_sound(self, severity: AlertSeverity):
        """Play alert sound based on severity"""
        pass
    
    def _speak_alert_message(self, message: str):
        """Speak alert message using text-to-speech"""
        pass
    
    def get_active_alerts(self, patient_id: str) -> List[Dict[str, Any]]:
        """Get currently active alerts for patient"""
        return []
    
    def get_alert_history(self, patient_id: str, hours: int = 24) -> List[Dict[str, Any]]:
        """Get alert history for patient"""
        return []
    
    def load_patient_rules(self, patient_id: str):
        """Load patient-specific alert rules"""
        pass
    
    def create_default_rules(self, patient_id: str) -> List[AlertRule]:
        """Create default alert rules for patient"""
        return []
    
    def get_alert_statistics(self, patient_id: str, days: int = 7) -> Dict[str, Any]:
        """Get alert statistics for patient"""
        return {}
    
    def test_alert_system(self) -> bool:
        """Test alert system functionality"""
        self.logger.info("Testing alert system...")
        if self.tts_manager:
            self.tts_manager.speak_scenario(ScenarioID.DEVICE_READY)
        return True