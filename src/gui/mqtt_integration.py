"""
MQTT Integration for GUI App
Helper functions để publish MQTT messages từ GUI measurements
"""

import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from src.communication.mqtt_payloads import (
    VitalsPayload,
    AlertPayload,
    DeviceStatusPayload
)


class GUIMQTTIntegration:
    """
    MQTT Integration Layer cho GUI App
    
    Xử lý việc publish vitals, alerts, status từ GUI measurements
    """
    
    def __init__(self, mqtt_client, device_id: str, patient_id: str, logger=None):
        """
        Initialize MQTT integration
        
        Args:
            mqtt_client: IoTHealthMQTTClient instance
            device_id: Device ID
            patient_id: Patient ID
            logger: Logger instance
        """
        self.mqtt_client = mqtt_client
        self.device_id = device_id
        self.patient_id = patient_id
        self.logger = logger or logging.getLogger(__name__)
        self.session_id = f"session_{int(time.time())}"
        self.measurement_sequence = 0
    
    def publish_vitals_from_measurement(
        self,
        measurement_data: Dict[str, Any],
        measurement_type: str
    ) -> bool:
        """
        Publish vitals từ measurement data
        
        Args:
            measurement_data: Data từ measurement screen
            measurement_type: 'heart_rate', 'temperature', 'blood_pressure'
        
        Returns:
            bool: True if published successfully
        """
        try:
            if not self.mqtt_client or not self.mqtt_client.is_connected:
                self.logger.debug("MQTT not connected, skipping vitals publish")
                return False
            
            self.measurement_sequence += 1
            
            # Convert measurement data to sensor_data format
            sensor_data = self._convert_measurement_to_sensor_data(
                measurement_data, 
                measurement_type
            )
            
            # Get device context
            device_context = self._get_device_context()
            
            # Create VitalsPayload
            vitals_payload = VitalsPayload.from_sensor_data(
                device_id=self.device_id,
                patient_id=self.patient_id,
                sensor_data=sensor_data,
                session_id=self.session_id,
                measurement_sequence=self.measurement_sequence,
                device_context=device_context
            )
            
            # Publish
            success = self.mqtt_client.publish_vitals(vitals_payload)
            
            if success:
                self.logger.info(f"📤 Published {measurement_type} vitals to MQTT")
            else:
                self.logger.warning(f"Failed to publish {measurement_type} vitals")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error publishing vitals: {e}", exc_info=True)
            return False
    
    def publish_alert_from_threshold_check(
        self,
        alert_type: str,
        severity: str,
        vital_sign: str,
        current_value: float,
        threshold_min: float,
        threshold_max: float,
        message: str = None
    ) -> bool:
        """
        Publish alert khi phát hiện vượt ngưỡng
        
        Args:
            alert_type: Type of alert (e.g., 'high_heart_rate')
            severity: 'info', 'warning', 'critical'
            vital_sign: 'heart_rate', 'spo2', 'temperature', 'blood_pressure'
            current_value: Current measurement value
            threshold_min: Minimum threshold
            threshold_max: Maximum threshold
            message: Custom alert message
        
        Returns:
            bool: True if published successfully
        """
        try:
            if not self.mqtt_client or not self.mqtt_client.is_connected:
                self.logger.debug("MQTT not connected, skipping alert publish")
                return False
            
            # Determine priority based on severity
            priority_map = {'info': 3, 'warning': 2, 'critical': 1}
            priority = priority_map.get(severity, 3)
            
            # Generate message if not provided
            if not message:
                if current_value < threshold_min:
                    message = f"{vital_sign} thấp: {current_value} (ngưỡng: {threshold_min}-{threshold_max})"
                elif current_value > threshold_max:
                    message = f"{vital_sign} cao: {current_value} (ngưỡng: {threshold_min}-{threshold_max})"
                else:
                    message = f"{vital_sign} bất thường: {current_value}"
            
            # Create AlertPayload
            alert_payload = AlertPayload(
                timestamp=time.time(),
                device_id=self.device_id,
                patient_id=self.patient_id,
                alert_type=alert_type,
                severity=severity,
                priority=priority,
                current_measurement={
                    vital_sign: current_value,
                    'timestamp': time.time()
                },
                thresholds={
                    'min': threshold_min,
                    'max': threshold_max,
                    'vital_sign': vital_sign
                },
                trend={
                    'direction': 'up' if current_value > threshold_max else 'down',
                    'rate': 0.0  # Could calculate from history
                },
                actions={
                    'notification_sent': True,
                    'tts_played': True
                },
                recommendations=[
                    f"Giám sát {vital_sign}",
                    "Liên hệ bác sĩ nếu triệu chứng tiếp diễn"
                ],
                metadata={
                    'source': 'gui_measurement',
                    'session_id': self.session_id
                }
            )
            
            # Publish
            success = self.mqtt_client.publish_alert(alert_payload)
            
            if success:
                self.logger.warning(f"🚨 Published alert: {alert_type} ({severity})")
            else:
                self.logger.warning(f"Failed to publish alert: {alert_type}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error publishing alert: {e}", exc_info=True)
            return False
    
    def publish_device_status(
        self,
        online: bool = True,
        sensors_status: Dict[str, str] = None,
        system_info: Dict[str, Any] = None
    ) -> bool:
        """
        Publish device status
        
        Args:
            online: Device online status
            sensors_status: Status of each sensor
            system_info: System information (uptime, memory, etc)
        
        Returns:
            bool: True if published successfully
        """
        try:
            if not self.mqtt_client:
                return False
            
            # Default sensors status
            if not sensors_status:
                sensors_status = {
                    'max30102': 'idle',
                    'mlx90614': 'idle',
                    'hx710b': 'idle'
                }
            
            # Default system info
            if not system_info:
                system_info = {
                    'uptime': 0,
                    'memory_usage': 50.0,
                    'cpu_usage': 30.0
                }
            
            # Create DeviceStatusPayload
            status_payload = DeviceStatusPayload(
                timestamp=time.time(),
                device_id=self.device_id,
                online=online,
                battery={
                    'level': 100,  # Could read from system
                    'charging': False
                },
                sensors=sensors_status,
                actuators={
                    'pump': 'idle',
                    'valve': 'closed'
                },
                system=system_info,
                network={
                    'wifi_signal': -50,  # Could read from system
                    'mqtt_connected': self.mqtt_client.is_connected if self.mqtt_client else False
                }
            )
            
            # Publish
            success = self.mqtt_client.publish_status(status_payload)
            
            if success:
                self.logger.debug(f"📊 Published device status (online={online})")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error publishing status: {e}", exc_info=True)
            return False
    
    def _convert_measurement_to_sensor_data(
        self,
        measurement_data: Dict[str, Any],
        measurement_type: str
    ) -> Dict[str, Any]:
        """
        Convert measurement data to sensor_data format for VitalsPayload
        
        Args:
            measurement_data: Raw measurement data from screen
            measurement_type: Type of measurement
        
        Returns:
            Dict in sensor_data format
        """
        sensor_data = {}
        
        if measurement_type == 'heart_rate':
            # Heart rate measurement
            if 'heart_rate' in measurement_data or 'hr' in measurement_data:
                sensor_data['heart_rate'] = measurement_data.get('heart_rate') or measurement_data.get('hr')
                sensor_data['heart_rate_metadata'] = {
                    'confidence': measurement_data.get('confidence', 0.9),
                    'ir_quality': measurement_data.get('signal_quality_index', 0.0),
                    'peak_count': measurement_data.get('peak_count', 0),
                    'sampling_rate': measurement_data.get('sampling_rate', 100.0),
                    'duration': measurement_data.get('measurement_duration', 0.0),
                    'cv': measurement_data.get('cv', 0.0)
                }
            
            # SpO2 measurement
            if 'spo2' in measurement_data:
                sensor_data['spo2'] = measurement_data['spo2']
                sensor_data['spo2_metadata'] = {
                    'confidence': measurement_data.get('spo2_confidence', 0.9),
                    'r_value': measurement_data.get('r_value', 0.0),
                    'ac_red': measurement_data.get('ac_red', 0),
                    'dc_red': measurement_data.get('dc_red', 0),
                    'ac_ir': measurement_data.get('ac_ir', 0),
                    'dc_ir': measurement_data.get('dc_ir', 0)
                }
        
        elif measurement_type == 'temperature':
            # Temperature measurement
            if 'temperature' in measurement_data or 'temp' in measurement_data:
                sensor_data['temperature'] = measurement_data.get('temperature') or measurement_data.get('temp')
                sensor_data['ambient_temperature'] = measurement_data.get('ambient_temperature', 25.0)
                sensor_data['temperature_metadata'] = {
                    'read_count': measurement_data.get('read_count', 1),
                    'std_dev': measurement_data.get('std_dev', 0.0)
                }
        
        elif measurement_type == 'blood_pressure':
            # Blood pressure measurement
            if 'systolic' in measurement_data or 'blood_pressure_systolic' in measurement_data:
                sensor_data['blood_pressure_systolic'] = (
                    measurement_data.get('systolic') or 
                    measurement_data.get('blood_pressure_systolic')
                )
                sensor_data['blood_pressure_diastolic'] = (
                    measurement_data.get('diastolic') or 
                    measurement_data.get('blood_pressure_diastolic')
                )
                sensor_data['blood_pressure_map'] = (
                    measurement_data.get('map') or 
                    measurement_data.get('map_bp')
                )
                sensor_data['bp_metadata'] = {
                    'valid': measurement_data.get('valid', True),
                    'quality': measurement_data.get('quality', 'good'),
                    'confidence': measurement_data.get('confidence', 0.85),
                    'pulse_pressure': measurement_data.get('pulse_pressure', 0),
                    'heart_rate': measurement_data.get('hr_from_bp', 0.0),
                    'max_pressure': measurement_data.get('max_pressure', 0),
                    'deflate_rate': measurement_data.get('deflate_rate', 0.0)
                }
        
        # Add total duration if available
        if 'measurement_elapsed' in measurement_data:
            sensor_data['total_duration'] = measurement_data['measurement_elapsed']
        
        # Add user triggered flag
        sensor_data['user_triggered'] = measurement_data.get('user_triggered', True)
        
        return sensor_data
    
    def _get_device_context(self) -> Dict[str, Any]:
        """
        Get current device context for vitals payload
        
        Returns:
            Dict with device context information
        """
        return {
            'gui_version': '2.0.0',
            'measurement_mode': 'manual',
            'screen_resolution': '480x320',
            'timestamp': time.time()
        }
