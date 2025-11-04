#!/usr/bin/env python3
"""
Database Query Tool
Query và thống kê database
"""

import sys
import os
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import yaml
import json
from datetime import datetime, timedelta

from src.data.database import DatabaseManager
from src.utils.logger import setup_logger


def load_config():
    """Load application configuration"""
    config_path = project_root / 'config' / 'app_config.yaml'
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    return config


def show_database_info(db: DatabaseManager):
    """Show database information"""
    print("\n" + "="*70)
    print("DATABASE INFORMATION")
    print("="*70 + "\n")
    
    info = db.get_database_info()
    
    print(f"Path: {info['db_path']}")
    print(f"Size: {info['db_size_mb']} MB")
    print(f"\nTable Counts:")
    for table, count in info['tables'].items():
        print(f"  - {table}: {count}")


def show_patients(db: DatabaseManager):
    """Show all patients"""
    print("\n" + "="*70)
    print("PATIENTS")
    print("="*70 + "\n")
    
    # Get from database
    with db.get_session() as session:
        from src.data.models import Patient
        patients = session.query(Patient).all()
        
        if not patients:
            print("No patients found.")
            return
        
        for patient in patients:
            print(f"ID: {patient.patient_id}")
            print(f"Name: {patient.name}")
            print(f"Age: {patient.age}, Gender: {patient.gender}")
            print(f"Medical Conditions: {patient.medical_conditions}")
            print(f"Created: {patient.created_at.strftime('%Y-%m-%d %H:%M')}")
            print(f"Active: {patient.is_active}")
            
            # Get thresholds
            thresholds = db.get_patient_thresholds(patient.patient_id)
            print(f"Thresholds: {len(thresholds)} vital signs")
            
            # Get latest vitals
            latest = db.get_latest_vitals(patient.patient_id)
            if latest:
                print(f"Latest Reading: {latest['timestamp']}")
                print(f"  HR: {latest['heart_rate']}, SpO2: {latest['spo2']}, Temp: {latest['temperature']}")
                print(f"  BP: {latest['systolic_bp']}/{latest['diastolic_bp']}")
            
            print()


def show_health_records(db: DatabaseManager, patient_id: str, limit: int = 10):
    """Show health records for patient"""
    print("\n" + "="*70)
    print(f"HEALTH RECORDS - {patient_id} (latest {limit})")
    print("="*70 + "\n")
    
    records = db.get_health_records(patient_id, limit=limit)
    
    if not records:
        print("No health records found.")
        return
    
    print(f"{'Timestamp':<20} {'HR':<6} {'SpO2':<6} {'Temp':<6} {'BP':<12} {'Quality':<8} {'Context':<10}")
    print("-" * 70)
    
    for record in records:
        timestamp = record['timestamp'][:19] if record['timestamp'] else 'N/A'
        hr = f"{record['heart_rate']:.0f}" if record['heart_rate'] else 'N/A'
        spo2 = f"{record['spo2']:.0f}" if record['spo2'] else 'N/A'
        temp = f"{record['temperature']:.1f}" if record['temperature'] else 'N/A'
        
        if record['systolic_bp'] and record['diastolic_bp']:
            bp = f"{record['systolic_bp']:.0f}/{record['diastolic_bp']:.0f}"
        else:
            bp = 'N/A'
        
        quality = f"{record['data_quality']:.2f}" if record['data_quality'] else 'N/A'
        context = record['measurement_context'] or 'N/A'
        
        print(f"{timestamp:<20} {hr:<6} {spo2:<6} {temp:<6} {bp:<12} {quality:<8} {context:<10}")


def show_statistics(db: DatabaseManager, patient_id: str, time_range: str = '7d'):
    """Show statistics for patient"""
    print("\n" + "="*70)
    print(f"HEALTH STATISTICS - {patient_id} ({time_range})")
    print("="*70 + "\n")
    
    stats = db.get_health_statistics(patient_id, time_range)
    
    if not stats:
        print("No statistics available.")
        return
    
    print(f"Time Range: {stats['time_range']}")
    print(f"Start: {stats['start_time'][:19]}")
    print(f"End: {stats['end_time'][:19]}")
    print(f"Record Count: {stats['record_count']}\n")
    
    vitals = ['heart_rate', 'spo2', 'temperature', 'systolic_bp', 'diastolic_bp']
    
    for vital in vitals:
        if vital in stats:
            data = stats[vital]
            print(f"{vital.upper()}:")
            print(f"  Average: {data['avg']}")
            print(f"  Range: {data['min']} - {data['max']}")
            print(f"  Readings: {data['count']}\n")


