#!/usr/bin/env python3
"""
Database Initialization Script
Khởi tạo database cho production deployment
"""

import sys
import os
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import yaml
import logging
from datetime import datetime

from src.data.database import DatabaseManager
from src.utils.logger import setup_logger


def load_config():
    """Load application configuration"""
    config_path = project_root / 'config' / 'app_config.yaml'
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    return config


def init_database(config):
    """Initialize database and create default patient"""
    print("\n" + "="*60)
    print("DATABASE INITIALIZATION")
    print("="*60 + "\n")
    
    # Create database manager
    db = DatabaseManager(config)
    
    # Initialize database
    print("1. Creating database tables...")
    success = db.initialize()
    
    if not success:
        print("❌ Failed to initialize database")
        return False
    
    print("✅ Database tables created\n")
    
    # Get database info
    info = db.get_database_info()
    print(f"2. Database path: {info['db_path']}")
    print(f"   Database size: {info['db_size_mb']} MB\n")
    
    # Create default patient from config
    patient_config = config.get('patient', {})
    
    if patient_config.get('id'):
        print("3. Creating default patient...")
        
        # Check if patient already exists
        existing = db.get_patient(patient_config['id'])
        
        if existing:
            print(f"   ⚠️  Patient {patient_config['id']} already exists")
            print(f"   Name: {existing['name']}, Age: {existing['age']}")
        else:
            patient_data = {
                'patient_id': patient_config['id'],
                'name': patient_config.get('name', 'Default Patient'),
                'age': patient_config.get('age'),
                'gender': patient_config.get('gender'),
                'medical_conditions': [],
                'emergency_contact': {
                    'name': 'Emergency Contact',
                    'phone': '',
                    'relationship': ''
                }
            }
            
            patient_id = db.create_patient(patient_data)
            
            if patient_id:
                print(f"   ✅ Created patient: {patient_id}")
                print(f"   Name: {patient_data['name']}, Age: {patient_data['age']}")
                
                # Get thresholds
                thresholds = db.get_patient_thresholds(patient_id)
                print(f"   ✅ Created {len(thresholds)} default thresholds")
            else:
                print("   ❌ Failed to create patient")
    
    print()
    
    # Save initial sensor calibrations if available
    hx710b_config = config.get('sensors', {}).get('blood_pressure', {}).get('hx710b', {})
    calibration = hx710b_config.get('calibration', {})
    
    if calibration.get('offset_counts') and calibration.get('slope_mmhg_per_count'):
        print("4. Saving HX710B calibration...")
        
        calibration_data = {
            'sensor_name': 'HX710B',
            'calibration_type': 'two_point',
            'reference_values': [0.0, 200.0],
            'measured_values': [calibration['offset_counts'], 0],  # Only offset known
            'calibration_factors': {
                'offset_counts': calibration['offset_counts'],
                'slope_mmhg_per_count': calibration['slope_mmhg_per_count'],
                'adc_inverted': calibration.get('adc_inverted', False)
            },
            'notes': f"Initial calibration from config (loaded {datetime.now().strftime('%Y-%m-%d %H:%M')})"
        }
        
        cal_id = db.save_sensor_calibration(calibration_data)
        
        if cal_id:
            print(f"   ✅ Saved calibration ID={cal_id}")
            print(f"   Offset: {calibration['offset_counts']}")
            print(f"   Slope: {calibration['slope_mmhg_per_count']}")
        else:
            print("   ❌ Failed to save calibration")
    
    print()
    
    # Final summary
    info = db.get_database_info()
    print("="*60)
    print("INITIALIZATION COMPLETE")
    print("="*60)
    print(f"\nDatabase: {info['db_path']}")
    print(f"Size: {info['db_size_mb']} MB")
    print(f"\nTable Counts:")
    for table, count in info['tables'].items():
        print(f"  - {table}: {count}")
    print()
    
    # Close database
    db.close()
    
    return True


def main():
    """Main entry point"""
    # Setup logging
    logger = setup_logger()
    
    try:
        # Load config
        config = load_config()
        
        # Initialize database
        success = init_database(config)
        
        if success:
            print("✅ Database initialization successful!\n")
            return 0
        else:
            print("❌ Database initialization failed!\n")
            return 1
            
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
