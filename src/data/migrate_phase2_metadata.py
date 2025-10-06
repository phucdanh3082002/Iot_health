"""
PHASE 2: Database Migration - Add Metadata Columns
Thêm các cột metadata cho Signal Quality Index và thống kê đo
"""

import sqlite3
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def migrate_database(db_path: str):
    """
    Thêm các cột metadata vào bảng vitals
    
    New columns:
    - hr_sqi: Signal Quality Index (0-100)
    - spo2_cv: Coefficient of Variation for SpO2 R-values
    - peak_count: Number of peaks detected
    - measurement_duration: Time taken for measurement (seconds)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check existing columns
    cursor.execute("PRAGMA table_info(vitals)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    print(f"Existing columns: {existing_columns}")
    
    # Add new columns if not exist
    new_columns = [
        ("hr_sqi", "REAL", "NULL"),          # Signal Quality Index 0-100
        ("spo2_cv", "REAL", "NULL"),         # Coefficient of Variation
        ("peak_count", "INTEGER", "NULL"),   # Number of peaks
        ("measurement_duration", "REAL", "NULL")  # Duration in seconds
    ]
    
    for col_name, col_type, default in new_columns:
        if col_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE vitals ADD COLUMN {col_name} {col_type} DEFAULT {default}")
                print(f"✅ Added column: {col_name} ({col_type})")
            except sqlite3.OperationalError as e:
                print(f"⚠️  Column {col_name} already exists or error: {e}")
        else:
            print(f"ℹ️  Column {col_name} already exists, skipping")
    
    conn.commit()
    
    # Verify schema
    cursor.execute("PRAGMA table_info(vitals)")
    all_columns = cursor.fetchall()
    print("\n📋 Final schema:")
    for col in all_columns:
        print(f"  {col[1]:25s} {col[2]:10s} {'NOT NULL' if col[3] else ''} DEFAULT {col[4] if col[4] else 'NULL'}")
    
    # Show record count
    cursor.execute("SELECT COUNT(*) FROM vitals")
    count = cursor.fetchone()[0]
    print(f"\n📊 Total records: {count}")
    
    # Show sample of new columns (NULL for old records)
    cursor.execute("SELECT id, ts, hr, spo2, hr_sqi, spo2_cv, peak_count, measurement_duration FROM vitals ORDER BY id DESC LIMIT 3")
    print("\n🔍 Sample recent records:")
    for row in cursor.fetchall():
        print(f"  ID={row[0]}, TS={row[1]}, HR={row[2]}, SpO2={row[3]}, SQI={row[4]}, CV={row[5]}, Peaks={row[6]}, Duration={row[7]}")
    
    conn.close()
    print("\n✅ Migration completed successfully!")


if __name__ == "__main__":
    db_path = project_root / "data" / "vitals.db"
    print(f"Migrating database: {db_path}")
    migrate_database(str(db_path))
