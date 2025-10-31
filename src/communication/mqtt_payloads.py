"""
MQTT Payload Templates
Định nghĩa cấu trúc payload chuẩn cho MQTT messages
"""

from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import time


# ==================== VITALS PAYLOADS ====================

@dataclass
class HRMetrics:
    """Heart Rate raw metrics từ MAX30102"""
    ir_quality: float
    peak_count: int
    sampling_rate: float
    measurement_duration: float
    cv_coefficient: float
    

@dataclass
class SpO2Metrics:
    """SpO2 raw metrics từ MAX30102"""
    r_value: float
    ac_red: int
    dc_red: int
    ac_ir: int
    dc_ir: int


@dataclass
class TemperatureMetrics:
    """Temperature raw metrics từ MLX90614"""
    read_count: int
    std_deviation: float


@dataclass
class BPRawMetrics:
    """Blood Pressure raw metrics từ HX710B"""
    pulse_pressure: int
    heart_rate_bp: float
    max_pressure_reached: int
    deflate_rate_actual: float
    oscillation_amplitude: float
    envelope_quality: float
    
    # HX710B specific
    max_counts: int
    map_counts: int
    samples_collected: int
    sampling_rate: float
    offset_counts: int
    slope_mmhg_per_count: float
    
    # AAMI validation
    aami_validation: Dict[str, bool] = field(default_factory=dict)


@dataclass
class VitalsPayload:
    """
    Complete vitals message với tất cả sensor data
    
    Topic: iot_health/device/{device_id}/vitals
    QoS: 1
    """
    timestamp: float
    device_id: str
    patient_id: str
    
    # Measurements
    measurements: Dict[str, Any] = field(default_factory=dict)
    
    # Session metadata
    session: Dict[str, Any] = field(default_factory=dict)
    
    # Device context
    device_context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)
    
    @classmethod
    def from_sensor_data(
        cls,
        device_id: str,
        patient_id: str,
        sensor_data: Dict[str, Any],
        session_id: str,
        measurement_sequence: int,
        device_context: Dict[str, Any]
    ) -> 'VitalsPayload':
        """
        Tạo payload từ sensor data
        
        Args:
            device_id: Device ID
            patient_id: Patient ID
            sensor_data: Raw sensor data dict
            session_id: Session ID
            measurement_sequence: Measurement number
            device_context: Device status context
        """
        measurements = {}
        
        # Heart Rate
        if 'heart_rate' in sensor_data and sensor_data['heart_rate'] is not None:
            hr_data = sensor_data.get('heart_rate_metadata', {})
            measurements['heart_rate'] = {
                'value': sensor_data['heart_rate'],
                'unit': 'bpm',
                'valid': True,
                'confidence': hr_data.get('confidence', 0.0),
                'source': 'MAX30102',
                'raw_metrics': {
                    'ir_quality': hr_data.get('ir_quality', 0.0),
                    'peak_count': hr_data.get('peak_count', 0),
                    'sampling_rate': hr_data.get('sampling_rate', 0.0),
                    'measurement_duration': hr_data.get('duration', 0.0),
                    'cv_coefficient': hr_data.get('cv', 0.0)
                }
            }
        
        # SpO2
        if 'spo2' in sensor_data and sensor_data['spo2'] is not None:
            spo2_data = sensor_data.get('spo2_metadata', {})
            measurements['spo2'] = {
                'value': sensor_data['spo2'],
                'unit': '%',
                'valid': True,
                'confidence': spo2_data.get('confidence', 0.0),
                'source': 'MAX30102',
                'raw_metrics': {
                    'r_value': spo2_data.get('r_value', 0.0),
                    'ac_red': spo2_data.get('ac_red', 0),
                    'dc_red': spo2_data.get('dc_red', 0),
                    'ac_ir': spo2_data.get('ac_ir', 0),
                    'dc_ir': spo2_data.get('dc_ir', 0)
                }
            }
        
        # Temperature
        if 'temperature' in sensor_data and sensor_data['temperature'] is not None:
            temp_data = sensor_data.get('temperature_metadata', {})
            measurements['temperature'] = {
                'object_temp': sensor_data['temperature'],
                'ambient_temp': sensor_data.get('ambient_temperature', 0.0),
                'unit': 'celsius',
                'valid': True,
                'source': 'MLX90614',
                'raw_metrics': {
                    'read_count': temp_data.get('read_count', 0),
                    'std_deviation': temp_data.get('std_dev', 0.0)
                }
            }
        
        # Blood Pressure
        if 'blood_pressure_systolic' in sensor_data:
            bp_data = sensor_data.get('bp_metadata', {})
            measurements['blood_pressure'] = {
                'systolic': sensor_data.get('blood_pressure_systolic', 0),
                'diastolic': sensor_data.get('blood_pressure_diastolic', 0),
                'map': sensor_data.get('blood_pressure_map', 0),
                'unit': 'mmHg',
                'valid': bp_data.get('valid', False),
                'quality': bp_data.get('quality', 'unknown'),
                'confidence': bp_data.get('confidence', 0.0),
                'source': 'HX710B',
                'raw_metrics': {
                    'pulse_pressure': bp_data.get('pulse_pressure', 0),
                    'heart_rate_bp': bp_data.get('heart_rate', 0.0),
                    'max_pressure_reached': bp_data.get('max_pressure', 0),
                    'deflate_rate_actual': bp_data.get('deflate_rate', 0.0),
                    'oscillation_amplitude': bp_data.get('oscillation_amp', 0.0),
                    'envelope_quality': bp_data.get('envelope_quality', 0.0),
                    'hx710b': {
                        'max_counts': bp_data.get('max_counts', 0),
                        'map_counts': bp_data.get('map_counts', 0),
                        'samples_collected': bp_data.get('samples', 0),
                        'sampling_rate': bp_data.get('sampling_rate', 0.0),
                        'offset_counts': bp_data.get('offset_counts', 0),
                        'slope_mmhg_per_count': bp_data.get('slope', 0.0)
                    },
                    'aami_validation': bp_data.get('aami_validation', {})
                }
            }
        
        return cls(
            timestamp=time.time(),
            device_id=device_id,
            patient_id=patient_id,
            measurements=measurements,
            session={
                'session_id': session_id,
                'measurement_sequence': measurement_sequence,
                'total_duration': sensor_data.get('total_duration', 0.0),
                'user_triggered': sensor_data.get('user_triggered', True)
            },
            device_context=device_context
        )


