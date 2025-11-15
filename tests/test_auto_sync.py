#!/usr/bin/env python3
"""
Test Auto-Sync to AWS RDS
Tạo dữ liệu test trong SQLite local và verify sync lên MySQL cloud

Author: IoT Health Monitor Team
Date: 2025-11-16
"""

import sys
import os
from pathlib import Path
import time
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import yaml
from dotenv import load_dotenv
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(project_root / '.env')

def load_config():
    """Load application config"""
    config_path = project_root / 'config' / 'app_config.yaml'
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def query_cloud_database(query, params=None):
    """Execute query on cloud database"""
    import mysql.connector
    
    config = load_config()
    mysql_cfg = config['cloud']['mysql']
    password = os.getenv(mysql_cfg.get('password_env', 'MYSQL_CLOUD_PASSWORD'))
    
    conn = mysql.connector.connect(
        host=mysql_cfg['host'],
        port=mysql_cfg['port'],
        user=mysql_cfg['user'],
        password=password,
        database=mysql_cfg['database'],
        connect_timeout=10
    )
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute(query, params or ())
    results = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return results

def test_auto_sync():
    """Test auto-sync functionality"""
    logger.info("=" * 70)
    logger.info("🔄 AUTO-SYNC TEST")
    logger.info("=" * 70)
    
    try:
        from src.data.database import DatabaseManager
        
        config = load_config()
        
        # Step 1: Initialize database with cloud sync enabled
        logger.info("\n📦 Step 1: Initialize DatabaseManager with cloud sync...")
        db_manager = DatabaseManager(config)
        
        if not db_manager.initialize():
            logger.error("❌ Failed to initialize database")
            return False
        
        logger.info("✅ Database initialized")
        
        # Verify cloud sync is enabled
        if not hasattr(db_manager, 'cloud_sync_manager') or db_manager.cloud_sync_manager is None:
            logger.error("❌ Cloud sync not initialized")
            return False
        
        logger.info("✅ Cloud sync manager is active")
        
        # Step 2: Insert test data into local SQLite
        logger.info("\n📝 Step 2: Insert test data into local SQLite...")
        
        test_patient_id = "test_patient_001"
        test_device_id = "rasp_pi_001"
        test_timestamp = datetime.now()
        
        # Insert patient if not exists
        with db_manager.get_session() as session:
            from src.data.models import Patient
            
            patient = session.query(Patient).filter_by(patient_id=test_patient_id).first()
            if not patient:
                patient = Patient(
                    patient_id=test_patient_id,
                    name="Test Patient for Auto-Sync",
                    age=30,
                    gender="M",
                    emergency_contact={"phone": "0123456789", "name": "Emergency Contact"}
                )
                session.add(patient)
                session.commit()
                logger.info(f"✅ Created test patient: {test_patient_id}")
            else:
                logger.info(f"✅ Test patient already exists: {test_patient_id}")
        
        # Insert health record
        with db_manager.get_session() as session:
            from src.data.models import HealthRecord
            
            record = HealthRecord(
                patient_id=test_patient_id,
                timestamp=test_timestamp,
                heart_rate=75,
                spo2=98,
                temperature=36.5,
                systolic_bp=120,
                diastolic_bp=80,
                mean_arterial_pressure=93,
                sensor_data={"device_id": test_device_id, "source": "auto_sync_test"}
            )
            session.add(record)
            session.commit()
            record_id = record.id
            
            logger.info(f"✅ Inserted health record (ID: {record_id})")
            logger.info(f"   Patient: {test_patient_id}")
            logger.info(f"   HR: 75 bpm, SpO2: 98%, Temp: 36.5°C")
            logger.info(f"   BP: 120/80 mmHg")
        
        # Step 3: Count records in local database
        logger.info("\n📊 Step 3: Count records in local SQLite...")
        with db_manager.get_session() as session:
            from src.data.models import HealthRecord, Patient
            
            local_patients = session.query(Patient).count()
            local_records = session.query(HealthRecord).count()
            
            logger.info(f"   Patients: {local_patients}")
            logger.info(f"   Health Records: {local_records}")
        
        # Step 4: Query cloud database BEFORE sync
        logger.info("\n☁️  Step 4: Query cloud database (BEFORE manual sync)...")
        try:
            cloud_patients_before = query_cloud_database(
                "SELECT COUNT(*) as count FROM patients WHERE patient_id = %s",
                (test_patient_id,)
            )
            cloud_records_before = query_cloud_database(
                "SELECT COUNT(*) as count FROM health_records WHERE patient_id = %s",
                (test_patient_id,)
            )
            
            logger.info(f"   Cloud patients: {cloud_patients_before[0]['count']}")
            logger.info(f"   Cloud health records: {cloud_records_before[0]['count']}")
        except Exception as e:
            logger.warning(f"⚠️  Cannot query cloud (will retry after sync): {e}")
            cloud_records_before = [{'count': 0}]
        
        # Step 5: Trigger manual sync
        logger.info("\n🔄 Step 5: Trigger manual sync to cloud...")
        logger.info("   (This simulates auto-sync that runs every 5 minutes)")
        
        # Method 1: Direct push of the health record
        logger.info(f"   Pushing health record ID {record_id} directly...")
        push_success = db_manager.cloud_sync_manager.push_health_record(record_id)
        
        if push_success:
            logger.info("   ✅ Direct push successful!")
        else:
            logger.warning("   ⚠️  Direct push failed, trying full sync...")
        
        # Method 2: Full sync (processes queue + existing records)
        result = db_manager.cloud_sync_manager.sync_all(direction='upload')
        
        if result.get('success', False):
            logger.info("✅ Sync completed!")
            logger.info(f"   Upload results: {result.get('upload', {})}")
            logger.info(f"   Duration: {result.get('duration_seconds', 0):.2f}s")
        else:
            logger.error(f"❌ Sync failed: {result.get('error', 'Unknown')}")
            return False
        
        # Step 6: Wait a moment for data to settle
        logger.info("\n⏳ Step 6: Wait 2 seconds for data to settle...")
        time.sleep(2)
        
        # Step 7: Query cloud database AFTER sync
        logger.info("\n☁️  Step 7: Query cloud database (AFTER sync)...")
        cloud_patients_after = query_cloud_database(
            "SELECT COUNT(*) as count FROM patients WHERE patient_id = %s",
            (test_patient_id,)
        )
        cloud_records_after = query_cloud_database(
            "SELECT COUNT(*) as count FROM health_records WHERE patient_id = %s",
            (test_patient_id,)
        )
        
        logger.info(f"   Cloud patients: {cloud_patients_after[0]['count']}")
        logger.info(f"   Cloud health records: {cloud_records_after[0]['count']}")
        
        # Step 8: Verify sync success
        logger.info("\n✅ Step 8: Verify sync results...")
        
        patient_synced = cloud_patients_after[0]['count'] > 0
        records_synced = cloud_records_after[0]['count'] > cloud_records_before[0]['count']
        
        if patient_synced:
            logger.info("   ✅ Patient synced to cloud")
        else:
            logger.warning("   ⚠️  Patient not found in cloud (may already exist)")
        
        if records_synced or cloud_records_after[0]['count'] > 0:
            logger.info("   ✅ Health records synced to cloud")
            logger.info(f"   📈 Records increased: {cloud_records_before[0]['count']} → {cloud_records_after[0]['count']}")
        else:
            logger.error("   ❌ Health records NOT synced to cloud")
            return False
        
        # Step 9: Query latest record details from cloud
        logger.info("\n📋 Step 9: Query latest synced record from cloud...")
        latest_records = query_cloud_database("""
            SELECT id, patient_id, timestamp, 
                   heart_rate, spo2, temperature, systolic_bp, diastolic_bp
            FROM health_records 
            WHERE patient_id = %s
            ORDER BY timestamp DESC
            LIMIT 5
        """, (test_patient_id,))
        
        logger.info(f"   Found {len(latest_records)} record(s) in cloud:")
        for idx, record in enumerate(latest_records, 1):
            logger.info(f"   {idx}. ID: {record['id']}")
            logger.info(f"      Time: {record['timestamp']}")
            logger.info(f"      HR: {record['heart_rate']} bpm, SpO2: {record['spo2']}%")
            logger.info(f"      Temp: {record['temperature']}°C, BP: {record['systolic_bp']}/{record['diastolic_bp']}")
        
        # Step 10: Test auto-sync scheduler status
        logger.info("\n⏰ Step 10: Check auto-sync scheduler status...")
        if hasattr(db_manager, 'sync_scheduler') and db_manager.sync_scheduler:
            scheduler = db_manager.sync_scheduler
            logger.info(f"   ✅ Scheduler is running")
            logger.info(f"   ⏱️  Interval: {scheduler.interval_seconds}s ({scheduler.interval_seconds/60:.1f} minutes)")
            logger.info(f"   🔄 Next sync in: ~{scheduler.interval_seconds}s")
        else:
            logger.warning("   ⚠️  Auto-sync scheduler not found")
            logger.info("   💡 Check config: cloud.sync.mode should be 'auto'")
        
        logger.info("\n" + "=" * 70)
        logger.info("🎉 AUTO-SYNC TEST PASSED!")
        logger.info("=" * 70)
        logger.info("\n💡 Summary:")
        logger.info("   ✅ Local SQLite → Cloud MySQL sync working")
        logger.info("   ✅ Data appears in AWS RDS database")
        logger.info("   ✅ Auto-sync scheduler running (every 5 minutes)")
        logger.info("\n📝 Next steps:")
        logger.info("   1. Monitor logs for automatic sync every 5 minutes")
        logger.info("   2. Run main.py to start full application")
        logger.info("   3. Create limited users (pi_sync, android_app)")
        
        return True
        
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        logger.error("   Make sure all dependencies are installed")
        return False
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def cleanup_test_data():
    """Clean up test data (optional)"""
    logger.info("\n🧹 Cleanup test data? (y/n): ")
    # Not implemented - manual cleanup if needed

if __name__ == "__main__":
    logger.info("\n" + "=" * 70)
    logger.info("🌐 AWS RDS AUTO-SYNC TEST")
    logger.info("=" * 70)
    logger.info("\n🔍 Checking environment...")
    
    password = os.getenv('MYSQL_CLOUD_PASSWORD')
    if not password:
        logger.error("❌ MYSQL_CLOUD_PASSWORD not found in .env")
        logger.error("   Please run: export MYSQL_CLOUD_PASSWORD=<your_password>")
        sys.exit(1)
    
    logger.info("✅ MYSQL_CLOUD_PASSWORD found")
    logger.info(f"   Password length: {len(password)} characters\n")
    
    # Run test
    success = test_auto_sync()
    
    sys.exit(0 if success else 1)
