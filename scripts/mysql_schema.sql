-- ============================================================================
-- MySQL Cloud Database Schema for IoT Health Monitoring System
-- ============================================================================
-- Version: 1.0.0
-- Date: 2025-11-04
-- Description: Cloud database schema for syncing data from Raspberry Pi devices
-- ============================================================================

-- Create database
CREATE DATABASE IF NOT EXISTS iot_health_cloud 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

USE iot_health_cloud;

-- ============================================================================
-- 1. DEVICES TABLE
-- Purpose: Registry of all Raspberry Pi devices
-- ============================================================================

CREATE TABLE IF NOT EXISTS devices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id VARCHAR(50) UNIQUE NOT NULL COMMENT 'Unique device identifier',
    device_name VARCHAR(100) NOT NULL COMMENT 'Friendly name',
    location VARCHAR(200) COMMENT 'Physical location',
    ip_address VARCHAR(45) COMMENT 'Last known IP address',
    last_seen DATETIME(6) COMMENT 'Last connection time',
    firmware_version VARCHAR(50) COMMENT 'Device firmware version',
    is_active TINYINT(1) DEFAULT 1 COMMENT 'Device active status',
    created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    
    INDEX idx_device_id (device_id),
    INDEX idx_last_seen (last_seen),
    INDEX idx_active (is_active)
) ENGINE=InnoDB COMMENT='Raspberry Pi devices registry';

-- ============================================================================
-- 2. PATIENTS TABLE
-- Purpose: Patient information with device tracking
-- ============================================================================

CREATE TABLE IF NOT EXISTS patients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id VARCHAR(50) UNIQUE NOT NULL COMMENT 'Unique patient ID',
    device_id VARCHAR(50) COMMENT 'Primary monitoring device',
    name VARCHAR(100) NOT NULL COMMENT 'Patient name',
    age INT COMMENT 'Patient age',
    gender CHAR(1) CHECK (gender IN ('M', 'F', 'O')) COMMENT 'Gender: M/F/O',
    medical_conditions JSON COMMENT 'Medical history as JSON',
    emergency_contact JSON COMMENT 'Emergency contacts as JSON',
    created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    is_active TINYINT(1) DEFAULT 1 COMMENT 'Patient active status',
    
    INDEX idx_patient_id (patient_id),
    INDEX idx_device_id (device_id),
    INDEX idx_active (is_active),
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE SET NULL
) ENGINE=InnoDB COMMENT='Patient information';

-- ============================================================================
-- 3. HEALTH_RECORDS TABLE (Partitioned by year)
-- Purpose: Vital signs measurements from devices
-- NOTE: Foreign keys removed due to MySQL partitioning limitation
--       Referential integrity enforced at application level
-- NOTE: PRIMARY KEY must include partitioning column (timestamp)
-- ============================================================================

CREATE TABLE IF NOT EXISTS health_records (
    id BIGINT AUTO_INCREMENT COMMENT 'Auto-incrementing ID',
    patient_id VARCHAR(50) NOT NULL COMMENT 'Patient identifier',
    device_id VARCHAR(50) NOT NULL COMMENT 'Device that recorded this data',
    timestamp DATETIME(6) NOT NULL COMMENT 'Measurement timestamp with microseconds',
    
    -- Vital Signs (DECIMAL for precision)
    heart_rate DECIMAL(6,2) COMMENT 'Heart rate in BPM',
    spo2 DECIMAL(5,2) COMMENT 'SpO2 percentage',
    temperature DECIMAL(4,2) COMMENT 'Temperature in Celsius',
    systolic_bp DECIMAL(6,2) COMMENT 'Systolic blood pressure in mmHg',
    diastolic_bp DECIMAL(6,2) COMMENT 'Diastolic blood pressure in mmHg',
    mean_arterial_pressure DECIMAL(6,2) COMMENT 'MAP in mmHg',
    
    -- Metadata
    sensor_data JSON COMMENT 'Additional sensor metadata (SQI, peaks, etc.)',
    data_quality DECIMAL(3,2) COMMENT 'Quality score 0-1',
    measurement_context VARCHAR(50) COMMENT 'Context: rest/activity/sleep',
    
    -- Sync tracking
    synced_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'Time synced to cloud',
    sync_status ENUM('pending', 'synced', 'conflict') DEFAULT 'synced',
    
    -- Primary key must include partition column
    -- Note: PRIMARY KEY (id, timestamp) ensures id uniqueness via AUTO_INCREMENT
    PRIMARY KEY (id, timestamp),
    
    INDEX idx_patient_timestamp (patient_id, timestamp),
    INDEX idx_device_timestamp (device_id, timestamp),
    INDEX idx_timestamp (timestamp),
    INDEX idx_sync_status (sync_status)
    -- Note: UNIQUE KEY on id removed - not allowed with partitioning
    -- Note: Foreign keys removed for partitioning support
    -- Application must ensure referential integrity
) ENGINE=InnoDB COMMENT='Health vital signs records'
PARTITION BY RANGE (YEAR(timestamp)) (
    PARTITION p2024 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION p2026 VALUES LESS THAN (2027),
    PARTITION p2027 VALUES LESS THAN (2028),
    PARTITION pmax VALUES LESS THAN MAXVALUE
);

