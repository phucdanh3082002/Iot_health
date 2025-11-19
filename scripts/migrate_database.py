#!/usr/bin/env python3
"""
Database Migration Script - SQLite Local Database
Migrates existing SQLite database to new schema v2.0.0

WHAT THIS SCRIPT DOES:
1. Backup current database
2. Create new tables (devices, device_ownership, sync_queue)
3. Add missing columns to existing tables
4. Migrate data to new structure
5. Verify migration success

SAFE TO RUN MULTIPLE TIMES - Will skip already migrated items
"""

import sys
import os
from pathlib import Path
import sqlite3
import shutil
from datetime import datetime
import json

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import yaml
import logging
from src.utils.logger import setup_logger


def load_config():
    """Load application configuration"""
    config_path = project_root / 'config' / 'app_config.yaml'
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def backup_database(db_path: str) -> str:
    """
    Create backup of current database
    
    Returns:
        Path to backup file
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{db_path}.backup_{timestamp}"
    
    print(f"\n📦 Creating backup: {backup_path}")
    shutil.copy2(db_path, backup_path)
    
    # Verify backup
    if os.path.exists(backup_path):
        backup_size = os.path.getsize(backup_path) / 1024 / 1024
        print(f"✅ Backup created successfully ({backup_size:.2f} MB)")
        return backup_path
    else:
        raise Exception("Backup creation failed!")


def check_table_exists(cursor, table_name: str) -> bool:
    """Check if table exists"""
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
    return cursor.fetchone() is not None


def check_column_exists(cursor, table_name: str, column_name: str) -> bool:
    """Check if column exists in table"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