def show_alerts(db: DatabaseManager, patient_id: str):
    """Show alerts for patient"""
    print("\n" + "="*70)
    print(f"ACTIVE ALERTS - {patient_id}")
    print("="*70 + "\n")
    
    alerts = db.get_active_alerts(patient_id)
    
    if not alerts:
        print("No active alerts.")
        return
    
    for alert in alerts:
        timestamp = alert['timestamp'][:19]
        status = 'Acknowledged' if alert['acknowledged'] else 'New'
        
        print(f"[{alert['severity'].upper()}] {alert['message']}")
        print(f"  Time: {timestamp}")
        print(f"  Type: {alert['alert_type']}, Status: {status}")
        
        if alert['vital_sign']:
            print(f"  Vital: {alert['vital_sign']}, Current: {alert['current_value']}, Threshold: {alert['threshold_value']}")
        
        print()


def show_calibrations(db: DatabaseManager):
    """Show sensor calibrations"""
    print("\n" + "="*70)
    print("SENSOR CALIBRATIONS")
    print("="*70 + "\n")
    
    # Get all calibrations
    with db.get_session() as session:
        from src.data.models import SensorCalibration
        calibrations = session.query(SensorCalibration).order_by(
            SensorCalibration.sensor_name, SensorCalibration.calibrated_at.desc()
        ).all()
        
        if not calibrations:
            print("No calibrations found.")
            return
        
        current_sensor = None
        for cal in calibrations:
            if cal.sensor_name != current_sensor:
                if current_sensor:
                    print()
                print(f"--- {cal.sensor_name} ---")
                current_sensor = cal.sensor_name
            
            status = "✓ ACTIVE" if cal.is_active else "  inactive"
            print(f"{status} [{cal.calibration_type}] Calibrated: {cal.calibrated_at.strftime('%Y-%m-%d %H:%M')}")
            
            if cal.calibration_factors:
                print(f"  Factors: {json.dumps(cal.calibration_factors, indent=2)}")
            
            if cal.notes:
                print(f"  Notes: {cal.notes}")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Database Query Tool')
    parser.add_argument('--patient', '-p', help='Patient ID')
    parser.add_argument('--info', '-i', action='store_true', help='Show database info')
    parser.add_argument('--patients', action='store_true', help='Show all patients')
    parser.add_argument('--records', '-r', action='store_true', help='Show health records')
    parser.add_argument('--stats', '-s', action='store_true', help='Show statistics')
    parser.add_argument('--alerts', '-a', action='store_true', help='Show alerts')
    parser.add_argument('--calibrations', '-c', action='store_true', help='Show calibrations')
    parser.add_argument('--limit', '-l', type=int, default=10, help='Limit for records')
    parser.add_argument('--range', default='7d', help='Time range for stats (24h, 7d, 30d)')
    
    args = parser.parse_args()
    
    try:
        # Setup logging
        logger = setup_logger()
        
        # Load config
        config = load_config()
        
        # Create database manager
        db = DatabaseManager(config)
        
        # Default patient
        patient_id = args.patient or config.get('patient', {}).get('id', 'patient_001')
        
        # Show info
        if args.info or not any([args.patients, args.records, args.stats, args.alerts, args.calibrations]):
            show_database_info(db)
        
        if args.patients:
            show_patients(db)
        
        if args.records:
            show_health_records(db, patient_id, args.limit)
        
        if args.stats:
            show_statistics(db, patient_id, args.range)
        
        if args.alerts:
            show_alerts(db, patient_id)
        
        if args.calibrations:
            show_calibrations(db)
        
        print()
        
        # Close database
        db.close()
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
