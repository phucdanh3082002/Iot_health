#!/usr/bin/env python3
"""
SQLite Local Database Migration - AI Threshold Feature
Date: 2025-12-15
Purpose: Migrate local SQLite to match new MySQL schema
"""

import sqlite3
import os
import sys
import json
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def backup_database(db_path: str) -> str:
    """Create backup of database before migration"""
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Copy database file
    import shutil
    if os.path.exists(db_path):
        shutil.copy2(db_path, backup_path)
        print(f"✅ Backup created: {backup_path}")
        return backup_path
    else:
        print(f"⚠️ Database file not found: {db_path}")
        return None


def migrate_patients_table(conn: sqlite3.Connection):
    """Add new columns to patients table"""
    cursor = conn.cursor()
    
    print("\n📋 Migrating patients table...")
    
    # Get existing columns
    cursor.execute("PRAGMA table_info(patients)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    # Define new columns
    new_columns = {
        'height': 'REAL',
        'weight': 'REAL',
        'blood_type': 'VARCHAR(5)',
        'chronic_diseases': 'TEXT',  # JSON as TEXT in SQLite
        'medications': 'TEXT',
        'allergies': 'TEXT',
        'family_history': 'TEXT',
        'smoking_status': 'VARCHAR(20)',
        'alcohol_consumption': 'VARCHAR(20)',
        'exercise_frequency': 'VARCHAR(20)',
        'risk_factors': 'TEXT'
    }
    
    # Add missing columns
    added_count = 0
    for column_name, column_type in new_columns.items():
        if column_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE patients ADD COLUMN {column_name} {column_type}")
                print(f"  ✅ Added column: {column_name}")
                added_count += 1
            except sqlite3.OperationalError as e:
                print(f"  ⚠️ Skip {column_name}: {e}")
    
    # Create indexes
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_blood_type ON patients(blood_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_smoking_status ON patients(smoking_status)")
        print(f"  ✅ Created indexes")
    except sqlite3.Error as e:
        print(f"  ⚠️ Index creation warning: {e}")
    
    conn.commit()
    print(f"✅ Patients table migrated ({added_count} columns added)")


def migrate_patient_thresholds_table(conn: sqlite3.Connection):
    """Add AI threshold columns to patient_thresholds table"""
    cursor = conn.cursor()
    
    print("\n📋 Migrating patient_thresholds table...")
    
    # Get existing columns
    cursor.execute("PRAGMA table_info(patient_thresholds)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    # Define new columns
    new_columns = {
        'min_warning': 'REAL',
        'max_warning': 'REAL',
        'generation_method': 'VARCHAR(50) DEFAULT "manual"',
        'ai_confidence': 'REAL',
        'ai_model': 'VARCHAR(50)',
        'generation_timestamp': 'DATETIME',
        'metadata': 'TEXT'  # JSON as TEXT
    }
    
    # Add missing columns
    added_count = 0
    for column_name, column_type in new_columns.items():
        if column_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE patient_thresholds ADD COLUMN {column_name} {column_type}")
                print(f"  ✅ Added column: {column_name}")
                added_count += 1
            except sqlite3.OperationalError as e:
                print(f"  ⚠️ Skip {column_name}: {e}")
    
    # Create indexes
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_generation_method ON patient_thresholds(generation_method)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_confidence ON patient_thresholds(ai_confidence)")
        print(f"  ✅ Created indexes")
    except sqlite3.Error as e:
        print(f"  ⚠️ Index creation warning: {e}")
    
    # Set default generation_method for existing records
    cursor.execute("""
        UPDATE patient_thresholds 
        SET generation_method = 'manual',
            generation_timestamp = created_at
        WHERE generation_method IS NULL
    """)
    updated_count = cursor.rowcount
    
    conn.commit()
    print(f"✅ Patient thresholds table migrated ({added_count} columns added, {updated_count} records updated)")


def migrate_sync_queue_table(conn: sqlite3.Connection):
    """Add priority column to sync_queue table"""
    cursor = conn.cursor()
    
    print("\n📋 Migrating sync_queue table...")
    
    # Get existing columns
    cursor.execute("PRAGMA table_info(sync_queue)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    # Add priority column if missing
    if 'priority' not in existing_columns:
        try:
            cursor.execute("ALTER TABLE sync_queue ADD COLUMN priority INTEGER DEFAULT 5")
            print(f"  ✅ Added column: priority")
            
            # Create index
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_priority ON sync_queue(priority, created_at)")
            print(f"  ✅ Created index on priority")
        except sqlite3.OperationalError as e:
            print(f"  ⚠️ Skip priority: {e}")
    else:
        print(f"  ℹ️ Column 'priority' already exists")
    
    # Add index for table_name if missing
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_table_name ON sync_queue(table_name)")
        print(f"  ✅ Created index on table_name")
    except sqlite3.Error as e:
        print(f"  ⚠️ Index creation warning: {e}")
    
    conn.commit()
    print(f"✅ Sync queue table migrated")


def verify_migration(conn: sqlite3.Connection):
    """Verify migration completed successfully"""
    cursor = conn.cursor()
    
    print("\n🔍 Verifying migration...")
    
    # Check patients table
    cursor.execute("PRAGMA table_info(patients)")
    patients_columns = [row[1] for row in cursor.fetchall()]
    print(f"  Patients columns: {len(patients_columns)}")
    
    required_patient_columns = ['height', 'weight', 'blood_type', 'chronic_diseases', 
                                'medications', 'allergies', 'smoking_status']
    missing_patient = [col for col in required_patient_columns if col not in patients_columns]
    if missing_patient:
        print(f"  ⚠️ Missing in patients: {missing_patient}")
    else:
        print(f"  ✅ All patient columns present")
    
    # Check patient_thresholds table
    cursor.execute("PRAGMA table_info(patient_thresholds)")
    threshold_columns = [row[1] for row in cursor.fetchall()]
    print(f"  Patient thresholds columns: {len(threshold_columns)}")
    
    required_threshold_columns = ['min_warning', 'max_warning', 'generation_method', 
                                  'ai_confidence', 'ai_model']
    missing_threshold = [col for col in required_threshold_columns if col not in threshold_columns]
    if missing_threshold:
        print(f"  ⚠️ Missing in thresholds: {missing_threshold}")
    else:
        print(f"  ✅ All threshold columns present")
    
    # Check sync_queue table
    cursor.execute("PRAGMA table_info(sync_queue)")
    queue_columns = [row[1] for row in cursor.fetchall()]
    if 'priority' in queue_columns:
        print(f"  ✅ Sync queue has priority column")
    else:
        print(f"  ⚠️ Sync queue missing priority column")
    
    # Show indexes
    print(f"\n📊 Database indexes:")
    for table in ['patients', 'patient_thresholds', 'sync_queue']:
        cursor.execute(f"PRAGMA index_list({table})")
        indexes = cursor.fetchall()
        print(f"  {table}: {len(indexes)} indexes")


def main():
    """Main migration function"""
    print("=" * 60)
    print("SQLite Database Migration - AI Threshold Feature")
    print("=" * 60)
    
    # Database path
    db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'health_monitor.db')
    db_path = os.path.abspath(db_path)
    
    print(f"\n📁 Database: {db_path}")
    
    # Check if database exists
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        print(f"ℹ️ Run the application first to create the database")
        return 1
    
    # Backup database
    backup_path = backup_database(db_path)
    if not backup_path:
        print("⚠️ Proceeding without backup...")
    
    # Connect to database
    try:
        conn = sqlite3.connect(db_path)
        print(f"✅ Connected to database")
        
        # Run migrations
        migrate_patients_table(conn)
        migrate_patient_thresholds_table(conn)
        migrate_sync_queue_table(conn)
        
        # Verify migration
        verify_migration(conn)
        
        # Close connection
        conn.close()
        print(f"\n✅ Migration completed successfully!")
        print(f"ℹ️ Backup: {backup_path if backup_path else 'No backup created'}")
        
        return 0
        
    except sqlite3.Error as e:
        print(f"\n❌ Migration failed: {e}")
        if backup_path:
            print(f"ℹ️ Restore from backup: {backup_path}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