-- ============================================================================
-- 4. ALERTS TABLE
-- Purpose: Health alerts with notification tracking
-- NOTE: FK to health_records removed due to partitioning limitation
-- ============================================================================

CREATE TABLE IF NOT EXISTS alerts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL COMMENT 'Patient identifier',
    device_id VARCHAR(50) NOT NULL COMMENT 'Device that generated alert',
    health_record_id BIGINT COMMENT 'Link to specific measurement',
    
    -- Alert details
    alert_type VARCHAR(20) NOT NULL COMMENT 'Type of alert',
    severity ENUM('low', 'medium', 'high', 'critical') NOT NULL COMMENT 'Alert severity',
    message TEXT NOT NULL COMMENT 'Alert message',
    vital_sign VARCHAR(20) COMMENT 'Affected vital sign',
    current_value DECIMAL(10,2) COMMENT 'Current value that triggered alert',
    threshold_value DECIMAL(10,2) COMMENT 'Threshold that was exceeded',
    
    -- Alert lifecycle
    timestamp DATETIME(6) NOT NULL COMMENT 'Alert creation time',
    acknowledged TINYINT(1) DEFAULT 0 COMMENT 'Alert acknowledged flag',
    acknowledged_at DATETIME(6) COMMENT 'Time alert was acknowledged',
    acknowledged_by VARCHAR(100) COMMENT 'User/System who acknowledged',
    resolved TINYINT(1) DEFAULT 0 COMMENT 'Alert resolved flag',
    resolved_at DATETIME(6) COMMENT 'Time alert was resolved',
    
    -- Notification tracking
    notification_sent TINYINT(1) DEFAULT 0 COMMENT 'Notification sent flag',
    notification_method ENUM('TTS', 'SMS', 'Email', 'Push') DEFAULT 'TTS' COMMENT 'Notification method',
    
    INDEX idx_patient_timestamp (patient_id, timestamp),
    INDEX idx_device_timestamp (device_id, timestamp),
    INDEX idx_severity (severity),
    INDEX idx_acknowledged (acknowledged),
    INDEX idx_resolved (resolved),
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE,
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE RESTRICT
    -- Note: FK to health_records removed due to partitioning limitation
) ENGINE=InnoDB COMMENT='Health alerts and warnings';

-- ============================================================================
-- 5. PATIENT_THRESHOLDS TABLE
-- Purpose: Personalized vital sign thresholds
-- ============================================================================

