#!/usr/bin/env python3
"""
Database Testing Script
Kiểm tra đầy đủ DatabaseManager implementation
"""

import sys
import os
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime, timedelta
import json

from src.data.database import DatabaseManager
from src.utils.logger import setup_logger


def test_database_initialization():
    """Test 1: Database initialization"""
    print("\n" + "="*60)
    print("TEST 1: Database Initialization")
    print("="*60)
    
    config = {
        'database': {
            'path': 'data/test_health_monitor.db'
        }
    }
    
    db = DatabaseManager(config)
    
    # Initialize
    success = db.initialize()
    print(f"✓ Database initialized: {success}")
    
    # Get info
    info = db.get_database_info()
    print(f"✓ Database info: {json.dumps(info, indent=2)}")
    
    return db


def test_patient_operations(db: DatabaseManager):
    """Test 2: Patient CRUD operations"""
    print("\n" + "="*60)
    print("TEST 2: Patient CRUD Operations")
    print("="*60)
    
    # Create patient
    patient_data = {
        'patient_id': 'P12345',
        'name': 'Nguyễn Văn A',
        'age': 65,
        'gender': 'M',
        'medical_conditions': ['Hypertension', 'Diabetes'],
        'emergency_contact': {
            'name': 'Nguyễn Thị B',
            'phone': '0901234567',
            'relationship': 'Vợ'
        }
    }
    
    patient_id = db.create_patient(patient_data)
    print(f"✓ Created patient: {patient_id}")
    
    # Get patient
    patient = db.get_patient(patient_id)
    print(f"✓ Retrieved patient: {patient['name']}, Age: {patient['age']}")
    
    # Update patient
    success = db.update_patient(patient_id, {'age': 66})
    print(f"✓ Updated patient age: {success}")
    
    # Get thresholds
    thresholds = db.get_patient_thresholds(patient_id)
    print(f"✓ Default thresholds created: {len(thresholds)} vital signs")
    for vital, values in thresholds.items():
        print(f"  - {vital}: {values['min_normal']}-{values['max_normal']}")
    
    return patient_id


def test_health_records(db: DatabaseManager, patient_id: str):
    """Test 3: Health records operations"""
    print("\n" + "="*60)
    print("TEST 3: Health Records Operations")
    print("="*60)
    
    # Save multiple health records
    base_time = datetime.utcnow()
    
    records_data = [
        {
            'patient_id': patient_id,
            'device_id': 'rpi_bp_001',  # REQUIRED after migration
            'timestamp': base_time - timedelta(hours=3),
            'heart_rate': 72.0,
            'spo2': 98.0,
            'temperature': 36.5,
            'systolic_bp': 120.0,
            'diastolic_bp': 80.0,
            'mean_arterial_pressure': 93.3,
            'data_quality': 0.95,
            'measurement_context': 'rest'
        },
        {
            'patient_id': patient_id,
            'device_id': 'rpi_bp_001',  # REQUIRED after migration
            'timestamp': base_time - timedelta(hours=2),
            'heart_rate': 85.0,
            'spo2': 97.0,
            'temperature': 36.7,
            'systolic_bp': 130.0,
            'diastolic_bp': 85.0,
            'mean_arterial_pressure': 100.0,
            'data_quality': 0.92,
            'measurement_context': 'activity'
        },
        {
            'patient_id': patient_id,
            'device_id': 'rpi_bp_001',  # REQUIRED after migration
            'timestamp': base_time - timedelta(hours=1),
            'heart_rate': 75.0,
            'spo2': 99.0,
            'temperature': 36.6,
            'systolic_bp': 125.0,
            'diastolic_bp': 82.0,
            'mean_arterial_pressure': 96.3,
            'data_quality': 0.98,
            'measurement_context': 'rest'
        }
    ]
    
    record_ids = []
    for data in records_data:
        record_id = db.save_health_record(data)
        record_ids.append(record_id)
    
    print(f"✓ Saved {len(record_ids)} health records")
    
    # Get latest vitals
    latest = db.get_latest_vitals(patient_id)
    print(f"✓ Latest vitals: HR={latest['heart_rate']}, SpO2={latest['spo2']}, Temp={latest['temperature']}")
    
    # Get all records
    all_records = db.get_health_records(patient_id)
    print(f"✓ Retrieved {len(all_records)} health records")
    
    # Get statistics
    stats = db.get_health_statistics(patient_id, '24h')
    print(f"✓ Statistics (24h):")
    print(f"  - Record count: {stats['record_count']}")
    if 'heart_rate' in stats:
        print(f"  - HR avg: {stats['heart_rate']['avg']}, range: {stats['heart_rate']['min']}-{stats['heart_rate']['max']}")
    if 'systolic_bp' in stats:
        print(f"  - BP avg: {stats['systolic_bp']['avg']}/{stats['diastolic_bp']['avg']}")


