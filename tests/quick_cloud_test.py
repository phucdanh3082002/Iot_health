#!/usr/bin/env python3
"""
Quick Cloud Sync Connection Test
Kiểm tra kết nối MySQL cloud và đăng ký device
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import yaml
from datetime import datetime
from src.data.database import DatabaseManager
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

def main():
    print("="*70)
    print("🔍 CLOUD SYNC - QUICK CONNECTION TEST")
    print("="*70)
    
    # Load config
    config_path = 'config/app_config.yaml'
    print(f"\n📁 Loading config from: {config_path}")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return False
    
    # Check cloud enabled
    cloud_config = config.get('cloud', {})
    if not cloud_config.get('enabled', False):
        print("\n⚠️  Cloud sync is DISABLED in config!")
        print("   Set cloud.enabled = true in app_config.yaml")
        return False
    
    print(f"✅ Cloud sync enabled")
    print(f"   Host: {cloud_config['mysql']['host']}")
    print(f"   Database: {cloud_config['mysql']['database']}")
    print(f"   User: {cloud_config['mysql']['user']}")
    
    # Initialize database manager
    print("\n🔄 Initializing DatabaseManager...")
    try:
        db = DatabaseManager(config)
        db.initialize()
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False
    
    print("✅ DatabaseManager initialized")
    
    # Check cloud sync manager
    if not db.cloud_sync_manager:
        print("❌ CloudSyncManager not initialized!")
        print("   Check if cloud.enabled = true in config")
        db.close()
        return False
    
    print("✅ CloudSyncManager initialized")
    
    # Test connection
    print("\n🌐 Testing MySQL cloud connection...")
    try:
        if db.cloud_sync_manager.check_cloud_connection():
            print("✅ MySQL connection successful!")
        else:
            print("❌ MySQL connection failed!")
            print("   Troubleshooting:")
            print("   1. Check PC MySQL server is running")
            print("   2. Check firewall allows port 3306")
            print("   3. Check bind-address in MySQL config")
            print("   4. Check user/password correct")
            print(f"   5. Try: mysql -h {cloud_config['mysql']['host']} -u {cloud_config['mysql']['user']} -p")
            db.close()
            return False
    except Exception as e:
        print(f"❌ Connection error: {e}")
        db.close()
        return False
    
    # Get sync status
    print("\n📊 Sync Status:")
    try:
        status = db.cloud_sync_manager.get_sync_status()
        for key, value in status.items():
            print(f"   {key}: {value}")
    except Exception as e:
        print(f"⚠️  Could not get status: {e}")
    
    # Test creating a dummy health record
    print("\n🧪 Testing auto-sync with dummy record...")
    try:
        test_data = {
            'patient_id': config.get('patient', {}).get('id', 'patient_001'),
            'timestamp': datetime.now(),
            'heart_rate': 75.0,
            'spo2': 98.0,
            'temperature': 36.6,
            'systolic_bp': 120.0,
            'diastolic_bp': 80.0,
            'mean_arterial_pressure': 93.3
        }
        
        record_id = db.save_health_record(test_data)
        print(f"✅ Saved health record locally: ID={record_id}")
        print(f"   Auto-sync should have triggered to cloud...")
        
        # Wait a moment for sync
        import time
        time.sleep(1)
        
        # Get statistics
        stats = db.cloud_sync_manager.get_sync_statistics()
        print(f"\n📈 Sync Statistics:")
        print(f"   Total pushes: {stats.get('total_pushes', 0)}")
        print(f"   Successful: {stats.get('successful_pushes', 0)}")
        print(f"   Failed: {stats.get('failed_pushes', 0)}")
        print(f"   Success rate: {stats.get('success_rate', 0):.1f}%")
        print(f"   Queue size: {stats.get('queue_size', 0)}")
        
        if stats.get('successful_pushes', 0) > 0:
            print("\n🎉 AUTO-SYNC WORKING! Data pushed to cloud successfully!")
        else:
            print("\n⚠️  Record saved locally but sync may have failed")
            print(f"   Queue size: {stats.get('queue_size', 0)} (will retry later)")
            
    except Exception as e:
        print(f"❌ Test record error: {e}")
        import traceback
        traceback.print_exc()
    
    # Cleanup
    db.close()
    
    print("\n" + "="*70)
    print("✅ TEST COMPLETED")
    print("="*70)
    print("\n💡 Next Steps:")
    print("   1. Check MySQL Workbench on PC:")
    print("      USE iot_health_cloud;")
    print("      SELECT * FROM devices;")
    print("      SELECT * FROM health_records ORDER BY timestamp DESC LIMIT 5;")
    print("")
    print("   2. If data is there → SUCCESS! Auto-sync working!")
    print("   3. Run full test suite: python3 tests/test_cloud_sync.py")
    print("")
    
    return True

if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