CREATE TABLE IF NOT EXISTS patient_thresholds (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL COMMENT 'Patient identifier',
    vital_sign VARCHAR(20) NOT NULL COMMENT 'Vital sign name',
    
    -- Threshold ranges
    min_normal DECIMAL(10,2) COMMENT 'Minimum normal value',
    max_normal DECIMAL(10,2) COMMENT 'Maximum normal value',
    min_critical DECIMAL(10,2) COMMENT 'Minimum critical value',
    max_critical DECIMAL(10,2) COMMENT 'Maximum critical value',
    
    is_active TINYINT(1) DEFAULT 1 COMMENT 'Threshold active status',
    created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    
    UNIQUE KEY unique_patient_vital (patient_id, vital_sign),
    INDEX idx_patient_id (patient_id),
    INDEX idx_active (is_active),
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='Personalized vital sign thresholds';

-- ============================================================================
-- 6. SENSOR_CALIBRATIONS TABLE
-- Purpose: Sensor calibration data per device
-- ============================================================================

CREATE TABLE IF NOT EXISTS sensor_calibrations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id VARCHAR(50) NOT NULL COMMENT 'Device where sensor is installed',
    sensor_name VARCHAR(50) NOT NULL COMMENT 'Sensor name (HX710B, MAX30102, etc.)',
    calibration_type VARCHAR(20) NOT NULL COMMENT 'Calibration type (two_point, etc.)',
    
    -- Calibration data (stored as JSON)
    reference_values JSON COMMENT 'Reference calibration values',
    measured_values JSON COMMENT 'Measured calibration values',
    calibration_factors JSON COMMENT 'Calibration factors (offset, slope, etc.)',
    
    calibrated_at DATETIME(6) COMMENT 'Calibration timestamp',
    is_active TINYINT(1) DEFAULT 1 COMMENT 'Calibration active status',
    notes TEXT COMMENT 'Additional calibration notes',
    
    UNIQUE KEY unique_device_sensor (device_id, sensor_name),
    INDEX idx_device_id (device_id),
    INDEX idx_sensor_name (sensor_name),
    INDEX idx_active (is_active),
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='Sensor calibration data';

-- ============================================================================
-- 7. SYSTEM_LOGS TABLE (Partitioned by year - same as health_records)
-- Purpose: System event logs from devices
-- NOTE: FK removed due to partitioning limitation
-- NOTE: PRIMARY KEY must include partitioning column (timestamp)
-- NOTE: Changed from UNIX_TIMESTAMP to YEAR() - UNIX_TIMESTAMP is timezone-dependent
-- ============================================================================

CREATE TABLE IF NOT EXISTS system_logs (
    id BIGINT AUTO_INCREMENT COMMENT 'Auto-incrementing ID',
    device_id VARCHAR(50) COMMENT 'Source device',
    level VARCHAR(10) NOT NULL COMMENT 'Log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)',
    message TEXT NOT NULL COMMENT 'Log message',
    module VARCHAR(50) COMMENT 'Source module',
    function_name VARCHAR(50) COMMENT 'Source function name',
    line_number INT COMMENT 'Source line number',
    timestamp DATETIME(6) NOT NULL COMMENT 'Log timestamp',
    additional_data JSON COMMENT 'Additional log data as JSON',
    
    -- Primary key must include partition column
    -- Note: PRIMARY KEY (id, timestamp) ensures id uniqueness via AUTO_INCREMENT
    PRIMARY KEY (id, timestamp),
    
    INDEX idx_device_timestamp (device_id, timestamp),
    INDEX idx_level (level),
    INDEX idx_timestamp (timestamp)
    -- Note: UNIQUE KEY on id removed - not allowed with partitioning
    -- Note: FK to devices removed for partitioning support
) ENGINE=InnoDB COMMENT='System event logs'
PARTITION BY RANGE (YEAR(timestamp)) (
    PARTITION p2024 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION p2026 VALUES LESS THAN (2027),
    PARTITION p2027 VALUES LESS THAN (2028),
    PARTITION pmax VALUES LESS THAN MAXVALUE
);

-- ============================================================================
-- 8. SYNC_QUEUE TABLE
-- Purpose: Track sync operations and failures (Store & Forward queue)
-- ============================================================================

CREATE TABLE IF NOT EXISTS sync_queue (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    device_id VARCHAR(50) NOT NULL COMMENT 'Source device',
    table_name VARCHAR(50) NOT NULL COMMENT 'Table name being synced',
    operation ENUM('INSERT', 'UPDATE', 'DELETE') NOT NULL COMMENT 'Sync operation type',
    record_id BIGINT NOT NULL COMMENT 'ID of record in source table',
    data_snapshot JSON NOT NULL COMMENT 'Full record data snapshot',
    
    -- Sync tracking
    created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'Queue entry creation time',
    sync_attempts INT DEFAULT 0 COMMENT 'Number of sync attempts',
    last_sync_attempt DATETIME(6) COMMENT 'Last sync attempt time',
    sync_status ENUM('pending', 'syncing', 'success', 'failed') DEFAULT 'pending' COMMENT 'Sync status',
    error_message TEXT COMMENT 'Error message if sync failed',
    
    INDEX idx_device_status (device_id, sync_status),
    INDEX idx_status_created (sync_status, created_at),
    INDEX idx_table_name (table_name),
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='Sync queue for offline operations';

-- ============================================================================
-- VIEWS FOR COMMON QUERIES
-- ============================================================================

-- View: Latest vitals per patient
CREATE OR REPLACE VIEW v_latest_vitals AS
SELECT 
    hr.patient_id,
    p.name AS patient_name,
    hr.device_id,
    d.device_name,
    hr.timestamp,
    hr.heart_rate,
    hr.spo2,
    hr.temperature,
    hr.systolic_bp,
    hr.diastolic_bp,
    hr.mean_arterial_pressure,
    hr.data_quality
FROM health_records hr
INNER JOIN patients p ON hr.patient_id = p.patient_id
INNER JOIN devices d ON hr.device_id = d.device_id
WHERE hr.id IN (
    SELECT MAX(id) 
    FROM health_records 
    GROUP BY patient_id
);

-- View: Active alerts summary
CREATE OR REPLACE VIEW v_active_alerts AS
SELECT 
    a.id,
    a.patient_id,
    p.name AS patient_name,
    a.device_id,
    d.device_name,
    a.severity,
    a.message,
    a.vital_sign,
    a.current_value,
    a.timestamp,
    a.acknowledged
FROM alerts a
INNER JOIN patients p ON a.patient_id = p.patient_id
INNER JOIN devices d ON a.device_id = d.device_id
WHERE a.resolved = 0
ORDER BY a.severity DESC, a.timestamp DESC;

-- View: Device status
CREATE OR REPLACE VIEW v_device_status AS
SELECT 
    d.device_id,
    d.device_name,
    d.location,
    d.last_seen,
    d.is_active,
    COUNT(DISTINCT p.patient_id) AS patient_count,
    COUNT(hr.id) AS total_records,
    MAX(hr.timestamp) AS last_measurement
FROM devices d
LEFT JOIN patients p ON d.device_id = p.device_id
LEFT JOIN health_records hr ON d.device_id = hr.device_id
GROUP BY d.device_id, d.device_name, d.location, d.last_seen, d.is_active;

-- ============================================================================
-- INITIAL DATA
-- ============================================================================

-- Note: Initial data will be created when first device connects
-- Each Raspberry Pi will auto-register itself in devices table

-- ============================================================================
-- STORED PROCEDURES (Optional - for advanced operations)
-- ============================================================================

DELIMITER //

-- Procedure: Clean up old records (maintenance)
CREATE PROCEDURE IF NOT EXISTS sp_cleanup_old_records(IN days_to_keep INT)
BEGIN
    DECLARE rows_deleted INT DEFAULT 0;
    
    -- Delete old health records (keep last N days)
    DELETE FROM health_records 
    WHERE timestamp < DATE_SUB(NOW(), INTERVAL days_to_keep DAY);
    
    SET rows_deleted = ROW_COUNT();
    
    -- Delete old system logs
    DELETE FROM system_logs 
    WHERE timestamp < DATE_SUB(NOW(), INTERVAL days_to_keep DAY);
    
    -- Delete successful sync queue entries older than 7 days
    DELETE FROM sync_queue 
    WHERE sync_status = 'success' 
    AND created_at < DATE_SUB(NOW(), INTERVAL 7 DAY);
    
    SELECT CONCAT('Cleanup completed. Deleted ', rows_deleted, ' health records.') AS result;
END //

-- Procedure: Get patient statistics
CREATE PROCEDURE IF NOT EXISTS sp_patient_statistics(IN p_patient_id VARCHAR(50))
BEGIN
    SELECT 
        COUNT(*) AS total_records,
        MIN(timestamp) AS first_record,
        MAX(timestamp) AS last_record,
        AVG(heart_rate) AS avg_heart_rate,
        AVG(spo2) AS avg_spo2,
        AVG(temperature) AS avg_temperature,
        AVG(systolic_bp) AS avg_systolic,
        AVG(diastolic_bp) AS avg_diastolic
    FROM health_records
    WHERE patient_id = p_patient_id;
    
    SELECT 
        severity,
        COUNT(*) AS alert_count
    FROM alerts
    WHERE patient_id = p_patient_id
    AND resolved = 0
    GROUP BY severity;
END //

DELIMITER ;

-- ============================================================================
-- GRANTS AND PERMISSIONS
-- ============================================================================

-- Create sync user (execute this separately with strong password)
-- CREATE USER 'iot_sync_user'@'%' IDENTIFIED BY 'YourStrongPasswordHere';
-- GRANT SELECT, INSERT, UPDATE ON iot_health_cloud.* TO 'iot_sync_user'@'%';
-- GRANT EXECUTE ON PROCEDURE iot_health_cloud.sp_cleanup_old_records TO 'iot_sync_user'@'%';
-- GRANT EXECUTE ON PROCEDURE iot_health_cloud.sp_patient_statistics TO 'iot_sync_user'@'%';
-- FLUSH PRIVILEGES;

-- ============================================================================
-- INDEXES OPTIMIZATION (after initial data load)
-- ============================================================================

-- These indexes will be created automatically, but can be rebuilt for optimization:
-- OPTIMIZE TABLE health_records;
-- OPTIMIZE TABLE alerts;
-- OPTIMIZE TABLE system_logs;

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================

SELECT 'MySQL Cloud Database Schema created successfully!' AS status;
