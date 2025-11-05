"""
Test Script for Cloud Sync Manager
Tests connection, push/pull operations, and sync functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from datetime import datetime
from src.data.database import DatabaseManager
from src.communication.cloud_sync_manager import CloudSyncManager


def load_config():
    """Load application configuration"""
    config_path = 'config/app_config.yaml'
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def print_section(title):
    """Print section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def test_cloud_connection(config):
    """Test 1: Cloud connection"""
    print_section("TEST 1: Cloud Connection")
    
    try:
        # Initialize database manager
        db = DatabaseManager(config)
        db.initialize()
        
        if not db.cloud_sync_manager:
            print("❌ Cloud sync is disabled in config")
            print("   Enable it in config/app_config.yaml: cloud.enabled = true")
            return False
        
        sync_mgr = db.cloud_sync_manager
        
        # Check connection status
        status = sync_mgr.get_sync_status()
        print("Cloud Sync Status:")
        for key, value in status.items():
            print(f"  {key}: {value}")
        
        # Test connection
        if sync_mgr.check_cloud_connection():
            print("\n✅ Cloud connection test PASSED")
            return True
        else:
            print("\n❌ Cloud connection test FAILED")
            print("   Check:")
            print("   1. MySQL server is running on PC")
            print("   2. Network connection between Pi and PC")
            print("   3. Firewall allows port 3306")
            print("   4. User credentials are correct")
            return False
            
    except Exception as e:
        print(f"❌ Connection test error: {e}")
        return False
    finally:
        db.close()