def migrate_database(db_path: str, config: dict):
    """
    Main migration function
    """
    print("\n" + "="*60)
    print("DATABASE MIGRATION - SQLite Schema v2.0.0")
    print("="*60)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # ========== STEP 1: Create new table - devices ==========
        print("\n1️⃣  Creating 'devices' table...")
        if not check_table_exists(cursor, 'devices'):
            cursor.execute("""
                CREATE TABLE devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id VARCHAR(50) NOT NULL UNIQUE,
                    device_name VARCHAR(100) NOT NULL,
                    device_type VARCHAR(50) DEFAULT 'blood_pressure_monitor',
                    location VARCHAR(200),
                    ip_address VARCHAR(45),
                    firmware_version VARCHAR(20),
                    os_version VARCHAR(50),
                    is_active BOOLEAN DEFAULT 1,
                    last_seen DATETIME,
                    pairing_code VARCHAR(32) UNIQUE,
                    pairing_qr_data TEXT,
                    paired_by VARCHAR(100),
                    paired_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Insert current device from config
            device_config = config.get('cloud', {}).get('device', {})
            device_id = device_config.get('device_id', 'rpi_bp_001')
            device_name = device_config.get('device_name', 'Raspberry Pi Monitor')
            location = device_config.get('location', 'Home')
            
            cursor.execute("""
                INSERT INTO devices (device_id, device_name, location, device_type, is_active, last_seen)
                VALUES (?, ?, ?, 'blood_pressure_monitor', 1, datetime('now'))
            """, (device_id, device_name, location))
            
            print(f"   ✅ Created 'devices' table and inserted device: {device_id}")
        else:
            print("   ⏭️  'devices' table already exists, skipping...")
        
        # ========== STEP 2: Create new table - device_ownership ==========
        print("\n2️⃣  Creating 'device_ownership' table...")
        if not check_table_exists(cursor, 'device_ownership'):
            cursor.execute("""
                CREATE TABLE device_ownership (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id VARCHAR(100) NOT NULL,
                    device_id VARCHAR(50) NOT NULL,
                    role VARCHAR(20) DEFAULT 'owner',
                    nickname VARCHAR(100),
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_accessed DATETIME,
                    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE,
                    UNIQUE (user_id, device_id)
                )
            """)
            print("   ✅ Created 'device_ownership' table")
        else:
            print("   ⏭️  'device_ownership' table already exists, skipping...")
        
        # ========== STEP 3: Create new table - sync_queue ==========
        print("\n3️⃣  Creating 'sync_queue' table...")
        if not check_table_exists(cursor, 'sync_queue'):
            cursor.execute("""
                CREATE TABLE sync_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id VARCHAR(50) NOT NULL,
                    table_name VARCHAR(50) NOT NULL,
                    operation VARCHAR(20) NOT NULL,
                    record_id VARCHAR(100) NOT NULL,
                    data_snapshot TEXT,
                    priority INTEGER DEFAULT 5,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    sync_status VARCHAR(20) DEFAULT 'pending',
                    sync_attempts INTEGER DEFAULT 0,
                    last_sync_attempt DATETIME,
                    error_message TEXT,
                    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
                )
            """)
            print("   ✅ Created 'sync_queue' table")
        else:
            print("   ⏭️  'sync_queue' table already exists, skipping...")
        
        # ========== STEP 4: Add missing columns to patients ==========
        print("\n4️⃣  Updating 'patients' table...")
        if check_table_exists(cursor, 'patients'):
            # Add device_id column if not exists
            if not check_column_exists(cursor, 'patients', 'device_id'):
                cursor.execute("ALTER TABLE patients ADD COLUMN device_id VARCHAR(50)")
                
                # Set device_id for existing patients
                device_id = config.get('cloud', {}).get('device', {}).get('device_id', 'rpi_bp_001')
                cursor.execute("UPDATE patients SET device_id = ?", (device_id,))
                print(f"   ✅ Added 'device_id' column to patients (set to {device_id})")
            else:
                print("   ⏭️  'device_id' column already exists in patients")
        
        # ========== STEP 5: Add missing columns to health_records ==========
        print("\n5️⃣  Updating 'health_records' table...")
        if check_table_exists(cursor, 'health_records'):
            device_id = config.get('cloud', {}).get('device', {}).get('device_id', 'rpi_bp_001')
            
            # Add device_id column
            if not check_column_exists(cursor, 'health_records', 'device_id'):
                cursor.execute("ALTER TABLE health_records ADD COLUMN device_id VARCHAR(50)")
                cursor.execute("UPDATE health_records SET device_id = ?", (device_id,))
                print(f"   ✅ Added 'device_id' column to health_records")
            
            # Add sync_status column
            if not check_column_exists(cursor, 'health_records', 'sync_status'):
                cursor.execute("ALTER TABLE health_records ADD COLUMN sync_status VARCHAR(20) DEFAULT 'pending'")
                print("   ✅ Added 'sync_status' column to health_records")
            
            # Add synced_at column
            if not check_column_exists(cursor, 'health_records', 'synced_at'):
                cursor.execute("ALTER TABLE health_records ADD COLUMN synced_at DATETIME")
                print("   ✅ Added 'synced_at' column to health_records")
        
        # ========== STEP 6: Add missing columns to alerts ==========
        print("\n6️⃣  Updating 'alerts' table...")
        if check_table_exists(cursor, 'alerts'):
            device_id = config.get('cloud', {}).get('device', {}).get('device_id', 'rpi_bp_001')
            
            # Add device_id column
            if not check_column_exists(cursor, 'alerts', 'device_id'):
                cursor.execute("ALTER TABLE alerts ADD COLUMN device_id VARCHAR(50)")
                cursor.execute("UPDATE alerts SET device_id = ?", (device_id,))
                print(f"   ✅ Added 'device_id' column to alerts")
            
            # Add health_record_id column
            if not check_column_exists(cursor, 'alerts', 'health_record_id'):
                cursor.execute("ALTER TABLE alerts ADD COLUMN health_record_id INTEGER")
                print("   ✅ Added 'health_record_id' column to alerts")
            
            # Add acknowledged_by column
            if not check_column_exists(cursor, 'alerts', 'acknowledged_by'):
                cursor.execute("ALTER TABLE alerts ADD COLUMN acknowledged_by VARCHAR(100)")
                print("   ✅ Added 'acknowledged_by' column to alerts")
            
            # Add notification_sent column
            if not check_column_exists(cursor, 'alerts', 'notification_sent'):
                cursor.execute("ALTER TABLE alerts ADD COLUMN notification_sent BOOLEAN DEFAULT 0")
                print("   ✅ Added 'notification_sent' column to alerts")
            
            # Add notification_method column
            if not check_column_exists(cursor, 'alerts', 'notification_method'):
                cursor.execute("ALTER TABLE alerts ADD COLUMN notification_method VARCHAR(50)")
                print("   ✅ Added 'notification_method' column to alerts")
        
        # ========== STEP 7: Add missing columns to sensor_calibrations ==========
        print("\n7️⃣  Updating 'sensor_calibrations' table...")
        if check_table_exists(cursor, 'sensor_calibrations'):
            device_id = config.get('cloud', {}).get('device', {}).get('device_id', 'rpi_bp_001')
            
            # Add device_id column
            if not check_column_exists(cursor, 'sensor_calibrations', 'device_id'):
                cursor.execute("ALTER TABLE sensor_calibrations ADD COLUMN device_id VARCHAR(50)")
                cursor.execute("UPDATE sensor_calibrations SET device_id = ?", (device_id,))
                print(f"   ✅ Added 'device_id' column to sensor_calibrations")
        
        # ========== STEP 8: Add missing columns to system_logs ==========
        print("\n8️⃣  Updating 'system_logs' table...")
        if check_table_exists(cursor, 'system_logs'):
            device_id = config.get('cloud', {}).get('device', {}).get('device_id', 'rpi_bp_001')
            
            # Add device_id column
            if not check_column_exists(cursor, 'system_logs', 'device_id'):
                cursor.execute("ALTER TABLE system_logs ADD COLUMN device_id VARCHAR(50)")
                cursor.execute("UPDATE system_logs SET device_id = ?", (device_id,))
                print(f"   ✅ Added 'device_id' column to system_logs")
            
            # Rename 'function' to 'function_name' if needed
            if check_column_exists(cursor, 'system_logs', 'function') and not check_column_exists(cursor, 'system_logs', 'function_name'):
                # SQLite doesn't support RENAME COLUMN directly in older versions
                # We'll create new column and copy data
                cursor.execute("ALTER TABLE system_logs ADD COLUMN function_name VARCHAR(100)")
                cursor.execute("UPDATE system_logs SET function_name = function")
                print("   ✅ Added 'function_name' column to system_logs (migrated from 'function')")
        
        # ========== STEP 9: Create indexes for performance ==========
        print("\n9️⃣  Creating indexes...")
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_devices_device_id ON devices(device_id)",
            "CREATE INDEX IF NOT EXISTS idx_devices_is_active ON devices(is_active)",
            "CREATE INDEX IF NOT EXISTS idx_device_ownership_user_id ON device_ownership(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_device_ownership_device_id ON device_ownership(device_id)",
            "CREATE INDEX IF NOT EXISTS idx_sync_queue_device_id ON sync_queue(device_id)",
            "CREATE INDEX IF NOT EXISTS idx_sync_queue_status ON sync_queue(sync_status)",
            "CREATE INDEX IF NOT EXISTS idx_health_records_device_id ON health_records(device_id)",
            "CREATE INDEX IF NOT EXISTS idx_health_records_sync_status ON health_records(sync_status)",
            "CREATE INDEX IF NOT EXISTS idx_alerts_device_id ON alerts(device_id)",
            "CREATE INDEX IF NOT EXISTS idx_sensor_calibrations_device_id ON sensor_calibrations(device_id)",
        ]
        
        for index_sql in indexes:
            cursor.execute(index_sql)
        print(f"   ✅ Created {len(indexes)} indexes")
        
        # Commit all changes
        conn.commit()
        
        # ========== STEP 10: Verification ==========
        print("\n🔍 Verifying migration...")
        verification = {
            'devices': check_table_exists(cursor, 'devices'),
            'device_ownership': check_table_exists(cursor, 'device_ownership'),
            'sync_queue': check_table_exists(cursor, 'sync_queue'),
            'patients.device_id': check_column_exists(cursor, 'patients', 'device_id'),
            'health_records.device_id': check_column_exists(cursor, 'health_records', 'device_id'),
            'health_records.sync_status': check_column_exists(cursor, 'health_records', 'sync_status'),
            'alerts.device_id': check_column_exists(cursor, 'alerts', 'device_id'),
            'alerts.notification_sent': check_column_exists(cursor, 'alerts', 'notification_sent'),
        }
        
        all_ok = all(verification.values())
        
        for item, status in verification.items():
            status_icon = "✅" if status else "❌"
            print(f"   {status_icon} {item}")
        
        if all_ok:
            print("\n" + "="*60)
            print("✅ MIGRATION COMPLETED SUCCESSFULLY!")
            print("="*60)
            print(f"\nDatabase: {db_path}")
            print(f"Backup: {backup_path}")
            print("\nYour database has been upgraded to schema v2.0.0")
            print("You can now:")
            print("  - Use device management features")
            print("  - Enable multi-user device ownership")
            print("  - Benefit from improved cloud sync with store & forward queue")
        else:
            print("\n" + "="*60)
            print("⚠️  MIGRATION COMPLETED WITH WARNINGS")
            print("="*60)
            print("Some items failed verification. Please review the log above.")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ MIGRATION FAILED: {e}")
        print(f"\nYour original database is backed up at: {backup_path}")
        print("You can restore it by copying the backup file back to the original location.")
        raise
    
    finally:
        conn.close()


def main():
    """Main entry point"""
    logger = setup_logger()
    
    try:
        # Load config
        config = load_config()
        
        # Get database path
        db_path = config.get('database', {}).get('path', 'data/health_monitor.db')
        
        if not os.path.exists(db_path):
            print(f"❌ Database not found: {db_path}")
            print("Please initialize the database first using init_database.py")
            return 1
        
        # Show database info
        db_size = os.path.getsize(db_path) / 1024 / 1024
        print(f"\n📊 Current database: {db_path}")
        print(f"   Size: {db_size:.2f} MB")
        
        # Confirm migration
        response = input("\n⚠️  This will modify your database structure. Continue? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Migration cancelled.")
            return 0
        
        # Backup database
        global backup_path
        backup_path = backup_database(db_path)
        
        # Run migration
        migrate_database(db_path, config)
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
