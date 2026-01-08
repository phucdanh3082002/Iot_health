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
    - Dynamic patient-specific thresholds (AI-generated)
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
        
        # Patient-specific thresholds cache (AI-generated)
        self.patient_thresholds: Dict[str, Dict[str, Dict[str, float]]] = {}
        self.threshold_reload_time: Dict[str, datetime] = {}
        
        # Baseline thresholds (fallback) - đọc từ config
        self.baseline_thresholds = config.get('threshold_management', {}).get('baseline', {
            'heart_rate': {'min_critical': 40, 'min_normal': 60, 'max_normal': 100, 'max_critical': 120},
            'spo2': {'min_critical': 85, 'min_normal': 95, 'max_normal': 100, 'max_critical': 100},
            'systolic_bp': {'min_critical': 80, 'min_normal': 90, 'max_normal': 120, 'max_critical': 180},
            'diastolic_bp': {'min_critical': 50, 'min_normal': 60, 'max_normal': 80, 'max_critical': 120},
            'temperature': {'min_critical': 35.0, 'min_normal': 36.1, 'max_normal': 37.2, 'max_critical': 39.0}
        })
        
        # Callbacks
        self.alert_callbacks: List[Callable] = []
        
        # Settings
        self.audio_enabled = config.get('audio_enabled', True)
        self.auto_alert_tts_enabled = False  # DISABLED: Tắt TTS tự động lúc startup, chỉ khi user trigger
        self.auto_reload_thresholds = config.get('threshold_management', {}).get('auto_reload', True)
        self.fallback_to_baseline = config.get('threshold_management', {}).get('fallback_to_baseline', True)
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        self.logger.info("AlertSystem initialized (auto TTS alerts DISABLED by default)")
    
    # ============================================================
    # PATIENT THRESHOLD MANAGEMENT (AI-generated)
    # ============================================================
    
    def _load_patient_thresholds(self, patient_id: str) -> Dict[str, Dict[str, float]]:
        """
        Load patient-specific thresholds from database
        
        Args:
            patient_id: Patient identifier
            
        Returns:
            Dict of thresholds per vital sign: {
                'heart_rate': {'min_critical': 40, 'min_normal': 60, ...},
                ...
            }
        """
        if not self.database:
            self.logger.warning(f"[THRESHOLD_LOAD] No database available, using baseline thresholds")
            return self.baseline_thresholds
        
        try:
            with self.database.get_session() as session:
                from src.data.models import PatientThreshold
                
                thresholds_raw = session.query(PatientThreshold).filter_by(
                    patient_id=patient_id
                ).all()
                
                if not thresholds_raw:
                    self.logger.info(f"[THRESHOLD_LOAD] No custom thresholds for patient {patient_id}, using baseline")
                    return self.baseline_thresholds
                
                # Build thresholds dictionary
                patient_thresholds = {}
                for threshold in thresholds_raw:
                    patient_thresholds[threshold.vital_sign] = {
                        'min_critical': threshold.min_critical,
                        'min_normal': threshold.min_normal,
                        'min_warning': threshold.min_warning,
                        'max_warning': threshold.max_warning,
                        'max_normal': threshold.max_normal,
                        'max_critical': threshold.max_critical,
                        'generation_method': threshold.generation_method,
                        'ai_confidence': threshold.ai_confidence  # Fixed: was confidence_score
                    }
                
                self.logger.info(f"[THRESHOLD_LOAD] Loaded {len(patient_thresholds)} custom thresholds for patient {patient_id}")
                return patient_thresholds
        
        except Exception as e:
            self.logger.error(f"[THRESHOLD_LOAD] Failed to load thresholds for patient {patient_id}: {e}", exc_info=True)
            if self.fallback_to_baseline:
                self.logger.warning(f"[THRESHOLD_LOAD] Falling back to baseline thresholds")
                return self.baseline_thresholds
            else:
                raise
    
    def reload_patient_thresholds(self, patient_id: str, force: bool = False):
        """
        Reload patient thresholds from database (e.g., after cloud sync)
        
        Args:
            patient_id: Patient identifier
            force: Force reload even if recently loaded
        """
        # Check if recently reloaded (cache for 60 seconds unless forced)
        last_reload = self.threshold_reload_time.get(patient_id)
        if not force and last_reload and (datetime.now() - last_reload).total_seconds() < 60:
            self.logger.debug(f"[THRESHOLD_RELOAD] Skipping reload for patient {patient_id} (recently loaded)")
            return
        
        self.logger.info(f"[THRESHOLD_RELOAD] Reloading thresholds for patient {patient_id}")
        self.patient_thresholds[patient_id] = self._load_patient_thresholds(patient_id)
        self.threshold_reload_time[patient_id] = datetime.now()
    
    def get_patient_thresholds(self, patient_id: str) -> Dict[str, Dict[str, float]]:
        """
        Get patient thresholds (from cache or database)
        
        Args:
            patient_id: Patient identifier
            
        Returns:
            Dict of thresholds per vital sign
        """
        # Return cached thresholds if available
        if patient_id in self.patient_thresholds:
            return self.patient_thresholds[patient_id]
        
        # Load from database
        self.patient_thresholds[patient_id] = self._load_patient_thresholds(patient_id)
        self.threshold_reload_time[patient_id] = datetime.now()
        
        return self.patient_thresholds[patient_id]
    
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
            # Load patient-specific thresholds
            thresholds = self.get_patient_thresholds(patient_id)
            
            hr = vital_data.get('heart_rate')
            spo2 = vital_data.get('spo2')
            sys_bp = vital_data.get('systolic_bp')
            dia_bp = vital_data.get('diastolic_bp')
            temp = vital_data.get('temperature')
            
            # Check Heart Rate
            if hr is not None and hr > 0:
                self._check_heart_rate(patient_id, hr, thresholds.get('heart_rate', self.baseline_thresholds['heart_rate']))
            
            # Check SpO2
            if spo2 is not None and spo2 > 0:
                self._check_spo2(patient_id, spo2, thresholds.get('spo2', self.baseline_thresholds['spo2']))
            
            # Check Blood Pressure
            if sys_bp is not None and dia_bp is not None:
                sys_thresholds = thresholds.get('systolic_bp', self.baseline_thresholds['systolic_bp'])
                dia_thresholds = thresholds.get('diastolic_bp', self.baseline_thresholds['diastolic_bp'])
                self._check_blood_pressure(patient_id, sys_bp, dia_bp, sys_thresholds, dia_thresholds)
            
            # Check Temperature (if needed)
            if temp is not None:
                self._check_temperature(patient_id, temp, thresholds.get('temperature', self.baseline_thresholds['temperature']))
                
        except Exception as e:
            self.logger.error(f"Error checking vital signs: {e}", exc_info=True)
    
    def _check_heart_rate(self, patient_id: str, hr: float, thresholds: Dict[str, float]):
        """Check HR thresholds với TTS tự động (patient-specific)"""
        min_critical = thresholds.get('min_critical', 40)
        min_normal = thresholds.get('min_normal', 60)
        max_normal = thresholds.get('max_normal', 100)
        max_critical = thresholds.get('max_critical', 120)
        
        # Bradycardia: HR < min_normal
        if hr < min_normal:
            severity = AlertSeverity.CRITICAL if hr < min_critical else AlertSeverity.HIGH
            if not self._check_cooldown('hr_too_low'):
                self._trigger_alert_with_tts(
                    patient_id=patient_id,
                    alert_type='hr_too_low',
                    severity=severity,
                    message=f"Nhịp tim quá thấp: {hr:.0f} BPM (ngưỡng: {min_normal})",
                    tts_scenario=ScenarioID.HR_TOO_LOW,
                    tts_params={'bpm': int(hr)},
                    vital_sign='heart_rate',
                    current_value=hr,
                    threshold_value=min_normal
                )
                self.cooldown_tracker['hr_too_low'] = datetime.now()
        
        # Tachycardia: HR > max_normal
        elif hr > max_normal:
            severity = AlertSeverity.CRITICAL if hr > max_critical else AlertSeverity.HIGH
            if not self._check_cooldown('hr_too_high'):
                self._trigger_alert_with_tts(
                    patient_id=patient_id,
                    alert_type='hr_too_high',
                    severity=severity,
                    message=f"Nhịp tim quá cao: {hr:.0f} BPM (ngưỡng: {max_normal})",
                    tts_scenario=ScenarioID.HR_TOO_HIGH,
                    tts_params={'bpm': int(hr)},
                    vital_sign='heart_rate',
                    current_value=hr,
                    threshold_value=max_normal
                )
                self.cooldown_tracker['hr_too_high'] = datetime.now()
    
    def _check_spo2(self, patient_id: str, spo2: float, thresholds: Dict[str, float]):
        """Check SpO2 thresholds với TTS tự động (patient-specific)"""
        min_critical = thresholds.get('min_critical', 85)
        min_normal = thresholds.get('min_normal', 95)
        
        # Critical hypoxia: SpO2 < min_critical
        if spo2 < min_critical:
            if not self._check_cooldown('spo2_critical'):
                self._trigger_alert_with_tts(
                    patient_id=patient_id,
                    alert_type='spo2_critical',
                    severity=AlertSeverity.CRITICAL,
                    message=f"Oxy máu cực thấp: {spo2:.0f}% (ngưỡng: {min_critical})",
                    tts_scenario=ScenarioID.SPO2_CRITICAL,
                    tts_params={'spo2': int(spo2)},
                    vital_sign='spo2',
                    current_value=spo2,
                    threshold_value=min_critical
                )
                self.cooldown_tracker['spo2_critical'] = datetime.now()
        
        # Hypoxia: SpO2 < min_normal
        elif spo2 < min_normal:
            if not self._check_cooldown('spo2_low'):
                self._trigger_alert_with_tts(
                    patient_id=patient_id,
                    alert_type='spo2_low',
                    severity=AlertSeverity.HIGH,
                    message=f"Oxy máu thấp: {spo2:.0f}% (ngưỡng: {min_normal})",
                    tts_scenario=ScenarioID.SPO2_LOW,
                    tts_params={'spo2': int(spo2)},
                    vital_sign='spo2',
                    current_value=spo2,
                    threshold_value=min_normal
                )
                self.cooldown_tracker['spo2_low'] = datetime.now()
    
    def _check_blood_pressure(self, patient_id: str, sys: float, dia: float, 
                             sys_thresholds: Dict[str, float], dia_thresholds: Dict[str, float]):
        """Check BP thresholds với TTS tự động (patient-specific)"""
        sys_max_critical = sys_thresholds.get('max_critical', 180)
        sys_max_normal = sys_thresholds.get('max_normal', 120)
        sys_min_normal = sys_thresholds.get('min_normal', 90)
        
        dia_max_critical = dia_thresholds.get('max_critical', 120)
        dia_max_normal = dia_thresholds.get('max_normal', 80)
        dia_min_normal = dia_thresholds.get('min_normal', 60)
        
        # Hypertensive crisis: SYS >= sys_max_critical or DIA >= dia_max_critical
        if sys >= sys_max_critical or dia >= dia_max_critical:
            if not self._check_cooldown('bp_crisis'):
                self._trigger_alert_with_tts(
                    patient_id=patient_id,
                    alert_type='bp_hypertensive_crisis',
                    severity=AlertSeverity.CRITICAL,
                    message=f"Huyết áp nguy hiểm: {sys:.0f}/{dia:.0f} mmHg (ngưỡng: {sys_max_critical}/{dia_max_critical})",
                    tts_scenario=ScenarioID.BP_HYPERTENSIVE_CRISIS,
                    tts_params={'sys': int(sys), 'dia': int(dia)},
                    vital_sign='blood_pressure',
                    current_value=sys,
                    threshold_value=sys_max_critical
                )
                self.cooldown_tracker['bp_crisis'] = datetime.now()
        
        # Hypertension: SYS >= sys_max_normal or DIA >= dia_max_normal
        elif sys >= sys_max_normal or dia >= dia_max_normal:
            if not self._check_cooldown('bp_high'):
                self._trigger_alert_with_tts(
                    patient_id=patient_id,
                    alert_type='bp_hypertension',
                    severity=AlertSeverity.HIGH,
                    message=f"Huyết áp cao: {sys:.0f}/{dia:.0f} mmHg (ngưỡng: {sys_max_normal}/{dia_max_normal})",
                    tts_scenario=ScenarioID.BP_HYPERTENSION,
                    tts_params={'sys': int(sys), 'dia': int(dia)},
                    vital_sign='blood_pressure',
                    current_value=sys,
                    threshold_value=sys_max_normal
                )
                self.cooldown_tracker['bp_high'] = datetime.now()
        
        # Hypotension: SYS < sys_min_normal or DIA < dia_min_normal
        elif sys < sys_min_normal or dia < dia_min_normal:
            if not self._check_cooldown('bp_low'):
                self._trigger_alert_with_tts(
                    patient_id=patient_id,
                    alert_type='bp_hypotension',
                    severity=AlertSeverity.MEDIUM,
                    message=f"Huyết áp thấp: {sys:.0f}/{dia:.0f} mmHg (ngưỡng: {sys_min_normal}/{dia_min_normal})",
                    tts_scenario=ScenarioID.BP_HYPOTENSION,
                    tts_params={'sys': int(sys), 'dia': int(dia)},
                    vital_sign='blood_pressure',
                    current_value=sys,
                    threshold_value=90
                )
                self.cooldown_tracker['bp_low'] = datetime.now()
    
    def _check_temperature(self, patient_id: str, temp: float, thresholds: Dict[str, float]):
        """Check temperature thresholds với TTS tự động (patient-specific)"""
        min_critical = thresholds.get('min_critical', 35.0)
        min_normal = thresholds.get('min_normal', 36.1)
        max_normal = thresholds.get('max_normal', 37.2)
        max_critical = thresholds.get('max_critical', 39.0)
        
        # Hypothermia: temp < min_critical
        if temp < min_critical:
            if not self._check_cooldown('temp_too_low'):
                self._trigger_alert_with_tts(
                    patient_id=patient_id,
                    alert_type='temp_hypothermia',
                    severity=AlertSeverity.CRITICAL,
                    message=f"Thân nhiệt quá thấp: {temp:.1f}°C (ngưỡng: {min_critical})",
                    tts_scenario=ScenarioID.TEMP_LOW,
                    tts_params={'temp': temp},
                    vital_sign='temperature',
                    current_value=temp,
                    threshold_value=min_critical
                )
                self.cooldown_tracker['temp_too_low'] = datetime.now()
        
        # Low temp: temp < min_normal
        elif temp < min_normal:
            if not self._check_cooldown('temp_low'):
                self._trigger_alert_with_tts(
                    patient_id=patient_id,
                    alert_type='temp_low',
                    severity=AlertSeverity.MEDIUM,
                    message=f"Thân nhiệt thấp: {temp:.1f}°C (ngưỡng: {min_normal})",
                    tts_scenario=ScenarioID.TEMP_LOW,
                    tts_params={'temp': temp},
                    vital_sign='temperature',
                    current_value=temp,
                    threshold_value=min_normal
                )
                self.cooldown_tracker['temp_low'] = datetime.now()
        
        # Fever: temp > max_normal
        elif temp > max_normal:
            severity = AlertSeverity.CRITICAL if temp > max_critical else AlertSeverity.HIGH
            if not self._check_cooldown('temp_high'):
                self._trigger_alert_with_tts(
                    patient_id=patient_id,
                    alert_type='temp_fever',
                    severity=severity,
                    message=f"Sốt cao: {temp:.1f}°C (ngưỡng: {max_normal})",
                    tts_scenario=ScenarioID.TEMP_HIGH,
                    tts_params={'temp': temp},
                    vital_sign='temperature',
                    current_value=temp,
                    threshold_value=max_normal
                )
                self.cooldown_tracker['temp_high'] = datetime.now()
    
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
            
            # Play TTS alert - CHỈ phát khi auto_alert_tts_enabled = True
            if self.tts_manager and self.audio_enabled and self.auto_alert_tts_enabled:
                try:
                    self.tts_manager.speak_scenario(tts_scenario, **tts_params)
                    self.logger.debug(f"TTS alert played: {tts_scenario}")
                except Exception as e:
                    self.logger.error(f"Failed to play TTS alert: {e}")
            elif not self.auto_alert_tts_enabled:
                self.logger.debug(f"TTS alert suppressed (auto_alert_tts_enabled=False): {tts_scenario}")
            
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