# ==================== ALERT PAYLOADS ====================

@dataclass
class AlertPayload:
    """
    Health alert message
    
    Topic: iot_health/device/{device_id}/alerts
    QoS: 2 (exactly once)
    """
    timestamp: float
    device_id: str
    patient_id: str
    alert_type: str
    severity: str  # "info" | "warning" | "critical"
    priority: int  # 1=highest, 5=lowest
    
    current_measurement: Dict[str, Any]
    thresholds: Dict[str, Any]
    trend: Dict[str, Any] = field(default_factory=dict)
    actions: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ==================== STATUS PAYLOADS ====================

@dataclass
class DeviceStatusPayload:
    """
    Device status message
    
    Topic: iot_health/device/{device_id}/status
    QoS: 0 (at most once)
    Retain: True
    """
    timestamp: float
    device_id: str
    online: bool
    
    battery: Dict[str, Any] = field(default_factory=dict)
    sensors: Dict[str, Any] = field(default_factory=dict)
    actuators: Dict[str, Any] = field(default_factory=dict)
    system: Dict[str, Any] = field(default_factory=dict)
    network: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ==================== COMMAND PAYLOADS ====================

@dataclass
class CommandPayload:
    """
    Remote command message
    
    Topic: iot_health/patient/{patient_id}/commands
    QoS: 2 (exactly once)
    """
    command_id: str
    timestamp: float
    issuer: str
    command: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    expires_at: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CommandPayload':
        """Parse command from MQTT message"""
        return cls(**data)
