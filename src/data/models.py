"""
Database Models
SQLAlchemy models cho IoT Health Monitoring System database
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.sqlite import JSON
import json


Base = declarative_base()


class Patient(Base):
    """
    Patient model for storing patient information
    
    Attributes:
        id: Primary key
        patient_id: Unique patient identifier
        name: Patient name
        age: Patient age
        gender: Patient gender
        medical_conditions: JSON field for medical conditions
        emergency_contact: Emergency contact information
        created_at: Record creation timestamp
        updated_at: Record update timestamp
        is_active: Active status
    """
    __tablename__ = 'patients'
    
    id = Column(Integer, primary_key=True)
    patient_id = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    age = Column(Integer)
    gender = Column(String(1))  # M/F
    medical_conditions = Column(JSON)
    emergency_contact = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    health_records = relationship("HealthRecord", back_populates="patient")
    alerts = relationship("Alert", back_populates="patient")
    thresholds = relationship("PatientThreshold", back_populates="patient")


class HealthRecord(Base):
    """
    Health record model for storing vital signs measurements
    
    Attributes:
        id: Primary key
        patient_id: Foreign key to Patient
        timestamp: Measurement timestamp
        heart_rate: Heart rate (BPM)
        spo2: SpO2 percentage
        temperature: Body temperature (Celsius)
        systolic_bp: Systolic blood pressure (mmHg)
        diastolic_bp: Diastolic blood pressure (mmHg)
        mean_arterial_pressure: Mean arterial pressure (mmHg)
        sensor_data: JSON field for raw sensor data
        data_quality: Data quality score (0-1)
        measurement_context: Context information (rest, activity, etc.)
    """
    __tablename__ = 'health_records'
    
    id = Column(Integer, primary_key=True)
    patient_id = Column(String(50), ForeignKey('patients.patient_id'), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Vital signs
    heart_rate = Column(Float)
    spo2 = Column(Float)
    temperature = Column(Float)
    systolic_bp = Column(Float)
    diastolic_bp = Column(Float)
    mean_arterial_pressure = Column(Float)
    
    # Additional data
    sensor_data = Column(JSON)
    data_quality = Column(Float, default=1.0)
    measurement_context = Column(String(50))  # rest, activity, sleep, etc.
    
    # Relationships
    patient = relationship("Patient", back_populates="health_records")


class Alert(Base):
    """
    Alert model for storing alert events
    
    Attributes:
        id: Primary key
        patient_id: Foreign key to Patient
        alert_type: Type of alert (threshold, anomaly, critical)
        severity: Alert severity (low, medium, high, critical)
        message: Alert message
        vital_sign: Affected vital sign
        current_value: Current value that triggered alert
        threshold_value: Threshold value that was exceeded
        timestamp: Alert timestamp
        acknowledged: Whether alert was acknowledged
        acknowledged_at: Acknowledgment timestamp
        resolved: Whether alert was resolved
        resolved_at: Resolution timestamp
    """
    __tablename__ = 'alerts'
    
    id = Column(Integer, primary_key=True)
    patient_id = Column(String(50), ForeignKey('patients.patient_id'), nullable=False)
    alert_type = Column(String(20), nullable=False)  # threshold, anomaly, critical
    severity = Column(String(10), nullable=False)   # low, medium, high, critical
    message = Column(Text, nullable=False)
    vital_sign = Column(String(20))  # heart_rate, spo2, temperature, blood_pressure
    current_value = Column(Float)
    threshold_value = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime)
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime)
    
    # Relationships
    patient = relationship("Patient", back_populates="alerts")


class PatientThreshold(Base):
    """
    Patient-specific threshold model
    
    Attributes:
        id: Primary key
        patient_id: Foreign key to Patient
        vital_sign: Vital sign name
        min_normal: Minimum normal value
        max_normal: Maximum normal value
        min_critical: Minimum critical value
        max_critical: Maximum critical value
        is_active: Whether threshold is active
        created_at: Creation timestamp
        updated_at: Update timestamp
    """
    __tablename__ = 'patient_thresholds'
    
    id = Column(Integer, primary_key=True)
    patient_id = Column(String(50), ForeignKey('patients.patient_id'), nullable=False)
    vital_sign = Column(String(20), nullable=False)
    min_normal = Column(Float)
    max_normal = Column(Float)
    min_critical = Column(Float)
    max_critical = Column(Float)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    patient = relationship("Patient", back_populates="thresholds")


class SensorCalibration(Base):
    """
    Sensor calibration data model
    
    Attributes:
        id: Primary key
        sensor_name: Name of sensor
        calibration_type: Type of calibration
        reference_values: JSON field for reference values
        measured_values: JSON field for measured values
        calibration_factors: JSON field for calibration factors
        calibrated_at: Calibration timestamp
        is_active: Whether calibration is active
        notes: Additional notes
    """
    __tablename__ = 'sensor_calibrations'
    
    id = Column(Integer, primary_key=True)
    sensor_name = Column(String(50), nullable=False)
    calibration_type = Column(String(20), nullable=False)
    reference_values = Column(JSON)
    measured_values = Column(JSON)
    calibration_factors = Column(JSON)
    calibrated_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    notes = Column(Text)


class SystemLog(Base):
    """
    System log model for storing system events
    
    Attributes:
        id: Primary key
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        message: Log message
        module: Source module
        function: Source function
        line_number: Source line number
        timestamp: Log timestamp
        additional_data: JSON field for additional data
    """
    __tablename__ = 'system_logs'
    
    id = Column(Integer, primary_key=True)
    level = Column(String(10), nullable=False)
    message = Column(Text, nullable=False)
    module = Column(String(50))
    function = Column(String(50))
    line_number = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    additional_data = Column(JSON)