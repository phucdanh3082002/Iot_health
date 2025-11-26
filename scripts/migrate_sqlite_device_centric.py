#!/usr/bin/env python3
"""
SQLite Migration Script - Device-Centric Approach
Migrates local SQLite database to allow NULL patient_id

Why needed:
- SQLite doesn't support ALTER COLUMN to modify constraints
- Must recreate tables with new schema

Steps:
1. Backup current database
2. Create new tables with nullable patient_id
3. Copy all data from old tables
4. Drop old tables
5. Rename new tables
"""

import sqlite3
import shutil
from datetime import datetime
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.models import Base
from sqlalchemy import create_engine

DB_PATH = 'data/health_monitor.db'
BACKUP_SUFFIX = datetime.now().strftime('%Y%m%d_%H%M%S')


def backup_database():
    """Backup current database"""
    if not os.path.exists(DB_PATH):
        print(f"⚠️  Database {DB_PATH} does not exist, will create new one")
        return None
    
    backup_path = f"{DB_PATH}.backup_{BACKUP_SUFFIX}"
    shutil.copy2(DB_PATH, backup_path)
    print(f"✅ Backup created: {backup_path}")
    return backup_path


def migrate_database():
    """Migrate database to new schema"""
    
    # Step 1: Backup
    print("=" * 60)
    print("SQLite Migration: Device-Centric Approach")
    print("=" * 60)
    backup_path = backup_database()
    
    # Step 2: Recreate database with new schema
    print("\n🔄 Recreating database with new schema...")
    
    # Remove old database
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"   Removed old database: {DB_PATH}")
    
    # Create new database with updated models
    engine = create_engine(f'sqlite:///{DB_PATH}')
    Base.metadata.create_all(engine)
    print(f"   Created new database with nullable patient_id")
    
    # Step 3: Copy data from backup (if exists)
    if backup_path and os.path.exists(backup_path):
        print("\n📋 Copying data from backup...")
        
        old_conn = sqlite3.connect(backup_path)
        new_conn = sqlite3.connect(DB_PATH)
        
        # Tables to migrate (in order to respect foreign keys)
        tables = [
            'devices',
            'patients', 
            'patient_thresholds',
            'health_records',
            'alerts',
            'sensor_calibrations',
            'system_logs',
            'device_ownership',
            'sync_queue'
        ]
        
        for table in tables:
            try:
                # Check if table exists in old database
                cursor = old_conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,)
                )
                if not cursor.fetchone():
                    print(f"   ⏭️  Skipping {table} (doesn't exist in backup)")
                    continue
                
                # Get column names from new table
                new_cursor = new_conn.execute(f"PRAGMA table_info({table})")
                new_columns = [row[1] for row in new_cursor.fetchall()]
                
                # Get column names from old table
                old_cursor = old_conn.execute(f"PRAGMA table_info({table})")
                old_columns = [row[1] for row in old_cursor.fetchall()]
                
                # Find common columns
                common_columns = [col for col in old_columns if col in new_columns]
                
                if not common_columns:
                    print(f"   ⚠️  No common columns in {table}, skipping")
                    continue
                
                columns_str = ', '.join(common_columns)
                
                # Copy data
                old_data = old_conn.execute(f"SELECT {columns_str} FROM {table}")
                rows = old_data.fetchall()
                
                if rows:
                    placeholders = ', '.join(['?' for _ in common_columns])
                    new_conn.executemany(
                        f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})",
                        rows
                    )
                    new_conn.commit()
                    print(f"   ✅ Copied {len(rows)} rows from {table}")
                else:
                    print(f"   ⏭️  No data in {table}")
                    
            except sqlite3.Error as e:
                print(f"   ⚠️  Error migrating {table}: {e}")
        
        old_conn.close()
        new_conn.close()
    
    print("\n" + "=" * 60)
    print("✅ Migration completed successfully!")
    print("=" * 60)
    print(f"\n📊 Summary:")
    print(f"   - Old database backed up to: {backup_path}")
    print(f"   - New database created: {DB_PATH}")
    print(f"   - Schema change: patient_id now allows NULL")
    print(f"\n🔧 Next steps:")
    print(f"   1. Test measurement and verify patient_id = NULL in local DB")
    print(f"   2. Verify cloud sync auto-resolves patient_id")
    print(f"   3. Check logs for any issues")


if __name__ == '__main__':
    try:
        migrate_database()
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
