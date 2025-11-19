"""
Database Models
SQLAlchemy models cho IoT Health Monitoring System database
Synchronized with MySQL Cloud Schema v2.0.0
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Enum, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.sqlite import JSON
import json
import enum


Base = declarative_base()


# ============================================================
# ENUMS
# ============================================================

class UserRole(str, enum.Enum):
    """User role for device ownership"""
    OWNER = 'owner'
    CAREGIVER = 'caregiver'
    VIEWER = 'viewer'


class SyncStatus(str, enum.Enum):
    """Sync status enumeration"""
    PENDING = 'pending'
    SYNCED = 'synced'
    FAILED = 'failed'


class SyncOperation(str, enum.Enum):
    """Sync operation types"""
    INSERT = 'INSERT'
    UPDATE = 'UPDATE'
    DELETE = 'DELETE'


class AlertSeverity(str, enum.Enum):
    """Alert severity levels"""
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'


class LogLevel(str, enum.Enum):
    """Log level enumeration"""
    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'
    CRITICAL = 'CRITICAL'



# ============================================================
# TABLE MODELS
# ============================================================

class Device(Base):
    """
    Device model for storing IoT device information
    
    Attributes:
        id: Primary key (auto-increment)
        device_id: Unique device identifier (e.g., rpi_bp_001)
        device_name: Human-readable device name
        device_type: Device type (blood_pressure_monitor, vitals_monitor, etc.)
        location: Physical location of device
        ip_address: Current IP address
        firmware_version: Firmware version
        os_version: Operating system version
        is_active: Device active status
        last_seen: Last heartbeat/connection timestamp
        pairing_code: Temporary pairing code for QR
        pairing_qr_data: QR code data (JSON)
        paired_by: User ID who paired device
        paired_at: Pairing timestamp
        created_at: Device creation timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = 'devices'
    
    # Primary identification
    id = Column(Integer, primary_key=True)
    device_id = Column(String(50), unique=True, nullable=False, index=True)
    device_name = Column(String(100), nullable=False)
    device_type = Column(String(50), default='blood_pressure_monitor')
    
    # Location & Network
    location = Column(String(200))
    ip_address = Column(String(45))
    
    # Software & Firmware
    firmware_version = Column(String(20))
    os_version = Column(String(50))
    
    # Status & Connection
    is_active = Column(Boolean, default=True, index=True)
    last_seen = Column(DateTime, index=True)
    
    # Pairing & QR Code
    pairing_code = Column(String(32), unique=True, index=True)
    pairing_qr_data = Column(Text)
    paired_by = Column(String(100))
    paired_at = Column(DateTime)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    ownerships = relationship("DeviceOwnership", back_populates="device", cascade="all, delete-orphan")
    patients = relationship("Patient", back_populates="device")
    health_records = relationship("HealthRecord", back_populates="device")
    alerts = relationship("Alert", back_populates="device")
    calibrations = relationship("SensorCalibration", back_populates="device")
    sync_queue_items = relationship("SyncQueue", back_populates="device")


