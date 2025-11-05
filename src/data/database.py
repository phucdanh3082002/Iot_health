"""
Database Manager
Database management và operations cho IoT Health Monitoring System
"""

from typing import Dict, Any, Optional, List, Tuple
import logging
import sqlite3
import shutil
from contextlib import contextmanager
from sqlalchemy import create_engine, MetaData, desc, and_, or_
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta
import os
import json

from .models import Base, Patient, HealthRecord, Alert, PatientThreshold, SensorCalibration, SystemLog


class DatabaseManager:
    """
    Database manager cho SQLite database operations
    
    Attributes:
        config (Dict): Database configuration
        db_path (str): Path to SQLite database file
        engine: SQLAlchemy engine
        SessionLocal: SQLAlchemy session factory
        cloud_sync_manager: Cloud sync manager instance (optional)
        logger (logging.Logger): Logger instance
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize database manager
        
        Args:
            config: Database configuration
        """
        self.logger = logging.getLogger(__name__)
        self.config = config.get('database', {})
        self.full_config = config  # Store full config for cloud sync
        
        # Get database path from config
        self.db_path = self.config.get('path', 'data/health_monitor.db')
        
        # Cloud sync manager (initialized later if enabled)
        self.cloud_sync_manager = None
        
        # Ensure data directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
            self.logger.info(f"Created database directory: {db_dir}")
        
        # Create SQLAlchemy engine
        db_url = f"sqlite:///{self.db_path}"
        self.engine = create_engine(
            db_url,
            echo=False,  # Set True for SQL debugging
            pool_pre_ping=True,  # Verify connections
            connect_args={
                'check_same_thread': False,  # Allow multi-threading
                'timeout': 30  # Increase timeout to 30 seconds
            }
        )
        
        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        self.logger.info(f"DatabaseManager initialized: {self.db_path}")
    
    def initialize(self) -> bool:
        """
        Initialize database and create tables
        Also initializes cloud sync if enabled
        
        Returns:
            bool: True if initialization successful
        """
        try:
            # Create all tables
            Base.metadata.create_all(bind=self.engine)
            self.logger.info("Database tables created successfully")
            
            # Verify tables exist (SQLAlchemy 2.0 compatible)
            from sqlalchemy import inspect
            inspector = inspect(self.engine)
            tables = inspector.get_table_names()
            self.logger.info(f"Tables in database: {tables}")
            
            # Initialize cloud sync if enabled
            self._initialize_cloud_sync()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Database initialization failed: {e}", exc_info=True)
            return False
    
    def _initialize_cloud_sync(self):
        """
        Initialize cloud sync manager if enabled in config
        """
        try:
            cloud_config = self.full_config.get('cloud', {})
            
            if not cloud_config.get('enabled', False):
                self.logger.info("Cloud sync is disabled")
                return
            
            # Import CloudSyncManager
            from src.communication.cloud_sync_manager import CloudSyncManager
            
            # Create sync manager instance
            self.cloud_sync_manager = CloudSyncManager(self, cloud_config)
            
            # Try to connect to cloud
            if self.cloud_sync_manager.connect_to_cloud():
                self.logger.info("Cloud sync initialized and connected")
            else:
                self.logger.warning("Cloud sync initialized but connection failed (will retry)")
                
        except ImportError as e:
            self.logger.error(f"Failed to import CloudSyncManager: {e}")
        except Exception as e:
            self.logger.error(f"Failed to initialize cloud sync: {e}")
    
    def close(self):
        """
        Close database connections and cloud sync
        """
        try:
            # Disconnect cloud sync
            if self.cloud_sync_manager:
                self.cloud_sync_manager.disconnect_from_cloud()
            
            if self.engine:
                self.engine.dispose()
                self.logger.info("Database connections closed")
        except Exception as e:
            self.logger.error(f"Error closing database: {e}")
    
    @contextmanager
    def get_session(self):
        """
        Context manager for database sessions
        
        Yields:
            SQLAlchemy session
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            self.logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def create_patient(self, patient_data: Dict[str, Any]) -> Optional[str]:
        """
        Create new patient record
        
        Args:
            patient_data: Patient information
            
        Returns:
            Patient ID if successful, None if error
        """
        try:
            with self.get_session() as session:
                # Check if patient already exists
                existing = session.query(Patient).filter_by(
                    patient_id=patient_data['patient_id']
                ).first()
                
                if existing:
                    self.logger.warning(f"Patient {patient_data['patient_id']} already exists")
                    return existing.patient_id
                
                # Create new patient
                patient = Patient(
                    patient_id=patient_data['patient_id'],
                    name=patient_data['name'],
                    age=patient_data.get('age'),
                    gender=patient_data.get('gender'),
                    medical_conditions=patient_data.get('medical_conditions'),
                    emergency_contact=patient_data.get('emergency_contact')
                )
                
                session.add(patient)
                session.flush()
                
                # Create default thresholds inline (avoid nested transaction)
                default_thresholds = {
                    'heart_rate': {
                        'min_normal': 60.0,
                        'max_normal': 100.0,
                        'min_critical': 40.0,
                        'max_critical': 150.0
                    },
                    'spo2': {
                        'min_normal': 95.0,
                        'max_normal': 100.0,
                        'min_critical': 90.0,
                        'max_critical': 100.0
                    },
                    'temperature': {
                        'min_normal': 36.0,
                        'max_normal': 37.5,
                        'min_critical': 35.0,
                        'max_critical': 39.0
                    },
                    'systolic_bp': {
                        'min_normal': 90.0,
                        'max_normal': 140.0,
                        'min_critical': 70.0,
                        'max_critical': 180.0
                    },
                    'diastolic_bp': {
                        'min_normal': 60.0,
                        'max_normal': 90.0,
                        'min_critical': 40.0,
                        'max_critical': 110.0
                    }
                }
                
                # Create threshold records
                for vital_sign, values in default_thresholds.items():
                    threshold = PatientThreshold(
                        patient_id=patient_data['patient_id'],
                        vital_sign=vital_sign,
                        min_normal=values.get('min_normal'),
                        max_normal=values.get('max_normal'),
                        min_critical=values.get('min_critical'),
                        max_critical=values.get('max_critical'),
                        is_active=True
                    )
                    session.add(threshold)
                
                self.logger.info(f"Created patient: {patient.patient_id}")
                return patient.patient_id
                
        except Exception as e:
            self.logger.error(f"Error creating patient: {e}", exc_info=True)
            return None
    
    def get_patient(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """
        Get patient information
        
        Args:
            patient_id: Patient identifier
            
        Returns:
            Patient data dictionary or None if not found
        """
        try:
            with self.get_session() as session:
                patient = session.query(Patient).filter_by(
                    patient_id=patient_id
                ).first()
                
                if not patient:
                    return None
                
                return {
                    'patient_id': patient.patient_id,
                    'name': patient.name,
                    'age': patient.age,
                    'gender': patient.gender,
                    'medical_conditions': patient.medical_conditions,
                    'emergency_contact': patient.emergency_contact,
                    'created_at': patient.created_at.isoformat(),
                    'is_active': patient.is_active
                }
                
        except Exception as e:
            self.logger.error(f"Error getting patient: {e}")
            return None
    
    def update_patient(self, patient_id: str, update_data: Dict[str, Any]) -> bool:
        """
        Update patient information
        
        Args:
            patient_id: Patient identifier
            update_data: Data to update
            
        Returns:
            bool: True if update successful
        """
        try:
            with self.get_session() as session:
                patient = session.query(Patient).filter_by(
                    patient_id=patient_id
                ).first()
                
                if not patient:
                    self.logger.warning(f"Patient {patient_id} not found")
                    return False
                
                # Update fields
                for key, value in update_data.items():
                    if hasattr(patient, key):
                        setattr(patient, key, value)
                
                patient.updated_at = datetime.utcnow()
                
                self.logger.info(f"Updated patient: {patient_id}")
                return True
                
        except Exception as e:
            self.logger.error(f"Error updating patient: {e}")
            return False
    
    def save_health_record(self, health_data: Dict[str, Any]) -> Optional[int]:
        """
        Save health measurement record
        
        Args:
            health_data: Health measurement data
            
        Returns:
            Record ID if successful, None if error
        """
        try:
            # Validate data first
            if not self._validate_health_data(health_data):
                self.logger.warning("Invalid health data, skipping save")
                return None
            
            with self.get_session() as session:
                record = HealthRecord(
                    patient_id=health_data['patient_id'],
                    timestamp=health_data.get('timestamp', datetime.utcnow()),
                    heart_rate=health_data.get('heart_rate'),
                    spo2=health_data.get('spo2'),
                    temperature=health_data.get('temperature'),
                    systolic_bp=health_data.get('systolic_bp'),
                    diastolic_bp=health_data.get('diastolic_bp'),
                    mean_arterial_pressure=health_data.get('mean_arterial_pressure'),
                    sensor_data=health_data.get('sensor_data'),
                    data_quality=health_data.get('data_quality', 1.0),
                    measurement_context=health_data.get('measurement_context', 'rest')
                )
                
                session.add(record)
                session.flush()
                
                record_id = record.id
                
                self.logger.info(f"Saved health record ID={record_id} for patient {health_data['patient_id']}")
                
                # Trigger cloud sync if enabled
                if self.cloud_sync_manager and self.cloud_sync_manager.sync_config.get('sync_health_records', True):
                    try:
                        self.cloud_sync_manager.push_health_record(record_id)
                    except Exception as sync_error:
                        self.logger.warning(f"Cloud sync failed for record {record_id}: {sync_error}")
                
                return record_id
                
        except Exception as e:
            self.logger.error(f"Error saving health record: {e}", exc_info=True)
            return None
    
    def get_health_records(self, patient_id: str, start_time: Optional[datetime] = None,
                          end_time: Optional[datetime] = None, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Get health records for patient
        
        Args:
            patient_id: Patient identifier
            start_time: Start time filter
            end_time: End time filter
            limit: Maximum number of records
            
        Returns:
            List of health records
        """
        try:
            with self.get_session() as session:
                query = session.query(HealthRecord).filter_by(patient_id=patient_id)
                
                # Apply time filters
                if start_time:
                    query = query.filter(HealthRecord.timestamp >= start_time)
                if end_time:
                    query = query.filter(HealthRecord.timestamp <= end_time)
                
                # Order by timestamp descending and limit
                records = query.order_by(desc(HealthRecord.timestamp)).limit(limit).all()
                
                # Convert to dict list
                result = []
                for record in records:
                    result.append({
                        'id': record.id,
                        'patient_id': record.patient_id,
                        'timestamp': record.timestamp.isoformat(),
                        'heart_rate': record.heart_rate,
                        'spo2': record.spo2,
                        'temperature': record.temperature,
                        'systolic_bp': record.systolic_bp,
                        'diastolic_bp': record.diastolic_bp,
                        'mean_arterial_pressure': record.mean_arterial_pressure,
                        'sensor_data': record.sensor_data,
                        'data_quality': record.data_quality,
                        'measurement_context': record.measurement_context
                    })
                
                return result
                
        except Exception as e:
            self.logger.error(f"Error getting health records: {e}")
            return []
    
    def get_latest_vitals(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """
        Get latest vital signs for patient
        
        Args:
            patient_id: Patient identifier
            
        Returns:
            Latest vitals data or None if not found
        """
        try:
            with self.get_session() as session:
                record = session.query(HealthRecord).filter_by(
                    patient_id=patient_id
                ).order_by(desc(HealthRecord.timestamp)).first()
                
                if not record:
                    return None
                
                return {
                    'timestamp': record.timestamp.isoformat(),
                    'heart_rate': record.heart_rate,
                    'spo2': record.spo2,
                    'temperature': record.temperature,
                    'systolic_bp': record.systolic_bp,
                    'diastolic_bp': record.diastolic_bp,
                    'mean_arterial_pressure': record.mean_arterial_pressure,
                    'data_quality': record.data_quality
                }
                
        except Exception as e:
            self.logger.error(f"Error getting latest vitals: {e}")
            return None
    
    def save_alert(self, alert_data: Dict[str, Any]) -> Optional[int]:
        """
        Save alert record
        
        Args:
            alert_data: Alert information
            
        Returns:
            Alert ID if successful, None if error
        """
        try:
            with self.get_session() as session:
                alert = Alert(
                    patient_id=alert_data['patient_id'],
                    alert_type=alert_data['alert_type'],
                    severity=alert_data['severity'],
                    message=alert_data['message'],
                    vital_sign=alert_data.get('vital_sign'),
                    current_value=alert_data.get('current_value'),
                    threshold_value=alert_data.get('threshold_value'),
                    timestamp=alert_data.get('timestamp', datetime.utcnow())
                )
                
                session.add(alert)
                session.flush()
                
                alert_id = alert.id
                
                self.logger.warning(f"Saved alert ID={alert_id}: {alert.severity} - {alert.message}")
                
                # Trigger cloud sync if enabled
                if self.cloud_sync_manager and self.cloud_sync_manager.sync_config.get('sync_alerts', True):
                    try:
                        self.cloud_sync_manager.push_alert(alert_id)
                    except Exception as sync_error:
                        self.logger.warning(f"Cloud sync failed for alert {alert_id}: {sync_error}")
                
                return alert_id
                
        except Exception as e:
            self.logger.error(f"Error saving alert: {e}")
            return None
    
    def get_active_alerts(self, patient_id: str) -> List[Dict[str, Any]]:
        """
        Get active alerts for patient
        
        Args:
            patient_id: Patient identifier
            
        Returns:
            List of active alerts
        """
        try:
            with self.get_session() as session:
                alerts = session.query(Alert).filter(
                    and_(
                        Alert.patient_id == patient_id,
                        Alert.resolved == False
                    )
                ).order_by(desc(Alert.timestamp)).all()
                
                result = []
                for alert in alerts:
                    result.append({
                        'id': alert.id,
                        'alert_type': alert.alert_type,
                        'severity': alert.severity,
                        'message': alert.message,
                        'vital_sign': alert.vital_sign,
                        'current_value': alert.current_value,
                        'threshold_value': alert.threshold_value,
                        'timestamp': alert.timestamp.isoformat(),
                        'acknowledged': alert.acknowledged
                    })
                
                return result
                
        except Exception as e:
            self.logger.error(f"Error getting active alerts: {e}")
            return []
    
    def acknowledge_alert(self, alert_id: int) -> bool:
        """
        Acknowledge alert
        
        Args:
            alert_id: Alert identifier
            
        Returns:
            bool: True if acknowledgment successful
        """
        try:
            with self.get_session() as session:
                alert = session.query(Alert).filter_by(id=alert_id).first()
                
                if not alert:
                    self.logger.warning(f"Alert {alert_id} not found")
                    return False
                
                alert.acknowledged = True
                alert.acknowledged_at = datetime.utcnow()
                
                self.logger.info(f"Acknowledged alert {alert_id}")
                return True
                
        except Exception as e:
            self.logger.error(f"Error acknowledging alert: {e}")
            return False
    
    def resolve_alert(self, alert_id: int) -> bool:
        """
        Resolve alert
        
        Args:
            alert_id: Alert identifier
            
        Returns:
            bool: True if resolution successful
        """
        try:
            with self.get_session() as session:
                alert = session.query(Alert).filter_by(id=alert_id).first()
                
                if not alert:
                    self.logger.warning(f"Alert {alert_id} not found")
                    return False
                
                alert.resolved = True
                alert.resolved_at = datetime.utcnow()
                
                self.logger.info(f"Resolved alert {alert_id}")
                return True
                
        except Exception as e:
            self.logger.error(f"Error resolving alert: {e}")
            return False
    
    def save_patient_thresholds(self, patient_id: str, thresholds: Dict[str, Dict[str, float]]) -> bool:
        """
        Save patient-specific thresholds
        
        Args:
            patient_id: Patient identifier
            thresholds: Dictionary of threshold values
            
        Returns:
            bool: True if save successful
        """
        try:
            with self.get_session() as session:
                # Deactivate old thresholds
                session.query(PatientThreshold).filter_by(
                    patient_id=patient_id
                ).update({'is_active': False})
                
                # Create new thresholds
                for vital_sign, values in thresholds.items():
                    threshold = PatientThreshold(
                        patient_id=patient_id,
                        vital_sign=vital_sign,
                        min_normal=values.get('min_normal'),
                        max_normal=values.get('max_normal'),
                        min_critical=values.get('min_critical'),
                        max_critical=values.get('max_critical'),
                        is_active=True
                    )
                    session.add(threshold)
                
                self.logger.info(f"Saved thresholds for patient {patient_id}")
                return True
                
        except Exception as e:
            self.logger.error(f"Error saving thresholds: {e}")
            return False
    
    def get_patient_thresholds(self, patient_id: str) -> Dict[str, Dict[str, float]]:
        """
        Get patient-specific thresholds
        
        Args:
            patient_id: Patient identifier
            
        Returns:
            Dictionary of threshold values
        """
        try:
            with self.get_session() as session:
                thresholds = session.query(PatientThreshold).filter(
                    and_(
                        PatientThreshold.patient_id == patient_id,
                        PatientThreshold.is_active == True
                    )
                ).all()
                
                result = {}
                for threshold in thresholds:
                    result[threshold.vital_sign] = {
                        'min_normal': threshold.min_normal,
                        'max_normal': threshold.max_normal,
                        'min_critical': threshold.min_critical,
                        'max_critical': threshold.max_critical
                    }
                
                return result
                
        except Exception as e:
            self.logger.error(f"Error getting thresholds: {e}")
            return {}
    
    def save_sensor_calibration(self, calibration_data: Dict[str, Any]) -> Optional[int]:
        """
        Save sensor calibration data
        
        Args:
            calibration_data: Calibration information
            
        Returns:
            Calibration ID if successful, None if error
        """
        try:
            with self.get_session() as session:
                # Deactivate old calibrations for this sensor
                session.query(SensorCalibration).filter_by(
                    sensor_name=calibration_data['sensor_name']
                ).update({'is_active': False})
                
                # Create new calibration
                calibration = SensorCalibration(
                    sensor_name=calibration_data['sensor_name'],
                    calibration_type=calibration_data['calibration_type'],
                    reference_values=calibration_data.get('reference_values'),
                    measured_values=calibration_data.get('measured_values'),
                    calibration_factors=calibration_data.get('calibration_factors'),
                    calibrated_at=calibration_data.get('calibrated_at', datetime.utcnow()),
                    is_active=True,
                    notes=calibration_data.get('notes')
                )
                
                session.add(calibration)
                session.flush()
                
                calibration_id = calibration.id
                
                self.logger.info(f"Saved calibration ID={calibration_id} for {calibration_data['sensor_name']}")
                
                # Trigger cloud sync if enabled
                if self.cloud_sync_manager and self.cloud_sync_manager.sync_config.get('sync_calibrations', True):
                    try:
                        self.cloud_sync_manager.push_calibration(calibration_id)
                    except Exception as sync_error:
                        self.logger.warning(f"Cloud sync failed for calibration {calibration_id}: {sync_error}")
                
                return calibration_id
                
        except Exception as e:
            self.logger.error(f"Error saving calibration: {e}")
            return None
    
    def get_sensor_calibration(self, sensor_name: str) -> Optional[Dict[str, Any]]:
        """
        Get active sensor calibration
        
        Args:
            sensor_name: Name of sensor
            
        Returns:
            Calibration data or None if not found
        """
        try:
            with self.get_session() as session:
                calibration = session.query(SensorCalibration).filter(
                    and_(
                        SensorCalibration.sensor_name == sensor_name,
                        SensorCalibration.is_active == True
                    )
                ).first()
                
                if not calibration:
                    return None
                
                return {
                    'id': calibration.id,
                    'sensor_name': calibration.sensor_name,
                    'calibration_type': calibration.calibration_type,
                    'reference_values': calibration.reference_values,
                    'measured_values': calibration.measured_values,
                    'calibration_factors': calibration.calibration_factors,
                    'calibrated_at': calibration.calibrated_at.isoformat(),
                    'notes': calibration.notes
                }
                
        except Exception as e:
            self.logger.error(f"Error getting calibration: {e}")
            return None
    
    def log_system_event(self, level: str, message: str, module: str = None,
                        function: str = None, additional_data: Dict[str, Any] = None):
        """
        Log system event to database
        
        Args:
            level: Log level
            message: Log message
            module: Source module
            function: Source function
            additional_data: Additional data
        """
        try:
            with self.get_session() as session:
                log = SystemLog(
                    level=level,
                    message=message,
                    module=module,
                    function=function,
                    timestamp=datetime.utcnow(),
                    additional_data=additional_data
                )
                
                session.add(log)
                
        except Exception as e:
            # Don't log error for logging failures (avoid infinite loop)
            pass
    
    def get_health_statistics(self, patient_id: str, time_range: str) -> Dict[str, Any]:
        """
        Get health statistics for patient
        
        Args:
            patient_id: Patient identifier
            time_range: Time range ('24h', '7d', '30d')
            
        Returns:
            Dictionary containing statistics
        """
        try:
            # Parse time range
            time_map = {
                '24h': timedelta(hours=24),
                '7d': timedelta(days=7),
                '30d': timedelta(days=30)
            }
            
            delta = time_map.get(time_range, timedelta(days=7))
            start_time = datetime.utcnow() - delta
            
            # Get records
            records = self.get_health_records(patient_id, start_time=start_time)
            
            if not records:
                return {}
            
            # Calculate statistics
            stats = {
                'time_range': time_range,
                'record_count': len(records),
                'start_time': start_time.isoformat(),
                'end_time': datetime.utcnow().isoformat()
            }
            
            # Calculate averages and ranges for each vital sign
            vitals = ['heart_rate', 'spo2', 'temperature', 'systolic_bp', 'diastolic_bp']
            
            for vital in vitals:
                values = [r[vital] for r in records if r[vital] is not None]
                
                if values:
                    stats[vital] = {
                        'avg': round(sum(values) / len(values), 2),
                        'min': round(min(values), 2),
                        'max': round(max(values), 2),
                        'count': len(values)
                    }
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error calculating statistics: {e}")
            return {}
    
    def cleanup_old_records(self, days_to_keep: int = 90) -> int:
        """
        Cleanup old health records
        
        Args:
            days_to_keep: Number of days to keep
            
        Returns:
            Number of records deleted
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
            
            with self.get_session() as session:
                deleted = session.query(HealthRecord).filter(
                    HealthRecord.timestamp < cutoff_date
                ).delete()
                
                self.logger.info(f"Deleted {deleted} old health records (older than {days_to_keep} days)")
                return deleted
                
        except Exception as e:
            self.logger.error(f"Error cleaning up records: {e}")
            return 0
    
    def backup_database(self, backup_path: str) -> bool:
        """
        Create database backup
        
        Args:
            backup_path: Path for backup file
            
        Returns:
            bool: True if backup successful
        """
        try:
            # Close all connections first
            self.engine.dispose()
            
            # Copy database file
            shutil.copy2(self.db_path, backup_path)
            
            # Recreate engine
            db_url = f"sqlite:///{self.db_path}"
            self.engine = create_engine(
                db_url,
                echo=False,
                pool_pre_ping=True,
                connect_args={'check_same_thread': False}
            )
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
            
            self.logger.info(f"Database backed up to {backup_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error backing up database: {e}")
            return False
    
    def restore_database(self, backup_path: str) -> bool:
        """
        Restore database from backup
        
        Args:
            backup_path: Path to backup file
            
        Returns:
            bool: True if restore successful
        """
        try:
            if not os.path.exists(backup_path):
                self.logger.error(f"Backup file not found: {backup_path}")
                return False
            
            # Close all connections
            self.engine.dispose()
            
            # Restore database file
            shutil.copy2(backup_path, self.db_path)
            
            # Recreate engine
            db_url = f"sqlite:///{self.db_path}"
            self.engine = create_engine(
                db_url,
                echo=False,
                pool_pre_ping=True,
                connect_args={'check_same_thread': False}
            )
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
            
            self.logger.info(f"Database restored from {backup_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error restoring database: {e}")
            return False
    
    def get_database_info(self) -> Dict[str, Any]:
        """
        Get database information and statistics
        
        Returns:
            Dictionary containing database info
        """
        try:
            info = {
                'db_path': self.db_path,
                'db_size_mb': round(os.path.getsize(self.db_path) / (1024 * 1024), 2) if os.path.exists(self.db_path) else 0,
                'tables': {}
            }
            
            with self.get_session() as session:
                # Count records in each table
                info['tables']['patients'] = session.query(Patient).count()
                info['tables']['health_records'] = session.query(HealthRecord).count()
                info['tables']['alerts'] = session.query(Alert).count()
                info['tables']['thresholds'] = session.query(PatientThreshold).count()
                info['tables']['calibrations'] = session.query(SensorCalibration).count()
                info['tables']['system_logs'] = session.query(SystemLog).count()
            
            return info
            
        except Exception as e:
            self.logger.error(f"Error getting database info: {e}")
            return {}
    
    def _create_default_thresholds(self, patient_id: str):
        """
        Create default thresholds for new patient
        
        Args:
            patient_id: Patient identifier
        """
        try:
            default_thresholds = {
                'heart_rate': {
                    'min_normal': 60.0,
                    'max_normal': 100.0,
                    'min_critical': 40.0,
                    'max_critical': 150.0
                },
                'spo2': {
                    'min_normal': 95.0,
                    'max_normal': 100.0,
                    'min_critical': 90.0,
                    'max_critical': 100.0
                },
                'temperature': {
                    'min_normal': 36.0,
                    'max_normal': 37.5,
                    'min_critical': 35.0,
                    'max_critical': 39.0
                },
                'systolic_bp': {
                    'min_normal': 90.0,
                    'max_normal': 140.0,
                    'min_critical': 70.0,
                    'max_critical': 180.0
                },
                'diastolic_bp': {
                    'min_normal': 60.0,
                    'max_normal': 90.0,
                    'min_critical': 40.0,
                    'max_critical': 110.0
                }
            }
            
            self.save_patient_thresholds(patient_id, default_thresholds)
            self.logger.info(f"Created default thresholds for patient {patient_id}")
            
        except Exception as e:
            self.logger.error(f"Error creating default thresholds: {e}")
    
    def _validate_health_data(self, health_data: Dict[str, Any]) -> bool:
        """
        Validate health data before saving
        
        Args:
            health_data: Health data to validate
            
        Returns:
            bool: True if data is valid
        """
        # Check required fields
        if 'patient_id' not in health_data:
            self.logger.warning("Missing patient_id in health data")
            return False
        
        # Validate vital sign ranges
        validations = {
            'heart_rate': (30, 200),
            'spo2': (0, 100),
            'temperature': (30, 45),
            'systolic_bp': (50, 250),
            'diastolic_bp': (30, 150)
        }
        
        for vital, (min_val, max_val) in validations.items():
            if vital in health_data and health_data[vital] is not None:
                value = health_data[vital]
                if not (min_val <= value <= max_val):
                    self.logger.warning(
                        f"Invalid {vital} value: {value} (expected {min_val}-{max_val})"
                    )
                    # Don't reject, just warn
        
        return True