def test_alerts(db: DatabaseManager, patient_id: str):
    """Test 4: Alert operations"""
    print("\n" + "="*60)
    print("TEST 4: Alert Operations")
    print("="*60)
    
    # Create alerts
    alerts_data = [
        {
            'patient_id': patient_id,
            'device_id': 'rpi_bp_001',  # REQUIRED after migration
            'alert_type': 'threshold',
            'severity': 'high',
            'message': 'Huyết áp cao: 145/95 mmHg',
            'vital_sign': 'blood_pressure',
            'current_value': 145.0,
            'threshold_value': 140.0
        },
        {
            'patient_id': patient_id,
            'device_id': 'rpi_bp_001',  # REQUIRED after migration
            'alert_type': 'threshold',
            'severity': 'medium',
            'message': 'SpO2 thấp: 93%',
            'vital_sign': 'spo2',
            'current_value': 93.0,
            'threshold_value': 95.0
        }
    ]
    
    alert_ids = []
    for data in alerts_data:
        alert_id = db.save_alert(data)
        alert_ids.append(alert_id)
    
    print(f"✓ Created {len(alert_ids)} alerts")
    
    # Get active alerts
    active = db.get_active_alerts(patient_id)
    print(f"✓ Active alerts: {len(active)}")
    for alert in active:
        print(f"  - [{alert['severity']}] {alert['message']}")
    
    # Acknowledge first alert
    success = db.acknowledge_alert(alert_ids[0])
    print(f"✓ Acknowledged alert {alert_ids[0]}: {success}")
    
    # Resolve second alert
    success = db.resolve_alert(alert_ids[1])
    print(f"✓ Resolved alert {alert_ids[1]}: {success}")
    
    # Check active alerts again
    active = db.get_active_alerts(patient_id)
    print(f"✓ Active alerts after resolution: {len(active)}")


def test_sensor_calibration(db: DatabaseManager):
    """Test 5: Sensor calibration operations"""
    print("\n" + "="*60)
    print("TEST 5: Sensor Calibration Operations")
    print("="*60)
    
    # Save HX710B calibration
    calibration_data = {
        'device_id': 'rpi_bp_001',  # REQUIRED after migration
        'sensor_name': 'HX710B',
        'calibration_type': 'two_point',
        'reference_values': [0.0, 200.0],  # mmHg
        'measured_values': [1300885, 7900123],  # ADC counts
        'calibration_factors': {
            'offset_counts': 1300885,
            'slope_mmhg_per_count': 3.5765e-05
        },
        'notes': 'Calibrated with MPS20N0040D-S sensor'
    }
    
    cal_id = db.save_sensor_calibration(calibration_data)
    print(f"✓ Saved HX710B calibration: ID={cal_id}")
    
    # Get calibration
    cal = db.get_sensor_calibration('HX710B')
    print(f"✓ Retrieved calibration:")
    print(f"  - Type: {cal['calibration_type']}")
    print(f"  - Offset: {cal['calibration_factors']['offset_counts']}")
    print(f"  - Slope: {cal['calibration_factors']['slope_mmhg_per_count']}")
    
    # Update calibration (new calibration deactivates old one)
    new_calibration_data = {
        'device_id': 'rpi_bp_001',  # REQUIRED after migration
        'sensor_name': 'HX710B',
        'calibration_type': 'two_point',
        'reference_values': [0.0, 200.0],
        'measured_values': [1303339, 7910456],
        'calibration_factors': {
            'offset_counts': 1303339,
            'slope_mmhg_per_count': 3.5800e-05
        },
        'notes': 'Recalibrated after drift'
    }
    
    new_cal_id = db.save_sensor_calibration(new_calibration_data)
    print(f"✓ Saved new calibration: ID={new_cal_id} (old one deactivated)")