class DeviceOwnership(Base):
    """
    Device ownership model for multi-user device access control
    
    Attributes:
        id: Primary key
        user_id: User identifier (from Android app)
        device_id: Device identifier (foreign key)
        role: User role (owner, caregiver, viewer)
        nickname: User-defined device nickname
        added_at: When user was granted access
        last_accessed: Last time user accessed device data
    """
    __tablename__ = 'device_ownership'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    device_id = Column(String(50), ForeignKey('devices.device_id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    
    # Access control
    role = Column(String(20), default='owner')  # owner, caregiver, viewer
    nickname = Column(String(100))
    
    # Timestamps
    added_at = Column(DateTime, default=datetime.utcnow)
    last_accessed = Column(DateTime)
    
    # Relationships
    device = relationship("Device", back_populates="ownerships")


class Patient(Base):
    """
    Patient model for storing patient information
    
    Attributes:
        id: Primary key
        patient_id: Unique patient identifier
        device_id: Associated device (nullable, foreign key)
        name: Patient name
        age: Patient age
        gender: Patient gender (M/F/O)
        medical_conditions: JSON field for medical conditions
        emergency_contact: Emergency contact information
        is_active: Active status
        created_at: Record creation timestamp
        updated_at: Record update timestamp
    """
    __tablename__ = 'patients'
    
    # Primary identification
    id = Column(Integer, primary_key=True)
    patient_id = Column(String(50), unique=True, nullable=False, index=True)
    device_id = Column(String(50), ForeignKey('devices.device_id', ondelete='SET NULL', onupdate='CASCADE'), index=True)
    
    # Personal information
    name = Column(String(100), nullable=False)
    age = Column(Integer)
    gender = Column(String(1))  # M/F/O
    
    # Medical information
    medical_conditions = Column(JSON)
    emergency_contact = Column(JSON)
    
    # Status & Timestamps
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    device = relationship("Device", back_populates="patients")
    health_records = relationship("HealthRecord", back_populates="patient")
    alerts = relationship("Alert", back_populates="patient")
    thresholds = relationship("PatientThreshold", back_populates="patient")


class HealthRecord(Base):
    """
    Health record model for storing vital signs measurements
    
    Attributes:
        id: Primary key
        patient_id: Foreign key to Patient
        device_id: Device that recorded measurement (foreign key)
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
        sync_status: Cloud sync status (pending, synced, failed)
        synced_at: When record was synced to cloud
    """
    __tablename__ = 'health_records'
    
    # Primary identification
    id = Column(Integer, primary_key=True, autoincrement=True)  # Integer for SQLite autoincrement
    patient_id = Column(String(50), ForeignKey('patients.patient_id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    device_id = Column(String(50), ForeignKey('devices.device_id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Vital signs
    heart_rate = Column(Float)
    spo2 = Column(Float)
    temperature = Column(Float)
    systolic_bp = Column(Float)
    diastolic_bp = Column(Float)
    mean_arterial_pressure = Column(Float)
    
    # Additional data
    sensor_data = Column(JSON)
    data_quality = Column(Float, default=1.0, index=True)
    measurement_context = Column(String(50), default='rest')
    
    # Sync status
    sync_status = Column(String(20), default='pending', index=True)  # pending, synced, failed
    synced_at = Column(DateTime)
    
    # Relationships
    patient = relationship("Patient", back_populates="health_records")
    device = relationship("Device", back_populates="health_records")


class Alert(Base):
    """
    Alert model for storing alert events
    
    Attributes:
        id: Primary key
        patient_id: Foreign key to Patient
        device_id: Device that generated alert (foreign key)
        health_record_id: Associated health record ID (optional)
        alert_type: Type of alert (threshold, anomaly, critical)
        severity: Alert severity (low, medium, high, critical)
        vital_sign: Affected vital sign
        message: Alert message
        current_value: Current value that triggered alert
        threshold_value: Threshold value that was exceeded
        timestamp: Alert timestamp
        acknowledged: Whether alert was acknowledged
        acknowledged_at: Acknowledgment timestamp
        acknowledged_by: User who acknowledged
        resolved: Whether alert was resolved
        resolved_at: Resolution timestamp
        notification_sent: Whether notification was sent
        notification_method: Notification method used
    """
    __tablename__ = 'alerts'
    
    # Primary identification
    id = Column(Integer, primary_key=True, autoincrement=True)  # Integer for SQLite autoincrement
    patient_id = Column(String(50), ForeignKey('patients.patient_id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    device_id = Column(String(50), ForeignKey('devices.device_id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    health_record_id = Column(BigInteger)  # Optional reference to health_records.id
    
    # Alert information
    alert_type = Column(String(50), nullable=False)  # threshold, anomaly, critical
    severity = Column(String(20), nullable=False, index=True)  # low, medium, high, critical
    vital_sign = Column(String(50))  # heart_rate, spo2, temperature, blood_pressure
    message = Column(Text, nullable=False)
    
    # Threshold values
    current_value = Column(Float)
    threshold_value = Column(Float)
    
    # Timestamps
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Acknowledgment
    acknowledged = Column(Boolean, default=False, index=True)
    acknowledged_at = Column(DateTime)
    acknowledged_by = Column(String(100))
    
    # Resolution
    resolved = Column(Boolean, default=False, index=True)
    resolved_at = Column(DateTime)
    
    # Notification
    notification_sent = Column(Boolean, default=False)
    notification_method = Column(String(50))  # mqtt, fcm, email
    
    # Relationships
    patient = relationship("Patient", back_populates="alerts")
    device = relationship("Device", back_populates="alerts")


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
    patient_id = Column(String(50), ForeignKey('patients.patient_id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    vital_sign = Column(String(50), nullable=False, index=True)
    
    # Normal range
    min_normal = Column(Float)
    max_normal = Column(Float)
    
    # Critical range
    min_critical = Column(Float)
    max_critical = Column(Float)
    
    # Status & Timestamps
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    patient = relationship("Patient", back_populates="thresholds")


class SensorCalibration(Base):
    """
    Sensor calibration data model
    
    Attributes:
        id: Primary key
        device_id: Device identifier (foreign key)
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
    device_id = Column(String(50), ForeignKey('devices.device_id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    sensor_name = Column(String(50), nullable=False, index=True)
    
    # Calibration data
    calibration_type = Column(String(50), nullable=False)
    reference_values = Column(JSON)
    measured_values = Column(JSON)
    calibration_factors = Column(JSON, nullable=False)
    
    # Metadata
    calibrated_at = Column(DateTime, default=datetime.utcnow, index=True)
    is_active = Column(Boolean, default=True, index=True)
    notes = Column(Text)
    
    # Relationships
    device = relationship("Device", back_populates="calibrations")


class SyncQueue(Base):
    """
    Store & Forward queue model for offline sync
    
    Attributes:
        id: Primary key
        device_id: Device identifier (foreign key)
        table_name: Target table name
        operation: Operation type (INSERT, UPDATE, DELETE)
        record_id: Record identifier
        data_snapshot: Data snapshot for operation (JSON)
        priority: Priority level (1=highest, 10=lowest)
        created_at: When queued
        sync_status: Sync status (pending, syncing, success, failed)
        sync_attempts: Number of sync attempts
        last_sync_attempt: Last attempt timestamp
        error_message: Error message if failed
    """
    __tablename__ = 'sync_queue'
    
    id = Column(Integer, primary_key=True, autoincrement=True)  # Integer for SQLite autoincrement
    device_id = Column(String(50), ForeignKey('devices.device_id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    
    # Queue item details
    table_name = Column(String(50), nullable=False)
    operation = Column(String(20), nullable=False)  # INSERT, UPDATE, DELETE
    record_id = Column(String(100), nullable=False)
    data_snapshot = Column(JSON)
    priority = Column(Integer, default=5, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Sync status
    sync_status = Column(String(20), default='pending', index=True)  # pending, syncing, success, failed
    sync_attempts = Column(Integer, default=0)
    last_sync_attempt = Column(DateTime)
    error_message = Column(Text)
    
    # Relationships
    device = relationship("Device", back_populates="sync_queue_items")


class SystemLog(Base):
    """
    System log model for storing system events
    
    Attributes:
        id: Primary key
        device_id: Device identifier (nullable, foreign key)
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        message: Log message
        module: Source module
        function_name: Source function
        line_number: Source line number
        timestamp: Log timestamp
        additional_data: JSON field for additional data
    """
    __tablename__ = 'system_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)  # Integer for SQLite autoincrement
    device_id = Column(String(50), ForeignKey('devices.device_id', ondelete='SET NULL', onupdate='CASCADE'), index=True)
    
    # Log details
    level = Column(String(20), nullable=False, index=True)  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    message = Column(Text, nullable=False)
    module = Column(String(100), index=True)
    function_name = Column(String(100))
    line_number = Column(Integer)
    
    # Timestamp
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Additional data
    additional_data = Column(JSON)
