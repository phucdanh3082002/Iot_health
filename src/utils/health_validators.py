"""
Health Data Validators
Validate measurement data before saving to database
"""

from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime
import time
import logging


logger = logging.getLogger(__name__)


class HealthDataValidator:
    """
    Validate health measurement data against acceptable ranges
    
    Prevents invalid/garbage data from being persisted to database
    and synced to cloud.
    """
    
    # Acceptable ranges for vital signs (based on medical standards)
    VALID_RANGES = {
        'heart_rate': {
            'min': 30,      # BPM - below this is bradycardia or sensor error
            'max': 250,     # BPM - above this is tachycardia or sensor error
            'name': 'Nhịp tim'
        },
        'spo2': {
            'min': 50,      # % - below 50% is likely sensor error
            'max': 100,     # % - cannot exceed 100%
            'name': 'SpO2'
        },
        'temperature': {
            'min': 30.0,    # °C - below this is hypothermia or sensor error
            'max': 45.0,    # °C - above this is hyperthermia or sensor error
            'name': 'Nhiệt độ'
        },
        'systolic_bp': {
            'min': 50,      # mmHg - severe hypotension or sensor error
            'max': 250,     # mmHg - hypertensive crisis or sensor error
            'name': 'Huyết áp tâm thu'
        },
        'diastolic_bp': {
            'min': 30,      # mmHg - severe hypotension or sensor error
            'max': 150,     # mmHg - hypertensive crisis or sensor error
            'name': 'Huyết áp tâm trương'
        },
        'mean_arterial_pressure': {
            'min': 40,      # mmHg - critical low MAP
            'max': 180,     # mmHg - critical high MAP
            'name': 'Huyết áp trung bình (MAP)'
        }
    }
    
    # Acceptable ranges for metadata/quality metrics
    METADATA_RANGES = {
        'signal_quality_index': {
            'min': 0,       # 0-100 scale
            'max': 100,
            'name': 'Chỉ số chất lượng tín hiệu'
        },
        'spo2_cv': {
            'min': 0,       # Coefficient of variation (0-100%)
            'max': 100,
            'name': 'Hệ số biến thiên SpO2'
        },
        'peak_count': {
            'min': 0,       # Number of peaks detected
            'max': 500,     # Upper limit for sanity check
            'name': 'Số lượng đỉnh'
        },
        'measurement_duration': {
            'min': 0,       # Seconds
            'max': 600,     # 10 minutes max
            'name': 'Thời gian đo'
        },
        'data_quality': {
            'min': 0.0,     # Quality score 0-1
            'max': 1.0,
            'name': 'Chất lượng dữ liệu'
        }
    }
    
    @classmethod
    def validate(cls, measurement_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate measurement data against acceptable ranges
        
        Args:
            measurement_data: Dictionary containing measurement values
        
        Returns:
            Tuple of (is_valid, list_of_error_messages)
            
        Example:
            >>> is_valid, errors = HealthDataValidator.validate({
            ...     'heart_rate': 75,
            ...     'spo2': 98,
            ...     'temperature': 37.2
            ... })
            >>> print(is_valid)  # True
            >>> print(errors)    # []
        """
        errors = []
        
        # Validate vital signs
        for field, limits in cls.VALID_RANGES.items():
            value = measurement_data.get(field)
            
            # Skip if not present or None (optional fields)
            if value is None:
                continue
            
            # Check if numeric
            if not isinstance(value, (int, float)):
                errors.append(f"{limits['name']}: giá trị không hợp lệ (phải là số)")
                continue
            
            # Skip zero/negative values (indicates no measurement)
            if value <= 0:
                continue
            
            # Check range
            if value < limits['min'] or value > limits['max']:
                errors.append(
                    f"{limits['name']}: {value} ngoài phạm vi hợp lệ "
                    f"({limits['min']}-{limits['max']})"
                )
        
        # Special validation: BP consistency check
        systolic = measurement_data.get('systolic_bp') or measurement_data.get('systolic')
        diastolic = measurement_data.get('diastolic_bp') or measurement_data.get('diastolic')
        
        if systolic and diastolic and systolic > 0 and diastolic > 0:
            if systolic <= diastolic:
                errors.append(
                    f"Huyết áp không hợp lệ: Tâm thu ({systolic}) phải lớn hơn "
                    f"tâm trương ({diastolic})"
                )
            
            # Pulse pressure check (normal range: 30-50 mmHg)
            pulse_pressure = systolic - diastolic
            if pulse_pressure < 20:
                errors.append(
                    f"Chênh lệch huyết áp quá thấp: {pulse_pressure} mmHg "
                    f"(tâm thu - tâm trương < 20)"
                )
            elif pulse_pressure > 100:
                errors.append(
                    f"Chênh lệch huyết áp quá cao: {pulse_pressure} mmHg "
                    f"(tâm thu - tâm trương > 100)"
                )
        
        # Validate metadata (if present)
        for field, limits in cls.METADATA_RANGES.items():
            value = measurement_data.get(field)
            
            if value is None:
                continue
            
            if not isinstance(value, (int, float)):
                errors.append(f"{limits['name']}: giá trị không hợp lệ (phải là số)")
                continue
            
            if value < limits['min'] or value > limits['max']:
                errors.append(
                    f"{limits['name']}: {value} ngoài phạm vi hợp lệ "
                    f"({limits['min']}-{limits['max']})"
                )
        
        # Validate timestamp
        timestamp = measurement_data.get('timestamp')
        if timestamp:
            timestamp_error = cls._validate_timestamp(timestamp)
            if timestamp_error:
                errors.append(timestamp_error)
        
        # Validate measurement_type (if present)
        measurement_type = measurement_data.get('measurement_type')
        if measurement_type:
            valid_types = [
                'heart_rate', 'heart_rate_spo2', 'temperature', 
                'blood_pressure', 'spo2', 'continuous'
            ]
            if measurement_type not in valid_types:
                errors.append(
                    f"Loại đo không hợp lệ: {measurement_type} "
                    f"(phải là một trong: {', '.join(valid_types)})"
                )
        
        is_valid = len(errors) == 0
        
        if not is_valid:
            logger.warning(f"Validation failed: {errors}")
        
        return (is_valid, errors)
    
    @classmethod
    def _validate_timestamp(cls, timestamp: Any) -> Optional[str]:
        """
        Validate timestamp is within acceptable range
        
        Args:
            timestamp: Unix timestamp (int/float) or datetime object or ISO string
        
        Returns:
            Error message if invalid, None if valid
        """
        try:
            # Convert to unix timestamp for comparison
            if isinstance(timestamp, datetime):
                ts_unix = timestamp.timestamp()
            elif isinstance(timestamp, str):
                ts_unix = datetime.fromisoformat(timestamp).timestamp()
            elif isinstance(timestamp, (int, float)):
                ts_unix = float(timestamp)
            else:
                return f"Timestamp không hợp lệ: kiểu dữ liệu {type(timestamp)}"
            
            # Check not too far in future (allow ±1 minute for clock skew)
            now = time.time()
            if ts_unix > now + 60:
                return f"Timestamp trong tương lai: {datetime.fromtimestamp(ts_unix).isoformat()}"
            
            # Check not too far in past (allow up to 7 days old measurements)
            week_ago = now - (86400 * 7)
            if ts_unix < week_ago:
                return f"Timestamp quá cũ: {datetime.fromtimestamp(ts_unix).isoformat()} (hơn 7 ngày)"
            
            return None
            
        except Exception as e:
            return f"Timestamp không hợp lệ: {e}"
    
    @classmethod
    def validate_strict(cls, measurement_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Strict validation requiring at least one vital sign measurement
        
        Args:
            measurement_data: Dictionary containing measurement values
        
        Returns:
            Tuple of (is_valid, list_of_error_messages)
        """
        # First run normal validation
        is_valid, errors = cls.validate(measurement_data)
        
        # Check if at least one vital sign is present
        vital_signs = ['heart_rate', 'spo2', 'temperature', 'systolic_bp', 'diastolic_bp']
        has_vital_sign = False
        
        for vs in vital_signs:
            value = measurement_data.get(vs)
            if value is not None and value > 0:
                has_vital_sign = True
                break
        
        if not has_vital_sign:
            errors.append(
                "Không có dữ liệu đo: cần ít nhất một chỉ số sinh tồn "
                "(nhịp tim, SpO2, nhiệt độ, hoặc huyết áp)"
            )
            is_valid = False
        
        return (is_valid, errors)
    
    @classmethod
    def sanitize(cls, measurement_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize measurement data by removing invalid values
        
        This is a lenient version that removes invalid fields instead of rejecting the entire record.
        Use when you want to save partial data even if some fields are invalid.
        
        Args:
            measurement_data: Dictionary containing measurement values
        
        Returns:
            Sanitized dictionary with only valid fields
        """
        sanitized = {}
        
        # Copy timestamp (validated separately)
        if 'timestamp' in measurement_data:
            sanitized['timestamp'] = measurement_data['timestamp']
        
        # Copy patient_id (not validated)
        if 'patient_id' in measurement_data:
            sanitized['patient_id'] = measurement_data['patient_id']
        
        # Copy measurement_type (validated separately)
        if 'measurement_type' in measurement_data:
            sanitized['measurement_type'] = measurement_data['measurement_type']
        
        # Sanitize vital signs
        for field, limits in cls.VALID_RANGES.items():
            value = measurement_data.get(field)
            
            # Skip if not present, None, or zero
            if value is None or value <= 0:
                continue
            
            # Skip if not numeric
            if not isinstance(value, (int, float)):
                logger.warning(f"Skipping non-numeric field: {field}={value}")
                continue
            
            # Only copy if within valid range
            if limits['min'] <= value <= limits['max']:
                sanitized[field] = value
            else:
                logger.warning(
                    f"Skipping out-of-range field: {field}={value} "
                    f"(valid: {limits['min']}-{limits['max']})"
                )
        
        # Sanitize metadata
        for field, limits in cls.METADATA_RANGES.items():
            value = measurement_data.get(field)
            
            if value is None:
                continue
            
            if not isinstance(value, (int, float)):
                logger.warning(f"Skipping non-numeric metadata: {field}={value}")
                continue
            
            if limits['min'] <= value <= limits['max']:
                sanitized[field] = value
            else:
                logger.warning(
                    f"Skipping out-of-range metadata: {field}={value} "
                    f"(valid: {limits['min']}-{limits['max']})"
                )
        
        # Copy sensor_data JSON (already validated by caller)
        if 'sensor_data' in measurement_data:
            sanitized['sensor_data'] = measurement_data['sensor_data']
        
        return sanitized


# Convenience functions for backward compatibility
def validate_measurement(measurement_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Shortcut for HealthDataValidator.validate()"""
    return HealthDataValidator.validate(measurement_data)


def validate_measurement_strict(measurement_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Shortcut for HealthDataValidator.validate_strict()"""
    return HealthDataValidator.validate_strict(measurement_data)


def sanitize_measurement(measurement_data: Dict[str, Any]) -> Dict[str, Any]:
    """Shortcut for HealthDataValidator.sanitize()"""
    return HealthDataValidator.sanitize(measurement_data)
