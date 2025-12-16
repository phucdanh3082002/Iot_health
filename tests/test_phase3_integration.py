#!/usr/bin/env python3
"""
Test Script: End-to-End AI Threshold Integration
Tests Phase 3 implementation: CloudSync + AlertSystem dynamic thresholds

Usage:
    python3 tests/test_phase3_integration.py
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import yaml
import time
from datetime import datetime
from src.communication.cloud_sync_manager import CloudSyncManager
from src.data.database import DatabaseManager
from src.ai.alert_system import AlertSystem

# ANSI colors for pretty output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_success(msg):
    print(f"{GREEN}✓ {msg}{RESET}")

def print_error(msg):
    print(f"{RED}✗ {msg}{RESET}")

def print_info(msg):
    print(f"{BLUE}ℹ {msg}{RESET}")

def print_warning(msg):
    print(f"{YELLOW}⚠ {msg}{RESET}")

def load_config():
    """Load app config"""
    with open('config/app_config.yaml', 'r') as f:
        return yaml.safe_load(f)

def test_cloud_connection(config):
    """Test 1: Cloud connection"""
    print_info("\n[TEST 1] Testing cloud connection...")
    
    try:
        db = DatabaseManager(config['database'])
        sync_mgr = CloudSyncManager(config['cloud'], db)
        
        if sync_mgr.check_cloud_connection():
            print_success("Cloud connection established")
            return True, sync_mgr, db
        else:
            print_error("Cannot connect to cloud database")
            return False, None, None
    except Exception as e:
        print_error(f"Cloud connection failed: {e}")
        return False, None, None

def test_sync_patient_thresholds(sync_mgr, patient_id=None):
    """Test 2: Sync patient thresholds from cloud"""
    print_info(f"\n[TEST 2] Syncing patient thresholds (patient_id={patient_id or 'all'})...")
    
    try:
        results = sync_mgr.sync_patient_thresholds(patient_id)
        
        print(f"  Thresholds synced: {results['thresholds_synced']}")
        print(f"  Thresholds updated: {results['thresholds_updated']}")
        
        if results['errors']:
            print_warning(f"  Errors: {results['errors']}")
        
        if results['thresholds_synced'] > 0 or results['thresholds_updated'] > 0:
            print_success("Thresholds synced successfully")
            return True, results
        else:
            print_warning("No thresholds to sync (device may not have assigned patients)")
            return True, results
            
    except Exception as e:
        print_error(f"Threshold sync failed: {e}")
        return False, None

def verify_local_thresholds(db, patient_id):
    """Test 3: Verify thresholds in local SQLite"""
    print_info(f"\n[TEST 3] Verifying local thresholds for patient {patient_id}...")
    
    try:
        with db.get_session() as session:
            from src.data.models import PatientThreshold
            
            thresholds = session.query(PatientThreshold).filter_by(
                patient_id=patient_id
            ).all()
            
            if not thresholds:
                print_warning(f"No thresholds found in local database for patient {patient_id}")
                return False
            
            print_success(f"Found {len(thresholds)} threshold records:")
            for t in thresholds:
                print(f"  - {t.vital_sign}: min={t.min_normal}, max={t.max_normal}, method={t.generation_method}")
            
            return True
            
    except Exception as e:
        print_error(f"Local verification failed: {e}")
        return False

def test_alert_system_load_thresholds(config, db, patient_id):
    """Test 4: AlertSystem loads patient thresholds"""
    print_info(f"\n[TEST 4] Testing AlertSystem threshold loading for patient {patient_id}...")
    
    try:
        alert_sys = AlertSystem(config.get('alerts', {}), database=db)
        
        # Load thresholds
        thresholds = alert_sys.get_patient_thresholds(patient_id)
        
        if not thresholds:
            print_error("AlertSystem returned empty thresholds")
            return False, None
        
        print_success("AlertSystem loaded thresholds:")
        for vital_sign, values in thresholds.items():
            min_n = values.get('min_normal', 'N/A')
            max_n = values.get('max_normal', 'N/A')
            method = values.get('generation_method', 'baseline')
            print(f"  - {vital_sign}: [{min_n} - {max_n}] (method={method})")
        
        return True, alert_sys
        
    except Exception as e:
        print_error(f"AlertSystem load failed: {e}")
        return False, None

def test_alert_trigger_with_custom_threshold(alert_sys, patient_id):
    """Test 5: Trigger alert with patient-specific threshold"""
    print_info(f"\n[TEST 5] Testing alert trigger with custom thresholds...")
    
    try:
        # Get patient thresholds
        thresholds = alert_sys.get_patient_thresholds(patient_id)
        
        # Test heart rate alert (use threshold slightly above max_normal)
        hr_threshold = thresholds.get('heart_rate', {})
        max_normal = hr_threshold.get('max_normal', 100)
        test_hr = max_normal + 3  # Slightly above threshold
        
        print(f"  Testing HR alert: {test_hr} BPM (threshold: {max_normal})")
        
        # Trigger check
        alert_sys.check_vital_signs(patient_id, {
            'heart_rate': test_hr,
            'spo2': 98,
            'systolic_bp': 120,
            'diastolic_bp': 80
        })
        
        # Note: Without TTS manager, alert won't actually play sound
        # But we can verify the logic runs without errors
        print_success("Alert check executed successfully (TTS would play if enabled)")
        print_info(f"  Expected alert: 'Nhịp tim quá cao: {test_hr} BPM (ngưỡng: {max_normal})'")
        
        return True
        
    except Exception as e:
        print_error(f"Alert trigger test failed: {e}")
        return False

def test_fallback_to_baseline(alert_sys):
    """Test 6: Fallback to baseline for non-existent patient"""
    print_info(f"\n[TEST 6] Testing fallback to baseline thresholds...")
    
    try:
        fake_patient_id = "non_existent_patient_999"
        thresholds = alert_sys.get_patient_thresholds(fake_patient_id)
        
        # Should return baseline thresholds
        hr_baseline = thresholds.get('heart_rate', {})
        
        if hr_baseline.get('min_normal') == 60 and hr_baseline.get('max_normal') == 100:
            print_success("Fallback to baseline thresholds works correctly")
            print(f"  Heart rate baseline: 60-100 BPM")
            return True
        else:
            print_error(f"Fallback failed: got {hr_baseline}")
            return False
            
    except Exception as e:
        print_error(f"Fallback test failed: {e}")
        return False

def main():
    """Run all tests"""
    print(f"\n{'='*60}")
    print(f"{BLUE}Phase 3 Integration Test Suite{RESET}")
    print(f"Testing: CloudSync + AlertSystem Dynamic Thresholds")
    print(f"{'='*60}")
    
    # Load config
    try:
        config = load_config()
        print_success("Config loaded")
    except Exception as e:
        print_error(f"Failed to load config: {e}")
        return 1
    
    # Test 1: Cloud connection
    success, sync_mgr, db = test_cloud_connection(config)
    if not success:
        print_error("\n❌ TEST SUITE FAILED: Cannot connect to cloud")
        return 1
    
    # Test 2: Sync thresholds
    device_id = config['cloud']['device']['device_id']
    print_info(f"\nDevice ID: {device_id}")
    
    success, sync_results = test_sync_patient_thresholds(sync_mgr)
    if not success:
        print_error("\n❌ TEST SUITE FAILED: Threshold sync failed")
        return 1
    
    # Get patient_id from sync results (if any)
    # For now, use a test patient_id - you should replace this with actual patient
    test_patient_id = input(f"\n{YELLOW}Enter patient_id to test (or press Enter to skip patient tests): {RESET}").strip()
    
    if test_patient_id:
        # Test 3: Verify local thresholds
        verify_local_thresholds(db, test_patient_id)
        
        # Test 4: AlertSystem load thresholds
        success, alert_sys = test_alert_system_load_thresholds(config, db, test_patient_id)
        if not success:
            print_warning("AlertSystem test skipped (load failed)")
        else:
            # Test 5: Trigger alert
            test_alert_trigger_with_custom_threshold(alert_sys, test_patient_id)
            
            # Test 6: Fallback
            test_fallback_to_baseline(alert_sys)
    else:
        print_info("\nSkipping patient-specific tests")
        
        # Still test fallback
        try:
            alert_sys = AlertSystem(config.get('alerts', {}), database=db)
            test_fallback_to_baseline(alert_sys)
        except Exception as e:
            print_error(f"Fallback test failed: {e}")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"{GREEN}✓ TEST SUITE COMPLETED{RESET}")
    print(f"{'='*60}")
    print(f"\nNext steps:")
    print(f"1. Create a patient with AI thresholds via Android/API")
    print(f"2. Wait 60 seconds for auto-sync")
    print(f"3. Run this test again with the patient_id")
    print(f"4. Test live measurement with real sensors\n")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