def test_backup_restore(db: DatabaseManager):
    """Test 6: Backup and restore"""
    print("\n" + "="*60)
    print("TEST 6: Backup & Restore Operations")
    print("="*60)
    
    backup_path = 'data/test_backup.db'
    
    # Backup
    success = db.backup_database(backup_path)
    print(f"✓ Database backed up: {success}")
    
    # Check backup file
    if os.path.exists(backup_path):
        size_mb = os.path.getsize(backup_path) / (1024 * 1024)
        print(f"✓ Backup file size: {size_mb:.2f} MB")
    
    # Restore (for testing - comment out in production)
    # success = db.restore_database(backup_path)
    # print(f"✓ Database restored: {success}")


def test_system_logs(db: DatabaseManager):
    """Test 7: System logging"""
    print("\n" + "="*60)
    print("TEST 7: System Logging")
    print("="*60)
    
    # Log events
    db.log_system_event('INFO', 'System started', 'main', 'main')
    db.log_system_event('WARNING', 'High CPU usage', 'monitor', 'check_resources', {'cpu': 85.5})
    db.log_system_event('ERROR', 'Sensor read failed', 'sensors', 'read_max30102', {'error': 'I2C timeout'})
    
    print("✓ Logged 3 system events")
    
    # Get database info
    info = db.get_database_info()
    print(f"✓ System logs count: {info['tables']['system_logs']}")


def test_cleanup(db: DatabaseManager):
    """Test 8: Cleanup old records"""
    print("\n" + "="*60)
    print("TEST 8: Cleanup Operations")
    print("="*60)
    
    # This would delete records older than 90 days
    deleted = db.cleanup_old_records(days_to_keep=90)
    print(f"✓ Deleted {deleted} old records (>90 days)")


def run_all_tests():
    """Run all database tests"""
    print("\n" + "🧪 " + "="*58)
    print("   DATABASE IMPLEMENTATION TESTING")
    print("="*60 + "\n")
    
    # Setup logging
    logger = setup_logger()
    
    try:
        # Test 1: Initialization
        db = test_database_initialization()
        
        # Test 2: Patient operations
        patient_id = test_patient_operations(db)
        
        # Test 3: Health records
        test_health_records(db, patient_id)
        
        # Test 4: Alerts
        test_alerts(db, patient_id)
        
        # Test 5: Sensor calibration
        test_sensor_calibration(db)
        
        # Test 6: Backup/restore
        test_backup_restore(db)
        
        # Test 7: System logs
        test_system_logs(db)
        
        # Test 8: Cleanup
        test_cleanup(db)
        
        # Final summary
        print("\n" + "="*60)
        print("📊 FINAL DATABASE SUMMARY")
        print("="*60)
        
        info = db.get_database_info()
        print(f"Database: {info['db_path']}")
        print(f"Size: {info['db_size_mb']} MB")
        print(f"\nTable Counts:")
        for table, count in info['tables'].items():
            print(f"  - {table}: {count}")
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60 + "\n")
        
        # Close database
        db.close()
        
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
