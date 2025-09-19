"""
Data Validators
Validation utilities cho health monitoring data
"""

from typing import Dict, Any, Optional, List, Union, Tuple
import re
from datetime import datetime, timedelta
import logging


class ValidationError(Exception):
    """Custom exception for validation errors"""
    pass


class DataValidator:
    """
    Data validator cho health monitoring system
    
    Attributes:
        config (Dict): Validation configuration
        logger (logging.Logger): Logger instance
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize data validator
        
        Args:
            config: Validation configuration
        """
        pass
    
    def validate_vital_signs(self, vital_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate vital signs data
        
        Args:
            vital_data: Vital signs data to validate
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        pass
    
    def validate_heart_rate(self, heart_rate: float) -> bool:
        """
        Validate heart rate value
        
        Args:
            heart_rate: Heart rate in BPM
            
        Returns:
            bool: True if valid
        """
        pass
    
    def validate_spo2(self, spo2: float) -> bool:
        """
        Validate SpO2 value
        
        Args:
            spo2: SpO2 percentage
            
        Returns:
            bool: True if valid
        """
        pass
    
    def validate_temperature(self, temperature: float, unit: str = "C") -> bool:
        """
        Validate temperature value
        
        Args:
            temperature: Temperature value
            unit: Temperature unit ("C" or "F")
            
        Returns:
            bool: True if valid
        """
        pass
    
    def validate_blood_pressure(self, systolic: float, diastolic: float) -> bool:
        """
        Validate blood pressure values
        
        Args:
            systolic: Systolic pressure
            diastolic: Diastolic pressure
            
        Returns:
            bool: True if valid
        """
        pass
    
    def validate_patient_id(self, patient_id: str) -> bool:
        """
        Validate patient ID format
        
        Args:
            patient_id: Patient identifier
            
        Returns:
            bool: True if valid
        """
        pass
    
    def validate_sensor_data(self, sensor_name: str, raw_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate raw sensor data
        
        Args:
            sensor_name: Name of sensor
            raw_data: Raw sensor data
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        pass
    
    def validate_timestamp(self, timestamp: Union[datetime, str, float]) -> bool:
        """
        Validate timestamp format and value
        
        Args:
            timestamp: Timestamp to validate
            
        Returns:
            bool: True if valid
        """
        pass
    
    def validate_data_quality_score(self, score: float) -> bool:
        """
        Validate data quality score
        
        Args:
            score: Quality score (0-1)
            
        Returns:
            bool: True if valid
        """
        pass
    
    def validate_alert_data(self, alert_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate alert data structure
        
        Args:
            alert_data: Alert data to validate
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        pass
    
    def validate_configuration(self, config_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate system configuration
        
        Args:
            config_data: Configuration data to validate
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        pass
    
    def _is_in_range(self, value: float, min_val: float, max_val: float) -> bool:
        """
        Check if value is within range
        
        Args:
            value: Value to check
            min_val: Minimum allowed value
            max_val: Maximum allowed value
            
        Returns:
            bool: True if in range
        """
        pass
    
    def _is_positive_number(self, value: Union[int, float]) -> bool:
        """
        Check if value is a positive number
        
        Args:
            value: Value to check
            
        Returns:
            bool: True if positive number
        """
        pass
    
    def _validate_string_format(self, value: str, pattern: str) -> bool:
        """
        Validate string against regex pattern
        
        Args:
            value: String to validate
            pattern: Regex pattern
            
        Returns:
            bool: True if matches pattern
        """
        pass
    
    def sanitize_input(self, input_data: Any) -> Any:
        """
        Sanitize input data for security
        
        Args:
            input_data: Data to sanitize
            
        Returns:
            Sanitized data
        """
        pass
    
    def validate_network_config(self, network_config: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate network configuration
        
        Args:
            network_config: Network configuration to validate
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        pass
    
    def validate_ip_address(self, ip_address: str) -> bool:
        """
        Validate IP address format
        
        Args:
            ip_address: IP address to validate
            
        Returns:
            bool: True if valid IP address
        """
        pass
    
    def validate_port_number(self, port: Union[int, str]) -> bool:
        """
        Validate port number
        
        Args:
            port: Port number to validate
            
        Returns:
            bool: True if valid port
        """
        pass
    
    def validate_email(self, email: str) -> bool:
        """
        Validate email address format
        
        Args:
            email: Email address to validate
            
        Returns:
            bool: True if valid email
        """
        pass
    
    def validate_phone_number(self, phone: str) -> bool:
        """
        Validate phone number format
        
        Args:
            phone: Phone number to validate
            
        Returns:
            bool: True if valid phone number
        """
        pass
    
    def validate_file_path(self, file_path: str, must_exist: bool = False) -> bool:
        """
        Validate file path
        
        Args:
            file_path: File path to validate
            must_exist: Whether file must exist
            
        Returns:
            bool: True if valid path
        """
        pass
    
    def validate_json_structure(self, json_data: Dict[str, Any], 
                               required_fields: List[str]) -> Tuple[bool, List[str]]:
        """
        Validate JSON structure has required fields
        
        Args:
            json_data: JSON data to validate
            required_fields: List of required field names
            
        Returns:
            Tuple of (is_valid, missing_fields)
        """
        pass
    
    def create_validation_report(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create comprehensive validation report
        
        Args:
            data: Data to validate
            
        Returns:
            Validation report dictionary
        """
        pass