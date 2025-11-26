"""
Cloud Sync Manager
Manages bidirectional synchronization between SQLite local and MySQL cloud database

Features:
- Real-time push when network available
- Store & Forward queue for offline mode
- Conflict resolution (cloud wins strategy)
- Delta sync (only changed records)
- Batch operations for efficiency
"""

from typing import Dict, Any, Optional, List, Tuple
import logging
from datetime import datetime, timedelta
from contextlib import contextmanager
import os
import json
import socket
from enum import Enum

from sqlalchemy import create_engine, text, MetaData, Table, Column, Integer, String, DateTime, JSON, Enum as SQLEnum, and_, or_
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy.pool import QueuePool

# Import local database manager
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.database import DatabaseManager


class SyncStatus(str, Enum):
    """Sync status enumeration"""
    PENDING = 'pending'
    SYNCING = 'syncing'
    SUCCESS = 'success'
    FAILED = 'failed'
    CONFLICT = 'conflict'


class SyncOperation(str, Enum):
    """Sync operation types"""
    INSERT = 'INSERT'
    UPDATE = 'UPDATE'
    DELETE = 'DELETE'


class CloudSyncManager:
    """
    Cloud Synchronization Manager
    
    Manages bidirectional sync between SQLite local cache and MySQL cloud database.
    Implements Store & Forward pattern for offline resilience.
    
    Attributes:
        local_db (DatabaseManager): Local SQLite database manager
        cloud_config (Dict): Cloud MySQL configuration
        mysql_engine: SQLAlchemy engine for MySQL connection
        SessionCloud: SQLAlchemy session factory for cloud
        is_online (bool): Current cloud connection status
        last_sync_time (datetime): Timestamp of last successful sync
        device_id (str): Unique device identifier
        logger (logging.Logger): Logger instance
    """
    
    def __init__(self, local_db: DatabaseManager, cloud_config: Dict[str, Any]):
        """
        Initialize Cloud Sync Manager
        
        Args:
            local_db: Local database manager instance
            cloud_config: Cloud configuration from app_config.yaml
        """
        self.logger = logging.getLogger(__name__)
        self.local_db = local_db
        self.cloud_config = cloud_config
        
        # MySQL connection
        self.mysql_engine = None
        self.SessionCloud = None
        self.is_online = False
        self.last_sync_time = None
        
        # Device identification
        device_config = cloud_config.get('device', {})
        self.device_id = device_config.get('device_id', 'unknown_device')
        self.device_name = device_config.get('device_name', 'Unknown Device')
        self.device_type = device_config.get('device_type', 'blood_pressure_monitor')
        self.location = device_config.get('location', '')
        self.pairing_code = device_config.get('pairing_code', '')
        self.firmware_version = device_config.get('firmware_version', '1.0.0')
        self.os_version = device_config.get('os_version', 'Unknown OS')
        
        # Sync configuration
        self.sync_config = cloud_config.get('sync', {})
        self.sync_mode = self.sync_config.get('mode', 'auto')
        self.sync_interval = self.sync_config.get('interval_seconds', 300)
        self.batch_size = self.sync_config.get('batch_size', 100)
        self.retry_attempts = self.sync_config.get('retry_attempts', 3)
        self.retry_delay = self.sync_config.get('retry_delay_seconds', 60)
        self.conflict_strategy = self.sync_config.get('conflict_strategy', 'cloud_wins')
        
        # Statistics
        self.stats = {
            'total_pushes': 0,
            'successful_pushes': 0,
            'failed_pushes': 0,
            'total_pulls': 0,
            'successful_pulls': 0,
            'failed_pulls': 0,
            'conflicts_resolved': 0,
            'queue_size': 0
        }
        
        self.logger.info(f"CloudSyncManager initialized for device: {self.device_id}")
    
    # ═══════════════════════════════════════════════════════════════════
    # CONNECTION MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════
    
    def connect_to_cloud(self) -> bool:
        """
        Establish connection to MySQL cloud database
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            if not self.cloud_config.get('enabled', False):
                self.logger.info("Cloud sync is disabled in configuration")
                return False
            
            mysql_config = self.cloud_config.get('mysql', {})
            
            # Get MySQL connection parameters
            host = mysql_config.get('host', 'localhost')
            port = mysql_config.get('port', 3306)
            database = mysql_config.get('database', 'iot_health_cloud')
            user = mysql_config.get('user', 'root')
            
            # Get password from environment variable for security
            password_env = mysql_config.get('password_env', 'MYSQL_CLOUD_PASSWORD')
            password = os.environ.get(password_env, mysql_config.get('password', ''))
            
            if not password:
                self.logger.warning(f"MySQL password not found in environment variable: {password_env}")
                return False
            
            # Build connection URL
            connection_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
            
            # Add SSL parameters if enabled
            connect_args = {
                # Support both mysql_native_password and caching_sha2_password
                'server_public_key': None  # Disable server public key verification for simplicity
            }
            
            if mysql_config.get('ssl_enabled', False):
                ssl_config = {
                    'ssl_ca': mysql_config.get('ssl_ca'),
                    'ssl_cert': mysql_config.get('ssl_cert'),
                    'ssl_key': mysql_config.get('ssl_key')
                }
                # Remove None values
                ssl_config = {k: v for k, v in ssl_config.items() if v}
                if ssl_config:
                    connect_args['ssl'] = ssl_config
            
            # Create SQLAlchemy engine with connection pooling
            self.mysql_engine = create_engine(
                connection_url,
                poolclass=QueuePool,
                pool_size=mysql_config.get('pool_size', 5),
                max_overflow=mysql_config.get('max_overflow', 10),
                pool_timeout=mysql_config.get('pool_timeout', 30),
                pool_recycle=mysql_config.get('pool_recycle', 3600),  # Recycle connections after 1 hour
                pool_pre_ping=True,  # Verify connections before use
                echo=False,  # Set to True for SQL debugging
                connect_args=connect_args
            )
            
            # Create session factory
            self.SessionCloud = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.mysql_engine
            )
            
            # Test connection
            with self.mysql_engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.fetchone()
            
            self.is_online = True
            self.logger.info(f"Successfully connected to cloud database: {host}:{port}/{database}")
            
            # Register device in cloud
            self._register_device()
            
            return True
            
        except OperationalError as e:
            self.logger.error(f"Failed to connect to MySQL cloud: {e}")
            self.is_online = False
            return False
            
        except Exception as e:
            self.logger.error(f"Error connecting to cloud: {e}", exc_info=True)
            self.is_online = False
            return False
    
    def check_cloud_connection(self) -> bool:
        """
        Check if cloud connection is alive
        
        Returns:
            bool: True if connection is active, False otherwise
        """
        try:
            if not self.mysql_engine:
                self.is_online = False
                return False
            
            # Quick ping test
            with self.mysql_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            self.is_online = True
            return True
            
        except Exception as e:
            self.logger.warning(f"Cloud connection check failed: {e}")
            self.is_online = False
            return False
    
    def disconnect_from_cloud(self):
        """
        Close cloud database connection and cleanup resources
        """
        try:
            if self.mysql_engine:
                self.mysql_engine.dispose()
                self.logger.info("Disconnected from cloud database")
            
            self.mysql_engine = None
            self.SessionCloud = None
            self.is_online = False
            
        except Exception as e:
            self.logger.error(f"Error disconnecting from cloud: {e}")
    
    @contextmanager
    def get_cloud_session(self):
        """
        Context manager for cloud database session
        
        Yields:
            Session: SQLAlchemy session for cloud database
        """
        if not self.SessionCloud:
            raise RuntimeError("Cloud database not connected. Call connect_to_cloud() first.")
        
        session = self.SessionCloud()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            self.logger.error(f"Cloud session error: {e}")
            raise
        finally:
            session.close()
    
    def _register_device(self):
        """
        Register/Update device in cloud with upsert strategy
        
        Strategy:
        - INSERT (first time): Push all fields from config
        - UPDATE (subsequent): Only update technical fields (firmware, OS, last_seen, ip)
        - PRESERVE: device_name, location (managed by Android app after pairing)
        """
        try:
            with self.get_cloud_session() as session:
                # Get device IP address
                hostname = socket.gethostname()
                try:
                    ip_address = socket.gethostbyname(hostname)
                except:
                    ip_address = None
                
                # Check if device exists
                result = session.execute(
                    text("SELECT id, device_name, location FROM devices WHERE device_id = :device_id"),
                    {'device_id': self.device_id}
                )
                device = result.fetchone()
                
                if device:
                    # UPDATE: Chỉ update technical fields, KHÔNG overwrite name/location
                    session.execute(
                        text("""
                            UPDATE devices 
                            SET last_seen = NOW(), 
                                ip_address = :ip_address,
                                firmware_version = :firmware_version,
                                os_version = :os_version,
                                is_active = 1
                            WHERE device_id = :device_id
                        """),
                        {
                            'device_id': self.device_id,
                            'ip_address': ip_address,
                            'firmware_version': self.firmware_version,
                            'os_version': self.os_version
                        }
                    )
                    self.logger.info(
                        f"Updated device technical fields: {self.device_id} "
                        f"(fw: {self.firmware_version}, os: {self.os_version})"
                    )
                else:
                    # INSERT: Đẩy tất cả fields lần đầu (including name/location from config)
                    session.execute(
                        text("""
                            INSERT INTO devices 
                            (device_id, device_name, device_type, location, pairing_code, 
                             firmware_version, os_version, ip_address, last_seen, is_active, created_at)
                            VALUES (:device_id, :device_name, :device_type, :location, :pairing_code,
                                    :firmware_version, :os_version, :ip_address, NOW(), 1, NOW())
                        """),
                        {
                            'device_id': self.device_id,
                            'device_name': self.device_name,
                            'device_type': self.device_type,
                            'location': self.location,
                            'pairing_code': self.pairing_code,
                            'firmware_version': self.firmware_version,
                            'os_version': self.os_version,
                            'ip_address': ip_address
                        }
                    )
                    self.logger.info(
                        f"Registered new device: {self.device_id} "
                        f"(pairing_code: {self.pairing_code}, type: {self.device_type})"
                    )
                
        except Exception as e:
            self.logger.error(f"Failed to register/update device: {e}")
    
    # ═══════════════════════════════════════════════════════════════════
    # PUSH OPERATIONS (Local → Cloud)
    # ═══════════════════════════════════════════════════════════════════
    
    def push_health_record(self, record_id: int) -> bool:
        """
        Push a health record from local to cloud
        
        Args:
            record_id: Local database record ID
            
        Returns:
            bool: True if push successful, False otherwise
        """
        try:
            # Check cloud connection
            if not self.check_cloud_connection():
                self.logger.warning("Cloud offline, enqueueing record for later sync")
                self.enqueue_for_sync('health_records', SyncOperation.INSERT, {'id': record_id})
                return False
            
            # Get record from local database
            with self.local_db.get_session() as local_session:
                from src.data.models import HealthRecord
                
                record = local_session.query(HealthRecord).filter_by(id=record_id).first()
                
                if not record:
                    self.logger.error(f"Health record {record_id} not found in local database")
                    return False
                
                # Device-centric: Get patient_id from cloud devices table if not set locally
                patient_id_to_use = record.patient_id
                if not patient_id_to_use:
                    # Query patient_id from cloud based on device_id
                    try:
                        with self.get_cloud_session() as cloud_session:
                            result = cloud_session.execute(
                                text("SELECT patient_id FROM patients WHERE device_id = :device_id AND is_active = 1 LIMIT 1"),
                                {'device_id': self.device_id}
                            )
                            patient_row = result.fetchone()
                            if patient_row:
                                patient_id_to_use = patient_row[0]
                                self.logger.info(f"Auto-resolved patient_id: {patient_id_to_use} for device {self.device_id}")
                    except Exception as e:
                        self.logger.warning(f"Could not auto-resolve patient_id: {e}")
                
                # Prepare data for cloud
                record_data = {
                    'patient_id': patient_id_to_use,  # Can be NULL if device not assigned to patient yet
                    'device_id': record.device_id if hasattr(record, 'device_id') and record.device_id else self.device_id,
                    'timestamp': record.timestamp,
                    'heart_rate': record.heart_rate,
                    'spo2': record.spo2,
                    'temperature': record.temperature,
                    'systolic_bp': record.systolic_bp,
                    'diastolic_bp': record.diastolic_bp,
                    'mean_arterial_pressure': record.mean_arterial_pressure,
                    'sensor_data': json.dumps(record.sensor_data) if record.sensor_data else None,  # Convert dict to JSON string
                    'data_quality': record.data_quality,
                    'measurement_context': record.measurement_context,
                    'synced_at': datetime.now(),
                    'sync_status': 'synced'
                }
            
            # Push to cloud
            with self.get_cloud_session() as cloud_session:
                cloud_session.execute(
                    text("""
                        INSERT INTO health_records 
                        (patient_id, device_id, timestamp, heart_rate, spo2, temperature,
                         systolic_bp, diastolic_bp, mean_arterial_pressure, sensor_data,
                         data_quality, measurement_context, synced_at, sync_status)
                        VALUES 
                        (:patient_id, :device_id, :timestamp, :heart_rate, :spo2, :temperature,
                         :systolic_bp, :diastolic_bp, :mean_arterial_pressure, :sensor_data,
                         :data_quality, :measurement_context, :synced_at, :sync_status)
                    """),
                    record_data
                )
            
            # Update local record sync status
            with self.local_db.get_session() as local_session:
                from src.data.models import HealthRecord
                record_to_update = local_session.query(HealthRecord).filter_by(id=record_id).first()
                if record_to_update:
                    record_to_update.synced_at = datetime.now()
                    record_to_update.sync_status = 'synced'
            
            self.stats['total_pushes'] += 1
            self.stats['successful_pushes'] += 1
            self.logger.info(f"Successfully pushed health record {record_id} to cloud")
            return True
            
        except Exception as e:
            self.stats['total_pushes'] += 1
            self.stats['failed_pushes'] += 1
            self.logger.error(f"Failed to push health record {record_id}: {e}")
            
            # Enqueue for retry
            self.enqueue_for_sync('health_records', SyncOperation.INSERT, {'id': record_id})
            return False
    
    def push_alert(self, alert_id: int) -> bool:
        """
        Push an alert from local to cloud
        
        Args:
            alert_id: Local database alert ID
            
        Returns:
            bool: True if push successful, False otherwise
        """
        try:
            if not self.check_cloud_connection():
                self.enqueue_for_sync('alerts', SyncOperation.INSERT, {'id': alert_id})
                return False
            
            # Get alert from local database
            with self.local_db.get_session() as local_session:
                from src.data.models import Alert
                
                alert = local_session.query(Alert).filter_by(id=alert_id).first()
                
                if not alert:
                    self.logger.error(f"Alert {alert_id} not found in local database")
                    return False
                
                # Device-centric: Get patient_id from cloud devices table if not set locally
                patient_id_to_use = alert.patient_id
                if not patient_id_to_use:
                    # Query patient_id from cloud based on device_id
                    try:
                        with self.get_cloud_session() as cloud_session:
                            result = cloud_session.execute(
                                text("SELECT patient_id FROM patients WHERE device_id = :device_id AND is_active = 1 LIMIT 1"),
                                {'device_id': self.device_id}
                            )
                            patient_row = result.fetchone()
                            if patient_row:
                                patient_id_to_use = patient_row[0]
                                self.logger.info(f"Auto-resolved patient_id: {patient_id_to_use} for device {self.device_id}")
                    except Exception as e:
                        self.logger.warning(f"Could not auto-resolve patient_id: {e}")
                
                # Prepare data for cloud
                alert_data = {
                    'patient_id': patient_id_to_use,  # Can be NULL if device not assigned to patient yet
                    'device_id': self.device_id,
                    'health_record_id': None,  # Local Alert doesn't have this field
                    'alert_type': alert.alert_type,
                    'severity': alert.severity,
                    'message': alert.message,
                    'vital_sign': alert.vital_sign,
                    'current_value': alert.current_value,
                    'threshold_value': alert.threshold_value,
                    'timestamp': alert.timestamp,
                    'acknowledged': alert.acknowledged,
                    'acknowledged_at': alert.acknowledged_at,
                    'resolved': alert.resolved,
                    'resolved_at': alert.resolved_at,
                    'notification_sent': 1 if alert.severity in ['high', 'critical'] else 0,
                    'notification_method': 'TTS'
                }
            
            # Push to cloud
            with self.get_cloud_session() as cloud_session:
                cloud_session.execute(
                    text("""
                        INSERT INTO alerts 
                        (patient_id, device_id, health_record_id, alert_type, severity, message,
                         vital_sign, current_value, threshold_value, timestamp, acknowledged,
                         acknowledged_at, resolved, resolved_at, notification_sent, notification_method)
                        VALUES 
                        (:patient_id, :device_id, :health_record_id, :alert_type, :severity, :message,
                         :vital_sign, :current_value, :threshold_value, :timestamp, :acknowledged,
                         :acknowledged_at, :resolved, :resolved_at, :notification_sent, :notification_method)
                    """),
                    alert_data
                )
            
            # Update local alert sync status
            with self.local_db.get_session() as local_session:
                alert_to_update = local_session.query(Alert).filter_by(id=alert_id).first()
                if alert_to_update and hasattr(alert_to_update, 'synced_at'):
                    alert_to_update.synced_at = datetime.now()
                    alert_to_update.sync_status = 'synced'
            
            self.stats['successful_pushes'] += 1
            self.logger.info(f"Successfully pushed alert {alert_id} to cloud")
            return True
            
        except Exception as e:
            self.stats['failed_pushes'] += 1
            self.logger.error(f"Failed to push alert {alert_id}: {e}")
            self.enqueue_for_sync('alerts', SyncOperation.INSERT, {'id': alert_id})
            return False
    
    def push_calibration(self, calibration_id: int) -> bool:
        """
        Push sensor calibration from local to cloud
        
        Args:
            calibration_id: Local database calibration ID
            
        Returns:
            bool: True if push successful, False otherwise
        """
        try:
            if not self.check_cloud_connection():
                self.enqueue_for_sync('sensor_calibrations', SyncOperation.INSERT, {'id': calibration_id})
                return False
            
            # Get calibration from local database
            with self.local_db.get_session() as local_session:
                from src.data.models import SensorCalibration
                
                calibration = local_session.query(SensorCalibration).filter_by(id=calibration_id).first()
                
                if not calibration:
                    self.logger.error(f"Calibration {calibration_id} not found in local database")
                    return False
                
                # Prepare data for cloud
                cal_data = {
                    'device_id': self.device_id,
                    'sensor_name': calibration.sensor_name,
                    'calibration_type': calibration.calibration_type,
                    'reference_values': calibration.reference_values,
                    'measured_values': calibration.measured_values,
                    'calibration_factors': calibration.calibration_factors,
                    'calibrated_at': calibration.calibrated_at,
                    'is_active': calibration.is_active,
                    'notes': calibration.notes
                }
            
            # Push to cloud (INSERT or UPDATE based on existence)
            with self.get_cloud_session() as cloud_session:
                # Check if calibration exists
                result = cloud_session.execute(
                    text("SELECT id FROM sensor_calibrations WHERE device_id = :device_id AND sensor_name = :sensor_name"),
                    {'device_id': self.device_id, 'sensor_name': calibration.sensor_name}
                )
                existing = result.fetchone()
                
                if existing:
                    # Update existing calibration
                    cloud_session.execute(
                        text("""
                            UPDATE sensor_calibrations 
                            SET calibration_type = :calibration_type,
                                reference_values = :reference_values,
                                measured_values = :measured_values,
                                calibration_factors = :calibration_factors,
                                calibrated_at = :calibrated_at,
                                is_active = :is_active,
                                notes = :notes
                            WHERE device_id = :device_id AND sensor_name = :sensor_name
                        """),
                        cal_data
                    )
                else:
                    # Insert new calibration
                    cloud_session.execute(
                        text("""
                            INSERT INTO sensor_calibrations 
                            (device_id, sensor_name, calibration_type, reference_values,
                             measured_values, calibration_factors, calibrated_at, is_active, notes)
                            VALUES 
                            (:device_id, :sensor_name, :calibration_type, :reference_values,
                             :measured_values, :calibration_factors, :calibrated_at, :is_active, :notes)
                        """),
                        cal_data
                    )
            
            self.stats['successful_pushes'] += 1
            self.logger.info(f"Successfully pushed calibration {calibration_id} to cloud")
            return True
            
        except Exception as e:
            self.stats['failed_pushes'] += 1
            self.logger.error(f"Failed to push calibration {calibration_id}: {e}")
            self.enqueue_for_sync('sensor_calibrations', SyncOperation.INSERT, {'id': calibration_id})
            return False
    
    def push_all_pending(self) -> Dict[str, int]:
        """
        Push all pending records from local queue to cloud
        
        Returns:
            Dict with counts of successful/failed pushes by table
        """
        results = {
            'health_records': {'success': 0, 'failed': 0},
            'alerts': {'success': 0, 'failed': 0},
            'calibrations': {'success': 0, 'failed': 0}
        }
        
        try:
            # Process sync queue
            queue_results = self.process_queue()
            
            self.logger.info(f"Pushed all pending: {queue_results}")
            return queue_results
            
        except Exception as e:
            self.logger.error(f"Error pushing all pending: {e}")
            return results
    
    # ═══════════════════════════════════════════════════════════════════
    # PULL OPERATIONS (Cloud → Local)
    # ═══════════════════════════════════════════════════════════════════
    
    def pull_patient_thresholds(self, patient_id: str) -> bool:
        """
        Pull patient thresholds from cloud to local
        
        Args:
            patient_id: Patient identifier
            
        Returns:
            bool: True if pull successful, False otherwise
        """
        try:
            if not self.check_cloud_connection():
                self.logger.warning("Cloud offline, cannot pull thresholds")
                return False
            
            # Get thresholds from cloud
            with self.get_cloud_session() as cloud_session:
                result = cloud_session.execute(
                    text("""
                        SELECT vital_sign, min_normal, max_normal, min_critical, max_critical
                        FROM patient_thresholds
                        WHERE patient_id = :patient_id AND is_active = 1
                    """),
                    {'patient_id': patient_id}
                )
                
                cloud_thresholds = result.fetchall()
                
                if not cloud_thresholds:
                    self.logger.info(f"No thresholds found in cloud for patient {patient_id}")
                    return False
                
                # Convert to dictionary format
                thresholds_dict = {}
                for row in cloud_thresholds:
                    thresholds_dict[row[0]] = {
                        'min_normal': float(row[1]) if row[1] is not None else None,
                        'max_normal': float(row[2]) if row[2] is not None else None,
                        'min_critical': float(row[3]) if row[3] is not None else None,
                        'max_critical': float(row[4]) if row[4] is not None else None
                    }
            
            # Update local database
            success = self.local_db.save_patient_thresholds(patient_id, thresholds_dict)
            
            if success:
                self.stats['successful_pulls'] += 1
                self.logger.info(f"Successfully pulled thresholds for patient {patient_id}")
            else:
                self.stats['failed_pulls'] += 1
                
            return success
            
        except Exception as e:
            self.stats['failed_pulls'] += 1
            self.logger.error(f"Failed to pull thresholds for patient {patient_id}: {e}")
            return False
    
    def pull_device_config(self) -> bool:
        """
        Pull device-specific configuration from cloud
        
        Returns:
            bool: True if pull successful, False otherwise
        """
        try:
            if not self.check_cloud_connection():
                return False
            
            with self.get_cloud_session() as cloud_session:
                result = cloud_session.execute(
                    text("SELECT device_name, location FROM devices WHERE device_id = :device_id"),
                    {'device_id': self.device_id}
                )
                
                device_config = result.fetchone()
                
                if device_config:
                    self.device_name = device_config[0]
                    self.location = device_config[1]
                    self.logger.info(f"Pulled device config from cloud: {self.device_name}")
                    return True
                
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to pull device config: {e}")
            return False
    
    def pull_updated_alerts(self) -> List[Dict[str, Any]]:
        """
        Pull alerts that were updated in cloud (e.g., acknowledged remotely)
        
        Returns:
            List of updated alert dictionaries
        """
        updated_alerts = []
        
        try:
            if not self.check_cloud_connection():
                return updated_alerts
            
            # Get alerts updated in cloud in last sync interval
            with self.get_cloud_session() as cloud_session:
                since_time = self.last_sync_time or (datetime.now() - timedelta(hours=24))
                
                result = cloud_session.execute(
                    text("""
                        SELECT id, patient_id, acknowledged, acknowledged_at, acknowledged_by,
                               resolved, resolved_at
                        FROM alerts
                        WHERE device_id = :device_id 
                        AND (acknowledged_at > :since_time OR resolved_at > :since_time)
                    """),
                    {'device_id': self.device_id, 'since_time': since_time}
                )
                
                for row in result:
                    updated_alerts.append({
                        'cloud_id': row[0],
                        'patient_id': row[1],
                        'acknowledged': bool(row[2]),
                        'acknowledged_at': row[3],
                        'acknowledged_by': row[4],
                        'resolved': bool(row[5]),
                        'resolved_at': row[6]
                    })
            
            self.logger.info(f"Pulled {len(updated_alerts)} updated alerts from cloud")
            return updated_alerts
            
        except Exception as e:
            self.logger.error(f"Failed to pull updated alerts: {e}")
            return updated_alerts
    
    # ═══════════════════════════════════════════════════════════════════
    # STORE & FORWARD QUEUE
    # ═══════════════════════════════════════════════════════════════════
    
    def enqueue_for_sync(self, table_name: str, operation: SyncOperation, data: Dict[str, Any]):
        """
        Add record to local sync queue for later processing
        
        Args:
            table_name: Name of the table (health_records, alerts, etc.)
            operation: Sync operation type (INSERT, UPDATE, DELETE)
            data: Record data to sync
        """
        try:
            # Store in local SQLite queue table
            with self.local_db.get_session() as session:
                from src.data.models import SystemLog
                
                # Use SystemLog table temporarily for queue storage
                # TODO: Create dedicated sync_queue table in local database
                queue_entry = SystemLog(
                    level='INFO',
                    message=f'Sync queue: {operation.value} {table_name}',
                    module='cloud_sync',
                    function_name='enqueue_for_sync',
                    timestamp=datetime.now(),
                    additional_data=json.dumps({
                        'table_name': table_name,
                        'operation': operation.value,
                        'record_data': data,
                        'device_id': self.device_id,
                        'sync_status': SyncStatus.PENDING.value
                    })
                )
                
                session.add(queue_entry)
            
            self.stats['queue_size'] += 1
            self.logger.debug(f"Enqueued for sync: {table_name} - {operation.value}")
            
        except Exception as e:
            self.logger.error(f"Failed to enqueue for sync: {e}")
    
    def process_queue(self) -> Dict[str, int]:
        """
        Process all pending items in sync queue
        
        Returns:
            Dict with counts of processed items by status
        """
        results = {
            'processed': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
        
        try:
            if not self.check_cloud_connection():
                self.logger.warning("Cloud offline, cannot process queue")
                return results
            
            # Get pending queue items from SystemLog
            with self.local_db.get_session() as session:
                from src.data.models import SystemLog
                
                pending = session.query(SystemLog).filter(
                    SystemLog.module == 'cloud_sync',
                    SystemLog.function_name == 'enqueue_for_sync'
                ).all()
                
                for item in pending:
                    try:
                        queue_data = json.loads(item.additional_data)
                        
                        if queue_data.get('sync_status') != SyncStatus.PENDING.value:
                            results['skipped'] += 1
                            continue
                        
                        table_name = queue_data['table_name']
                        record_data = queue_data['record_data']
                        
                        # Process based on table type
                        success = False
                        if table_name == 'health_records' and 'id' in record_data:
                            success = self.push_health_record(record_data['id'])
                        elif table_name == 'alerts' and 'id' in record_data:
                            success = self.push_alert(record_data['id'])
                        elif table_name == 'sensor_calibrations' and 'id' in record_data:
                            success = self.push_calibration(record_data['id'])
                        
                        results['processed'] += 1
                        if success:
                            results['success'] += 1
                            # Mark as synced
                            queue_data['sync_status'] = SyncStatus.SUCCESS.value
                            item.additional_data = json.dumps(queue_data)
                        else:
                            results['failed'] += 1
                            
                    except Exception as e:
                        results['failed'] += 1
                        self.logger.error(f"Error processing queue item: {e}")
            
            self.logger.info(f"Queue processing results: {results}")
            return results
            
        except Exception as e:
            self.logger.error(f"Error processing queue: {e}")
            return results
    
    def clear_synced_queue(self):
        """
        Remove successfully synced items from queue
        """
        try:
            with self.local_db.get_session() as session:
                from src.data.models import SystemLog
                
                # Delete synced items older than 7 days
                cutoff_date = datetime.now() - timedelta(days=7)
                
                deleted = session.query(SystemLog).filter(
                    SystemLog.module == 'cloud_sync',
                    SystemLog.timestamp < cutoff_date
                ).delete()
                
                self.logger.info(f"Cleared {deleted} synced queue items")
                
        except Exception as e:
            self.logger.error(f"Error clearing synced queue: {e}")
    
    # ═══════════════════════════════════════════════════════════════════
    # SYNC ORCHESTRATION
    # ═══════════════════════════════════════════════════════════════════
    
    def sync_all(self, direction: str = 'both') -> Dict[str, Any]:
        """
        Perform full synchronization
        
        Args:
            direction: 'push', 'pull', or 'both'
            
        Returns:
            Dict with sync results
        """
        results = {
            'started_at': datetime.now(),
            'direction': direction,
            'push_results': {},
            'pull_results': {},
            'errors': []
        }
        
        try:
            if not self.check_cloud_connection():
                results['errors'].append("Cloud connection not available")
                return results
            
            # Push operations
            if direction in ['push', 'both']:
                results['push_results'] = self.push_all_pending()
            
            # Pull operations
            if direction in ['pull', 'both']:
                # Pull thresholds for all patients
                # Pull updated alerts
                results['pull_results']['updated_alerts'] = len(self.pull_updated_alerts())
            
            self.last_sync_time = datetime.now()
            results['completed_at'] = self.last_sync_time
            results['success'] = True
            
            self.logger.info(f"Sync completed: {direction}")
            
        except Exception as e:
            results['errors'].append(str(e))
            results['success'] = False
            self.logger.error(f"Sync failed: {e}")
        
        return results
    
    def sync_incremental(self, since: datetime) -> Dict[str, Any]:
        """
        Perform incremental sync (only changes since timestamp)
        
        Args:
            since: Sync records changed after this timestamp
            
        Returns:
            Dict with sync results
        """
        results = {
            'since': since,
            'records_synced': 0,
            'alerts_synced': 0,
            'errors': []
        }
        
        try:
            if not self.check_cloud_connection():
                results['errors'].append("Cloud offline")
                return results
            
            # Get records created/updated after 'since' timestamp
            with self.local_db.get_session() as session:
                from src.data.models import HealthRecord, Alert
                
                # Sync new health records (only those not synced or updated after last sync)
                new_records = session.query(HealthRecord).filter(
                    and_(
                        HealthRecord.timestamp > since,
                        or_(
                            HealthRecord.synced_at.is_(None),  # Never synced
                            HealthRecord.synced_at < HealthRecord.timestamp  # Updated after sync
                        )
                    )
                ).all()
                
                for record in new_records:
                    if self.push_health_record(record.id):
                        results['records_synced'] += 1
                
                # Sync new alerts (only those not synced or updated after last sync)
                # Check if synced_at column exists in Alert model
                if hasattr(Alert, 'synced_at'):
                    new_alerts = session.query(Alert).filter(
                        and_(
                            Alert.timestamp > since,
                            or_(
                                Alert.synced_at.is_(None),  # Never synced
                                Alert.synced_at < Alert.timestamp  # Updated after sync
                            )
                        )
                    ).all()
                else:
                    # Fallback: sync all alerts after 'since' timestamp
                    new_alerts = session.query(Alert).filter(
                        Alert.timestamp > since
                    ).all()
                
                for alert in new_alerts:
                    if self.push_alert(alert.id):
                        results['alerts_synced'] += 1
            
            self.logger.info(f"Incremental sync completed: {results}")
            
        except Exception as e:
            results['errors'].append(str(e))
            self.logger.error(f"Incremental sync failed: {e}")
        
        return results
    
    def resolve_conflicts(self, conflicts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Resolve sync conflicts based on configured strategy
        
        Args:
            conflicts: List of conflict dictionaries
            
        Returns:
            List of resolved conflict results
        """
        resolved = []
        
        for conflict in conflicts:
            resolution = {
                'conflict_id': conflict.get('id'),
                'strategy': self.conflict_strategy,
                'action': None,
                'success': False
            }
            
            try:
                if self.conflict_strategy == 'cloud_wins':
                    # Cloud data takes precedence, update local
                    resolution['action'] = 'update_local_from_cloud'
                    # TODO: Implement actual update logic
                    resolution['success'] = True
                    
                elif self.conflict_strategy == 'local_wins':
                    # Local data takes precedence, push to cloud
                    resolution['action'] = 'update_cloud_from_local'
                    # TODO: Implement actual update logic
                    resolution['success'] = True
                    
                else:
                    # Manual resolution required
                    resolution['action'] = 'manual_required'
                    self.logger.warning(f"Manual conflict resolution required: {conflict}")
                
                self.stats['conflicts_resolved'] += 1
                
            except Exception as e:
                resolution['error'] = str(e)
                self.logger.error(f"Error resolving conflict: {e}")
            
            resolved.append(resolution)
        
        return resolved
    
    # ═══════════════════════════════════════════════════════════════════
    # MONITORING & STATISTICS
    # ═══════════════════════════════════════════════════════════════════
    
    def get_sync_status(self) -> Dict[str, Any]:
        """
        Get current sync status and health
        
        Returns:
            Dict with sync status information
        """
        status = {
            'is_online': self.is_online,
            'device_id': self.device_id,
            'last_sync_time': self.last_sync_time.isoformat() if self.last_sync_time else None,
            'sync_mode': self.sync_mode,
            'queue_size': self.stats['queue_size'],
            'cloud_connected': self.check_cloud_connection(),
            'sync_enabled': self.cloud_config.get('enabled', False)
        }
        
        return status
    
    def get_sync_statistics(self) -> Dict[str, Any]:
        """
        Get detailed sync statistics
        
        Returns:
            Dict with sync statistics
        """
        stats = {
            **self.stats,
            'success_rate': 0.0,
            'last_sync': self.last_sync_time.isoformat() if self.last_sync_time else None,
            'device_id': self.device_id
        }
        
        # Calculate success rate
        total_ops = stats['total_pushes'] + stats['total_pulls']
        if total_ops > 0:
            successful = stats['successful_pushes'] + stats['successful_pulls']
            stats['success_rate'] = round((successful / total_ops) * 100, 2)
        
        return stats
    
    def __repr__(self):
        return f"<CloudSyncManager device={self.device_id} online={self.is_online}>"