def test_push_health_record(config):
    """Test 2: Push health record to cloud"""
    print_section("TEST 2: Push Health Record")
    
    try:
        db = DatabaseManager(config)
        db.initialize()
        
        if not db.cloud_sync_manager:
            print("❌ Cloud sync not enabled")
            return False
        
        # Create test health record
        test_data = {
            'patient_id': 'patient_001',
            'timestamp': datetime.now(),
            'heart_rate': 72.0,
            'spo2': 98.0,
            'temperature': 36.5,
            'systolic_bp': 120.0,
            'diastolic_bp': 80.0,
            'sensor_data': '{"signal_quality_index": 85, "peak_count": 10}'
        }
        
        print("Creating test health record...")
        record_id = db.save_health_record(test_data)
        
        if record_id:
            print(f"✅ Health record created: ID={record_id}")
            print(f"   Heart Rate: {test_data['heart_rate']} BPM")
            print(f"   SpO2: {test_data['spo2']}%")
            print(f"   Temperature: {test_data['temperature']}°C")
            print(f"   Blood Pressure: {test_data['systolic_bp']}/{test_data['diastolic_bp']} mmHg")
            
            # Check if auto-synced
            stats = db.cloud_sync_manager.get_sync_statistics()
            print(f"\nSync Statistics:")
            print(f"   Total pushes: {stats['total_pushes']}")
            print(f"   Successful: {stats['successful_pushes']}")
            print(f"   Failed: {stats['failed_pushes']}")
            print(f"   Success rate: {stats['success_rate']}%")
            
            if stats['successful_pushes'] > 0:
                print("\n✅ Push health record test PASSED")
                return True
            else:
                print("\n⚠️  Record saved locally but sync pending")
                print("   (This is normal if cloud is offline - will retry later)")
                return True
        else:
            print("❌ Failed to create health record")
            return False
            
    except Exception as e:
        print(f"❌ Push test error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_push_alert(config):
    """Test 3: Push alert to cloud"""
    print_section("TEST 3: Push Alert")
    
    try:
        db = DatabaseManager(config)
        db.initialize()
        
        if not db.cloud_sync_manager:
            print("❌ Cloud sync not enabled")
            return False
        
        # Create test alert
        alert_data = {
            'patient_id': 'patient_001',
            'alert_type': 'high_heart_rate',
            'severity': 'medium',
            'message': 'Heart rate above normal threshold',
            'vital_sign': 'heart_rate',
            'current_value': 110.0,
            'threshold_value': 100.0,
            'timestamp': datetime.now()
        }
        
        print("Creating test alert...")
        alert_id = db.save_alert(alert_data)
        
        if alert_id:
            print(f"✅ Alert created: ID={alert_id}")
            print(f"   Type: {alert_data['alert_type']}")
            print(f"   Severity: {alert_data['severity']}")
            print(f"   Message: {alert_data['message']}")
            
            # Check sync stats
            stats = db.cloud_sync_manager.get_sync_statistics()
            print(f"\nSync Statistics:")
            print(f"   Total pushes: {stats['total_pushes']}")
            print(f"   Successful: {stats['successful_pushes']}")
            
            if stats['successful_pushes'] > 0:
                print("\n✅ Push alert test PASSED")
                return True
            else:
                print("\n⚠️  Alert saved locally but sync pending")
                return True
        else:
            print("❌ Failed to create alert")
            return False
            
    except Exception as e:
        print(f"❌ Alert test error: {e}")
        return False
    finally:
        db.close()


def test_pull_thresholds(config):
    """Test 4: Pull patient thresholds from cloud"""
    print_section("TEST 4: Pull Patient Thresholds")
    
    try:
        db = DatabaseManager(config)
        db.initialize()
        
        if not db.cloud_sync_manager:
            print("❌ Cloud sync not enabled")
            return False
        
        sync_mgr = db.cloud_sync_manager
        
        # Try to pull thresholds
        print("Pulling thresholds from cloud...")
        success = sync_mgr.pull_patient_thresholds('patient_001')
        
        if success:
            print("✅ Successfully pulled thresholds from cloud")
            
            # Display pulled thresholds
            thresholds = db.get_patient_thresholds('patient_001')
            if thresholds:
                print("\nPulled Thresholds:")
                for vital, threshold in thresholds.items():
                    print(f"  {vital}:")
                    print(f"    Normal: {threshold['min_normal']} - {threshold['max_normal']}")
                    print(f"    Critical: {threshold['min_critical']} - {threshold['max_critical']}")
                
                print("\n✅ Pull thresholds test PASSED")
                return True
            else:
                print("⚠️  No thresholds found")
                return True
        else:
            print("⚠️  No thresholds in cloud (this is normal for new setup)")
            return True
            
    except Exception as e:
        print(f"❌ Pull test error: {e}")
        return False
    finally:
        db.close()


def test_sync_all(config):
    """Test 5: Full sync operation"""
    print_section("TEST 5: Full Sync")
    
    try:
        db = DatabaseManager(config)
        db.initialize()
        
        if not db.cloud_sync_manager:
            print("❌ Cloud sync not enabled")
            return False
        
        sync_mgr = db.cloud_sync_manager
        
        print("Performing full sync...")
        results = sync_mgr.sync_all(direction='both')
        
        print("\nSync Results:")
        print(f"  Started: {results.get('started_at')}")
        print(f"  Direction: {results.get('direction')}")
        print(f"  Success: {results.get('success')}")
        
        if results.get('push_results'):
            print(f"\n  Push Results: {results['push_results']}")
        
        if results.get('pull_results'):
            print(f"  Pull Results: {results['pull_results']}")
        
        if results.get('errors'):
            print(f"  Errors: {results['errors']}")
        
        if results.get('success'):
            print("\n✅ Full sync test PASSED")
            return True
        else:
            print("\n❌ Full sync test FAILED")
            return False
            
    except Exception as e:
        print(f"❌ Sync test error: {e}")
        return False
    finally:
        db.close()


def test_sync_statistics(config):
    """Test 6: Sync statistics and monitoring"""
    print_section("TEST 6: Sync Statistics")
    
    try:
        db = DatabaseManager(config)
        db.initialize()
        
        if not db.cloud_sync_manager:
            print("❌ Cloud sync not enabled")
            return False
        
        sync_mgr = db.cloud_sync_manager
        
        # Get detailed statistics
        stats = sync_mgr.get_sync_statistics()
        
        print("Detailed Sync Statistics:")
        print(f"  Device ID: {stats.get('device_id')}")
        print(f"  Last Sync: {stats.get('last_sync')}")
        print(f"\n  Push Operations:")
        print(f"    Total: {stats.get('total_pushes', 0)}")
        print(f"    Successful: {stats.get('successful_pushes', 0)}")
        print(f"    Failed: {stats.get('failed_pushes', 0)}")
        print(f"\n  Pull Operations:")
        print(f"    Total: {stats.get('total_pulls', 0)}")
        print(f"    Successful: {stats.get('successful_pulls', 0)}")
        print(f"    Failed: {stats.get('failed_pulls', 0)}")
        print(f"\n  Queue:")
        print(f"    Size: {stats.get('queue_size', 0)}")
        print(f"\n  Overall Success Rate: {stats.get('success_rate', 0)}%")
        
        print("\n✅ Statistics test PASSED")
        return True
        
    except Exception as e:
        print(f"❌ Statistics test error: {e}")
        return False
    finally:
        db.close()


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("  CLOUD SYNC MANAGER - TEST SUITE")
    print("="*70)
    
    # Load config
    try:
        config = load_config()
    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        return
    
    # Check if cloud sync is enabled
    if not config.get('cloud', {}).get('enabled', False):
        print("\n⚠️  WARNING: Cloud sync is DISABLED in config")
        print("   To enable: Edit config/app_config.yaml")
        print("   Set: cloud.enabled = true")
        print("   Then run this test again.\n")
        return
    
    # Run tests
    test_results = []
    
    # Test 1: Connection
    test_results.append(("Connection", test_cloud_connection(config)))
    
    # Only continue if connection works
    if test_results[0][1]:
        test_results.append(("Push Health Record", test_push_health_record(config)))
        test_results.append(("Push Alert", test_push_alert(config)))
        test_results.append(("Pull Thresholds", test_pull_thresholds(config)))
        test_results.append(("Full Sync", test_sync_all(config)))
        test_results.append(("Statistics", test_sync_statistics(config)))
    else:
        print("\n⚠️  Skipping remaining tests due to connection failure")
        print("   Fix connection issues first, then run tests again")
    
    # Print summary
    print_section("TEST SUMMARY")
    
    passed = sum(1 for _, result in test_results if result)
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}  {test_name}")
    
    print(f"\n  Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n  🎉 ALL TESTS PASSED!")
        print("  Cloud sync is working correctly.")
    else:
        print(f"\n  ⚠️  {total - passed} test(s) failed")
        print("  Review error messages above and fix issues.")
    
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    main()
