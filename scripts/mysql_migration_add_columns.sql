-- ============================================================
-- IoT Health Monitor - MySQL Migration Script
-- Purpose: Add missing columns to existing MySQL tables
-- Version: 2.0.0
-- Date: 2025-11-20
-- ============================================================
-- This script adds new columns to existing tables created by v1.0
-- Run this AFTER mysql_cloud_schema.sql if tables already exist
-- ============================================================

USE iot_health_cloud;

-- ============================================================
-- 1. ALTER DEVICES TABLE - Add new columns
-- ============================================================
-- Add firmware_version
SET @col_exists = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
  WHERE TABLE_SCHEMA = 'iot_health_cloud' AND TABLE_NAME = 'devices' AND COLUMN_NAME = 'firmware_version'
);
SET @sql = IF(@col_exists = 0, 
  'ALTER TABLE devices ADD COLUMN firmware_version VARCHAR(20) DEFAULT NULL COMMENT "Firmware version" AFTER ip_address', 
  'SELECT "firmware_version already exists" AS message'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Add os_version
SET @col_exists = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
  WHERE TABLE_SCHEMA = 'iot_health_cloud' AND TABLE_NAME = 'devices' AND COLUMN_NAME = 'os_version'
);
SET @sql = IF(@col_exists = 0, 
  'ALTER TABLE devices ADD COLUMN os_version VARCHAR(50) DEFAULT NULL COMMENT "Operating system version" AFTER firmware_version', 
  'SELECT "os_version already exists" AS message'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Add pairing_code
SET @col_exists = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
  WHERE TABLE_SCHEMA = 'iot_health_cloud' AND TABLE_NAME = 'devices' AND COLUMN_NAME = 'pairing_code'
);
SET @sql = IF(@col_exists = 0, 
  'ALTER TABLE devices ADD COLUMN pairing_code VARCHAR(32) DEFAULT NULL COMMENT "Temporary pairing code for QR" AFTER last_seen', 
  'SELECT "pairing_code already exists" AS message'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Add unique constraint for pairing_code
SET @idx_exists = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS 
  WHERE TABLE_SCHEMA = 'iot_health_cloud' AND TABLE_NAME = 'devices' AND INDEX_NAME = 'pairing_code'
);
SET @sql = IF(@idx_exists = 0 AND @col_exists > 0, 
  'ALTER TABLE devices ADD UNIQUE KEY pairing_code (pairing_code)', 
  'SELECT "pairing_code unique constraint already exists" AS message'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Add pairing_qr_data
SET @col_exists = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
  WHERE TABLE_SCHEMA = 'iot_health_cloud' AND TABLE_NAME = 'devices' AND COLUMN_NAME = 'pairing_qr_data'
);
SET @sql = IF(@col_exists = 0, 
  'ALTER TABLE devices ADD COLUMN pairing_qr_data TEXT DEFAULT NULL COMMENT "QR code data (JSON)" AFTER pairing_code', 
  'SELECT "pairing_qr_data already exists" AS message'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Add paired_by
SET @col_exists = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
  WHERE TABLE_SCHEMA = 'iot_health_cloud' AND TABLE_NAME = 'devices' AND COLUMN_NAME = 'paired_by'
);
SET @sql = IF(@col_exists = 0, 
  'ALTER TABLE devices ADD COLUMN paired_by VARCHAR(100) DEFAULT NULL COMMENT "User ID who paired device" AFTER pairing_qr_data', 
  'SELECT "paired_by already exists" AS message'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Add paired_at
SET @col_exists = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
  WHERE TABLE_SCHEMA = 'iot_health_cloud' AND TABLE_NAME = 'devices' AND COLUMN_NAME = 'paired_at'
);
SET @sql = IF(@col_exists = 0, 
  'ALTER TABLE devices ADD COLUMN paired_at DATETIME DEFAULT NULL COMMENT "Pairing timestamp" AFTER paired_by', 
  'SELECT "paired_at already exists" AS message'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Add index for pairing_code
SET @idx_exists = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS 
  WHERE TABLE_SCHEMA = 'iot_health_cloud' AND TABLE_NAME = 'devices' AND INDEX_NAME = 'idx_pairing_code'
);
SET @sql = IF(@idx_exists = 0, 
  'CREATE INDEX idx_pairing_code ON devices(pairing_code)', 
  'SELECT "idx_pairing_code already exists" AS message'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ============================================================
-- 2. ALTER HEALTH_RECORDS TABLE - Add device_id if missing
-- ============================================================
-- Check if device_id column exists, if not add it
SET @col_exists = (
  SELECT COUNT(*) 
  FROM INFORMATION_SCHEMA.COLUMNS 
  WHERE TABLE_SCHEMA = 'iot_health_cloud' 
    AND TABLE_NAME = 'health_records' 
    AND COLUMN_NAME = 'device_id'
);

-- Add device_id if it doesn't exist
SET @sql = IF(@col_exists = 0,
  'ALTER TABLE health_records ADD COLUMN device_id VARCHAR(50) NOT NULL COMMENT "Device that recorded measurement" AFTER patient_id',
  'SELECT "device_id already exists in health_records" AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add foreign key if device_id was just added
SET @fk_sql = IF(@col_exists = 0,
  'ALTER TABLE health_records ADD FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE ON UPDATE CASCADE',
  'SELECT "Foreign key already exists" AS message'
);

PREPARE stmt FROM @fk_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add index for device_id
SET @idx_exists = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS 
  WHERE TABLE_SCHEMA = 'iot_health_cloud' AND TABLE_NAME = 'health_records' AND INDEX_NAME = 'idx_device_timestamp'
);
SET @sql = IF(@idx_exists = 0, 
  'CREATE INDEX idx_device_timestamp ON health_records(device_id, timestamp DESC)', 
  'SELECT "idx_device_timestamp already exists" AS message'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ============================================================
-- 3. ALTER ALERTS TABLE - Add device_id if missing
-- ============================================================
SET @col_exists = (
  SELECT COUNT(*) 
  FROM INFORMATION_SCHEMA.COLUMNS 
  WHERE TABLE_SCHEMA = 'iot_health_cloud' 
    AND TABLE_NAME = 'alerts' 
    AND COLUMN_NAME = 'device_id'
);

SET @sql = IF(@col_exists = 0,
  'ALTER TABLE alerts ADD COLUMN device_id VARCHAR(50) NOT NULL COMMENT "Device that generated alert" AFTER patient_id',
  'SELECT "device_id already exists in alerts" AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add foreign key
SET @fk_sql = IF(@col_exists = 0,
  'ALTER TABLE alerts ADD FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE ON UPDATE CASCADE',
  'SELECT "Foreign key already exists" AS message'
);

PREPARE stmt FROM @fk_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add index
SET @idx_exists = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS 
  WHERE TABLE_SCHEMA = 'iot_health_cloud' AND TABLE_NAME = 'alerts' AND INDEX_NAME = 'idx_device_id'
);
SET @sql = IF(@idx_exists = 0, 
  'CREATE INDEX idx_device_id ON alerts(device_id)', 
  'SELECT "idx_device_id already exists on alerts" AS message'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ============================================================
-- 4. ALTER ALERTS TABLE - Add sync/notification columns
-- ============================================================
-- Add notification_sent
SET @col_exists = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
  WHERE TABLE_SCHEMA = 'iot_health_cloud' AND TABLE_NAME = 'alerts' AND COLUMN_NAME = 'notification_sent'
);
SET @sql = IF(@col_exists = 0, 
  'ALTER TABLE alerts ADD COLUMN notification_sent BOOLEAN DEFAULT FALSE COMMENT "Whether notification was sent" AFTER resolved_at', 
  'SELECT "notification_sent already exists" AS message'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Add notification_method
SET @col_exists = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
  WHERE TABLE_SCHEMA = 'iot_health_cloud' AND TABLE_NAME = 'alerts' AND COLUMN_NAME = 'notification_method'
);
SET @sql = IF(@col_exists = 0, 
  'ALTER TABLE alerts ADD COLUMN notification_method VARCHAR(50) DEFAULT NULL COMMENT "Notification method: mqtt, fcm, email" AFTER notification_sent', 
  'SELECT "notification_method already exists" AS message'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ============================================================
-- 5. ALTER HEALTH_RECORDS TABLE - Add sync status columns
-- ============================================================
-- Add sync_status
SET @col_exists = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
  WHERE TABLE_SCHEMA = 'iot_health_cloud' AND TABLE_NAME = 'health_records' AND COLUMN_NAME = 'sync_status'
);
SET @sql = IF(@col_exists = 0, 
  'ALTER TABLE health_records ADD COLUMN sync_status ENUM("pending", "synced", "failed") DEFAULT "synced" COMMENT "Cloud sync status" AFTER measurement_context', 
  'SELECT "sync_status already exists" AS message'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Add synced_at
SET @col_exists = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
  WHERE TABLE_SCHEMA = 'iot_health_cloud' AND TABLE_NAME = 'health_records' AND COLUMN_NAME = 'synced_at'
);
SET @sql = IF(@col_exists = 0, 
  'ALTER TABLE health_records ADD COLUMN synced_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT "When record was synced" AFTER sync_status', 
  'SELECT "synced_at already exists" AS message'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Add index for sync_status
SET @idx_exists = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS 
  WHERE TABLE_SCHEMA = 'iot_health_cloud' AND TABLE_NAME = 'health_records' AND INDEX_NAME = 'idx_sync_status'
);
SET @sql = IF(@idx_exists = 0, 
  'CREATE INDEX idx_sync_status ON health_records(sync_status)', 
  'SELECT "idx_sync_status already exists" AS message'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ============================================================
-- 6. ALTER SENSOR_CALIBRATIONS TABLE - Add device_id if missing
-- ============================================================
SET @col_exists = (
  SELECT COUNT(*) 
  FROM INFORMATION_SCHEMA.COLUMNS 
  WHERE TABLE_SCHEMA = 'iot_health_cloud' 
    AND TABLE_NAME = 'sensor_calibrations' 
    AND COLUMN_NAME = 'device_id'
);

SET @sql = IF(@col_exists = 0,
  'ALTER TABLE sensor_calibrations ADD COLUMN device_id VARCHAR(50) NOT NULL COMMENT "Device identifier" AFTER id',
  'SELECT "device_id already exists in sensor_calibrations" AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add foreign key
SET @fk_sql = IF(@col_exists = 0,
  'ALTER TABLE sensor_calibrations ADD FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE ON UPDATE CASCADE',
  'SELECT "Foreign key already exists" AS message'
);

PREPARE stmt FROM @fk_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add index
SET @idx_exists = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS 
  WHERE TABLE_SCHEMA = 'iot_health_cloud' AND TABLE_NAME = 'sensor_calibrations' AND INDEX_NAME = 'idx_device_sensor'
);
SET @sql = IF(@idx_exists = 0, 
  'CREATE INDEX idx_device_sensor ON sensor_calibrations(device_id, sensor_name)', 
  'SELECT "idx_device_sensor already exists" AS message'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ============================================================
-- 7. CREATE DEVICE_OWNERSHIP TABLE if not exists
-- ============================================================
CREATE TABLE IF NOT EXISTS device_ownership (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Auto-increment primary key',
    user_id VARCHAR(100) NOT NULL COMMENT 'User identifier (from Android app)',
    device_id VARCHAR(50) NOT NULL COMMENT 'Device identifier',
    
    -- Access control
    role ENUM('owner', 'caregiver', 'viewer') DEFAULT 'owner' COMMENT 'User role for this device',
    nickname VARCHAR(100) DEFAULT NULL COMMENT 'User-defined device nickname',
    
    -- Timestamps
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'When user was granted access',
    last_accessed DATETIME DEFAULT NULL COMMENT 'Last time user accessed device data',
    
    -- Foreign keys
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE ON UPDATE CASCADE,
    
    -- Constraints
    UNIQUE KEY unique_user_device (user_id, device_id),
    INDEX idx_user_id (user_id),
    INDEX idx_device_id (device_id),
    INDEX idx_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Multi-user device ownership and access control';

-- ============================================================
-- 8. CREATE SYNC_QUEUE TABLE if not exists
-- ============================================================
CREATE TABLE IF NOT EXISTS sync_queue (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT 'Auto-increment primary key',
    device_id VARCHAR(50) NOT NULL COMMENT 'Device identifier',
    
    -- Queue item details
    table_name VARCHAR(50) NOT NULL COMMENT 'Target table name',
    operation ENUM('INSERT', 'UPDATE', 'DELETE') NOT NULL COMMENT 'Operation type',
    record_id VARCHAR(100) NOT NULL COMMENT 'Record identifier',
    data_snapshot JSON DEFAULT NULL COMMENT 'Data snapshot for operation',
    priority INT DEFAULT 5 COMMENT 'Priority (1=highest, 10=lowest)',
    
    -- Timestamps
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'When queued',
    
    -- Sync status
    sync_status ENUM('pending', 'syncing', 'success', 'failed') DEFAULT 'pending' COMMENT 'Sync status',
    sync_attempts INT DEFAULT 0 COMMENT 'Number of sync attempts',
    last_sync_attempt DATETIME DEFAULT NULL COMMENT 'Last attempt timestamp',
    error_message TEXT DEFAULT NULL COMMENT 'Error message if failed',
    
    -- Foreign keys
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE ON UPDATE CASCADE,
    
    -- Indexes
    INDEX idx_device_status (device_id, sync_status),
    INDEX idx_priority (priority, created_at),
    INDEX idx_sync_status (sync_status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Store & forward queue for offline sync';

-- ============================================================
-- 9. UPDATE EXISTING DEVICE RECORDS with default values
-- ============================================================
-- Update existing devices to have firmware/os version from config
UPDATE devices 
SET 
  firmware_version = COALESCE(firmware_version, '1.0.0'),
  os_version = COALESCE(os_version, 'Raspberry Pi OS Bookworm 64-bit')
WHERE firmware_version IS NULL OR os_version IS NULL;

-- ============================================================
-- VERIFICATION QUERIES
-- ============================================================
SELECT '✅ Migration completed successfully!' AS status;

-- Show updated devices table structure
SELECT 'Devices table columns:' AS info;
SELECT COLUMN_NAME, COLUMN_TYPE, COLUMN_COMMENT 
FROM INFORMATION_SCHEMA.COLUMNS 
WHERE TABLE_SCHEMA = 'iot_health_cloud' AND TABLE_NAME = 'devices'
ORDER BY ORDINAL_POSITION;

-- Count records in each table
SELECT 'Table record counts:' AS info;
SELECT 
  (SELECT COUNT(*) FROM devices) AS devices_count,
  (SELECT COUNT(*) FROM patients) AS patients_count,
  (SELECT COUNT(*) FROM health_records) AS health_records_count,
  (SELECT COUNT(*) FROM alerts) AS alerts_count,
  (SELECT COUNT(*) FROM sensor_calibrations) AS calibrations_count,
  (SELECT COUNT(*) FROM device_ownership) AS ownership_count,
  (SELECT COUNT(*) FROM sync_queue) AS sync_queue_count;

-- Show sample device record
SELECT 'Sample device record:' AS info;
SELECT 
  device_id, 
  device_name, 
  firmware_version, 
  os_version, 
  is_active, 
  last_seen,
  pairing_code,
  paired_at,
  created_at
FROM devices 
LIMIT 1;
