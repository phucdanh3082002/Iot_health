-- ============================================================
-- IoT Health Monitor - MySQL Cloud Database Schema
-- Version: 2.0.0 (Restructured & Optimized)
-- Date: 2025-11-20
-- Engine: MySQL 8.0+ with InnoDB
-- Charset: utf8mb4_unicode_ci
-- ============================================================

-- Drop existing tables if recreating (CAUTION: Use only for clean setup)
-- SET FOREIGN_KEY_CHECKS = 0;
-- DROP TABLE IF EXISTS device_ownership, sensor_calibrations, patient_thresholds, alerts, health_records, patients, devices, sync_queue, system_logs;
-- SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
-- 1. DEVICES TABLE (Master device registry)
-- ============================================================
CREATE TABLE IF NOT EXISTS devices (
    -- Primary identification
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Auto-increment primary key',
    device_id VARCHAR(50) NOT NULL UNIQUE COMMENT 'Unique device identifier (e.g., rpi_bp_001)',
    device_name VARCHAR(100) NOT NULL COMMENT 'Human-readable device name',
    device_type VARCHAR(50) DEFAULT 'blood_pressure_monitor' COMMENT 'Device type (bp_monitor, vitals_monitor, etc.)',
    
    -- Location & Network
    location VARCHAR(200) DEFAULT NULL COMMENT 'Physical location of device',
    ip_address VARCHAR(45) DEFAULT NULL COMMENT 'Current IP address (IPv4/IPv6)',
    
    -- Software & Firmware
    firmware_version VARCHAR(20) DEFAULT NULL COMMENT 'Firmware version',
    os_version VARCHAR(50) DEFAULT NULL COMMENT 'Operating system version',
    
    -- Status & Connection
    is_active BOOLEAN DEFAULT TRUE COMMENT 'Device active status',
    last_seen DATETIME DEFAULT NULL COMMENT 'Last heartbeat/connection timestamp',
    
    -- Pairing & QR Code
    pairing_code VARCHAR(32) DEFAULT NULL UNIQUE COMMENT 'Temporary pairing code for QR',
    pairing_qr_data TEXT DEFAULT NULL COMMENT 'QR code data (JSON)',
    paired_by VARCHAR(100) DEFAULT NULL COMMENT 'User ID who paired device',
    paired_at DATETIME DEFAULT NULL COMMENT 'Pairing timestamp',
    
    -- Timestamps
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'Device creation timestamp',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update timestamp',
    
    -- Indexes
    INDEX idx_device_id (device_id),
    INDEX idx_is_active (is_active),
    INDEX idx_last_seen (last_seen),
    INDEX idx_pairing_code (pairing_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Device registry for IoT health monitors';

-- ============================================================
-- 2. DEVICE_OWNERSHIP TABLE (Multi-user device access control)
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
-- 3. PATIENTS TABLE (Patient information)
-- ============================================================
CREATE TABLE IF NOT EXISTS patients (
    -- Primary identification
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Auto-increment primary key',
    patient_id VARCHAR(50) NOT NULL UNIQUE COMMENT 'Unique patient identifier',
    device_id VARCHAR(50) DEFAULT NULL COMMENT 'Associated device (nullable for flexibility)',
    
    -- Personal information
    name VARCHAR(100) NOT NULL COMMENT 'Patient full name',
    age INT DEFAULT NULL COMMENT 'Patient age',
    gender ENUM('M', 'F', 'O') DEFAULT NULL COMMENT 'Patient gender (M/F/O)',
    
    -- Medical information
    medical_conditions JSON DEFAULT NULL COMMENT 'List of medical conditions',
    emergency_contact JSON DEFAULT NULL COMMENT 'Emergency contact info {name, phone, relationship}',
    
    -- Status & Timestamps
    is_active BOOLEAN DEFAULT TRUE COMMENT 'Patient active status',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation timestamp',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update timestamp',
    
    -- Foreign keys
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE SET NULL ON UPDATE CASCADE,
    
    -- Indexes
    INDEX idx_patient_id (patient_id),
    INDEX idx_device_id (device_id),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Patient information registry';

-- ============================================================
-- 4. HEALTH_RECORDS TABLE (Vital signs measurements)
-- Partitioned by RANGE on timestamp for performance
-- ============================================================
CREATE TABLE IF NOT EXISTS health_records (
    -- Primary identification
    id BIGINT AUTO_INCREMENT COMMENT 'Auto-increment primary key',
    patient_id VARCHAR(50) NOT NULL COMMENT 'Patient identifier',
    device_id VARCHAR(50) NOT NULL COMMENT 'Device that recorded measurement',
    timestamp DATETIME NOT NULL COMMENT 'Measurement timestamp',
    
    -- Vital signs
    heart_rate FLOAT DEFAULT NULL COMMENT 'Heart rate (BPM)',
    spo2 FLOAT DEFAULT NULL COMMENT 'SpO2 saturation (%)',
    temperature FLOAT DEFAULT NULL COMMENT 'Body temperature (Celsius)',
    systolic_bp FLOAT DEFAULT NULL COMMENT 'Systolic blood pressure (mmHg)',
    diastolic_bp FLOAT DEFAULT NULL COMMENT 'Diastolic blood pressure (mmHg)',
    mean_arterial_pressure FLOAT DEFAULT NULL COMMENT 'Mean arterial pressure (mmHg)',
    
    -- Metadata
    sensor_data JSON DEFAULT NULL COMMENT 'Raw sensor data and metadata',
    data_quality FLOAT DEFAULT 1.0 COMMENT 'Data quality score (0-1)',
    measurement_context VARCHAR(50) DEFAULT 'rest' COMMENT 'Context: rest, activity, sleep, etc.',
    
    -- Sync status
    sync_status ENUM('pending', 'synced', 'failed') DEFAULT 'synced' COMMENT 'Cloud sync status',
    synced_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'When record was synced',
    
    -- Primary key (composite with timestamp for partitioning)
    PRIMARY KEY (id, timestamp),
    
    -- Foreign keys
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE ON UPDATE CASCADE,
    
    -- Indexes
    INDEX idx_patient_timestamp (patient_id, timestamp DESC),
    INDEX idx_device_timestamp (device_id, timestamp DESC),
    INDEX idx_sync_status (sync_status),
    INDEX idx_data_quality (data_quality)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Health vital signs measurements'
PARTITION BY RANGE (YEAR(timestamp)) (
    PARTITION p2024 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION p2026 VALUES LESS THAN (2027),
    PARTITION p2027 VALUES LESS THAN (2028),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);

-- ============================================================
-- 5. ALERTS TABLE (Alert events and notifications)
-- ============================================================
CREATE TABLE IF NOT EXISTS alerts (
    -- Primary identification
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT 'Auto-increment primary key',
    patient_id VARCHAR(50) NOT NULL COMMENT 'Patient identifier',
    device_id VARCHAR(50) NOT NULL COMMENT 'Device that generated alert',
    health_record_id BIGINT DEFAULT NULL COMMENT 'Associated health record ID (optional)',
    
    -- Alert information
    alert_type VARCHAR(50) NOT NULL COMMENT 'Alert type: threshold, anomaly, critical',
    severity ENUM('low', 'medium', 'high', 'critical') NOT NULL COMMENT 'Alert severity level',
    vital_sign VARCHAR(50) DEFAULT NULL COMMENT 'Affected vital: heart_rate, spo2, temperature, bp',
    message TEXT NOT NULL COMMENT 'Alert message',
    
    -- Threshold values
    current_value FLOAT DEFAULT NULL COMMENT 'Current value that triggered alert',
    threshold_value FLOAT DEFAULT NULL COMMENT 'Threshold value exceeded',
    
    -- Timestamps
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Alert generation time',
    
    -- Acknowledgment
    acknowledged BOOLEAN DEFAULT FALSE COMMENT 'Whether alert was acknowledged',
    acknowledged_at DATETIME DEFAULT NULL COMMENT 'Acknowledgment timestamp',
    acknowledged_by VARCHAR(100) DEFAULT NULL COMMENT 'User who acknowledged',
    
    -- Resolution
    resolved BOOLEAN DEFAULT FALSE COMMENT 'Whether alert was resolved',
    resolved_at DATETIME DEFAULT NULL COMMENT 'Resolution timestamp',
    
    -- Notification
    notification_sent BOOLEAN DEFAULT FALSE COMMENT 'Whether notification was sent',
    notification_method VARCHAR(50) DEFAULT NULL COMMENT 'Notification method: mqtt, fcm, email',
    
    -- Foreign keys
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE ON UPDATE CASCADE,
    
    -- Indexes
    INDEX idx_patient_id (patient_id),
    INDEX idx_device_id (device_id),
    INDEX idx_timestamp (timestamp DESC),
    INDEX idx_severity (severity),
    INDEX idx_resolved (resolved),
    INDEX idx_acknowledged (acknowledged)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Alert events and notifications';

-- ============================================================
-- 6. PATIENT_THRESHOLDS TABLE (Patient-specific alert thresholds)
-- ============================================================
CREATE TABLE IF NOT EXISTS patient_thresholds (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Auto-increment primary key',
    patient_id VARCHAR(50) NOT NULL COMMENT 'Patient identifier',
    vital_sign VARCHAR(50) NOT NULL COMMENT 'Vital sign name',
    
    -- Normal range
    min_normal FLOAT DEFAULT NULL COMMENT 'Minimum normal value',
    max_normal FLOAT DEFAULT NULL COMMENT 'Maximum normal value',
    
    -- Critical range
    min_critical FLOAT DEFAULT NULL COMMENT 'Minimum critical value (emergency)',
    max_critical FLOAT DEFAULT NULL COMMENT 'Maximum critical value (emergency)',
    
    -- Status & Timestamps
    is_active BOOLEAN DEFAULT TRUE COMMENT 'Whether threshold is active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation timestamp',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update timestamp',
    
    -- Foreign keys
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE ON UPDATE CASCADE,
    
    -- Constraints
    UNIQUE KEY unique_patient_vital (patient_id, vital_sign, is_active),
    INDEX idx_patient_id (patient_id),
    INDEX idx_vital_sign (vital_sign),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Patient-specific alert thresholds';

-- ============================================================
-- 7. SENSOR_CALIBRATIONS TABLE (Sensor calibration data)
-- ============================================================
CREATE TABLE IF NOT EXISTS sensor_calibrations (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Auto-increment primary key',
    device_id VARCHAR(50) NOT NULL COMMENT 'Device identifier',
    sensor_name VARCHAR(50) NOT NULL COMMENT 'Sensor name: HX710B, MAX30102, MLX90614',
    
    -- Calibration data
    calibration_type VARCHAR(50) NOT NULL COMMENT 'Calibration type: two_point, linear, polynomial',
    reference_values JSON DEFAULT NULL COMMENT 'Reference values used',
    measured_values JSON DEFAULT NULL COMMENT 'Measured values obtained',
    calibration_factors JSON NOT NULL COMMENT 'Calibration factors (offset, slope, etc.)',
    
    -- Metadata
    calibrated_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'Calibration timestamp',
    is_active BOOLEAN DEFAULT TRUE COMMENT 'Whether calibration is active',
    notes TEXT DEFAULT NULL COMMENT 'Additional notes',
    
    -- Foreign keys
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE ON UPDATE CASCADE,
    
    -- Indexes
    INDEX idx_device_sensor (device_id, sensor_name),
    INDEX idx_is_active (is_active),
    INDEX idx_calibrated_at (calibrated_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Sensor calibration data';

-- ============================================================
-- 8. SYNC_QUEUE TABLE (Store & Forward queue for offline sync)
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
-- 9. SYSTEM_LOGS TABLE (System event logs)
-- Partitioned by timestamp for performance
-- ============================================================
CREATE TABLE IF NOT EXISTS system_logs (
    id BIGINT AUTO_INCREMENT COMMENT 'Auto-increment primary key',
    device_id VARCHAR(50) DEFAULT NULL COMMENT 'Device identifier (nullable for system-wide logs)',
    
    -- Log details
    level ENUM('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL') NOT NULL COMMENT 'Log level',
    message TEXT NOT NULL COMMENT 'Log message',
    module VARCHAR(100) DEFAULT NULL COMMENT 'Source module',
    function_name VARCHAR(100) DEFAULT NULL COMMENT 'Source function',
    line_number INT DEFAULT NULL COMMENT 'Source line number',
    
    -- Timestamp
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Log timestamp',
    
    -- Additional data
    additional_data JSON DEFAULT NULL COMMENT 'Additional structured data',
    
    -- Primary key (composite for partitioning)
    PRIMARY KEY (id, timestamp),
    
    -- Foreign keys (with NULL allowed)
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE SET NULL ON UPDATE CASCADE,
    
    -- Indexes
    INDEX idx_device_timestamp (device_id, timestamp DESC),
    INDEX idx_level (level),
    INDEX idx_timestamp (timestamp DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='System event logs'
PARTITION BY RANGE (YEAR(timestamp)) (
    PARTITION p2024 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION p2026 VALUES LESS THAN (2027),
    PARTITION p2027 VALUES LESS THAN (2028),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);

-- ============================================================
-- ANALYTICAL VIEWS
-- ============================================================

-- View 1: Latest vitals per patient
CREATE OR REPLACE VIEW v_latest_vitals AS
SELECT 
    p.patient_id,
    p.name AS patient_name,
    d.device_id,
    d.device_name,
    hr.timestamp,
    hr.heart_rate,
    hr.spo2,
    hr.temperature,
    hr.systolic_bp,
    hr.diastolic_bp,
    hr.mean_arterial_pressure,
    hr.data_quality
FROM patients p
LEFT JOIN devices d ON p.device_id = d.device_id
LEFT JOIN health_records hr ON p.patient_id = hr.patient_id
WHERE hr.id = (
    SELECT id FROM health_records 
    WHERE patient_id = p.patient_id 
    ORDER BY timestamp DESC 
    LIMIT 1
);

-- View 2: Active alerts
CREATE OR REPLACE VIEW v_active_alerts AS
SELECT 
    a.id,
    a.patient_id,
    p.name AS patient_name,
    a.device_id,
    d.device_name,
    a.severity,
    a.vital_sign,
    a.message,
    a.current_value,
    a.timestamp,
    a.acknowledged
FROM alerts a
JOIN patients p ON a.patient_id = p.patient_id
JOIN devices d ON a.device_id = d.device_id
WHERE a.resolved = FALSE
ORDER BY a.severity DESC, a.timestamp DESC;

-- View 3: Device health status
CREATE OR REPLACE VIEW v_device_health AS
SELECT 
    d.device_id,
    d.device_name,
    d.location,
    d.is_active,
    d.last_seen,
    d.ip_address,
    d.firmware_version,
    TIMESTAMPDIFF(MINUTE, d.last_seen, NOW()) AS minutes_since_last_seen,
    CASE 
        WHEN TIMESTAMPDIFF(MINUTE, d.last_seen, NOW()) <= 5 THEN 'online'
        WHEN TIMESTAMPDIFF(MINUTE, d.last_seen, NOW()) <= 30 THEN 'idle'
        ELSE 'offline'
    END AS connection_status,
    (SELECT COUNT(*) FROM health_records WHERE device_id = d.device_id AND DATE(timestamp) = CURDATE()) AS records_today,
    (SELECT COUNT(*) FROM health_records WHERE device_id = d.device_id AND timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)) AS records_24h,
    (SELECT COUNT(*) FROM alerts WHERE device_id = d.device_id AND DATE(timestamp) = CURDATE()) AS alerts_today,
    (SELECT AVG(data_quality) FROM health_records WHERE device_id = d.device_id AND timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)) AS avg_data_quality,
    d.created_at,
    d.updated_at
FROM devices d;

-- View 4: Patient vitals trend (daily aggregates)
CREATE OR REPLACE VIEW v_patient_vitals_trend AS
SELECT 
    patient_id,
    DATE(timestamp) AS trend_date,
    COUNT(*) AS measurement_count,
    AVG(heart_rate) AS avg_heart_rate,
    MIN(heart_rate) AS min_heart_rate,
    MAX(heart_rate) AS max_heart_rate,
    STDDEV(heart_rate) AS stddev_heart_rate,
    AVG(spo2) AS avg_spo2,
    MIN(spo2) AS min_spo2,
    MAX(spo2) AS max_spo2,
    AVG(temperature) AS avg_temperature,
    MIN(temperature) AS min_temperature,
    MAX(temperature) AS max_temperature,
    AVG(systolic_bp) AS avg_systolic,
    AVG(diastolic_bp) AS avg_diastolic,
    AVG(mean_arterial_pressure) AS avg_map,
    SUM(CASE WHEN heart_rate IS NOT NULL THEN 1 ELSE 0 END) AS has_heart_rate,
    SUM(CASE WHEN spo2 IS NOT NULL THEN 1 ELSE 0 END) AS has_spo2,
    SUM(CASE WHEN temperature IS NOT NULL THEN 1 ELSE 0 END) AS has_temperature,
    SUM(CASE WHEN systolic_bp IS NOT NULL THEN 1 ELSE 0 END) AS has_blood_pressure,
    MIN(timestamp) AS first_measurement,
    MAX(timestamp) AS last_measurement,
    (SELECT COUNT(*) FROM alerts WHERE alerts.patient_id = health_records.patient_id AND DATE(alerts.timestamp) = DATE(health_records.timestamp) AND severity = 'critical') AS critical_alerts
FROM health_records
GROUP BY patient_id, DATE(timestamp);

-- View 5: Alert summary (daily aggregates)
CREATE OR REPLACE VIEW v_alert_summary AS
SELECT 
    DATE(timestamp) AS alert_date,
    device_id,
    vital_sign,
    severity,
    COUNT(*) AS total_alerts,
    SUM(CASE WHEN acknowledged = FALSE THEN 1 ELSE 0 END) AS unacknowledged,
    SUM(CASE WHEN resolved = FALSE THEN 1 ELSE 0 END) AS unresolved,
    SUM(CASE WHEN notification_sent = TRUE THEN 1 ELSE 0 END) AS notifications_sent,
    AVG(TIMESTAMPDIFF(MINUTE, timestamp, acknowledged_at)) AS avg_response_minutes,
    MAX(TIMESTAMPDIFF(MINUTE, timestamp, acknowledged_at)) AS max_response_minutes,
    AVG(TIMESTAMPDIFF(MINUTE, timestamp, resolved_at)) AS avg_resolution_minutes,
    AVG(current_value) AS avg_value,
    MIN(current_value) AS min_value,
    MAX(current_value) AS max_value,
    MIN(timestamp) AS first_alert,
    MAX(timestamp) AS last_alert
FROM alerts
GROUP BY DATE(timestamp), device_id, vital_sign, severity;

-- View 6: Sync queue status
CREATE OR REPLACE VIEW v_sync_queue_status AS
SELECT 
    device_id,
    sync_status,
    table_name,
    COUNT(*) AS queue_count,
    MAX(TIMESTAMPDIFF(MINUTE, created_at, NOW())) AS max_age_minutes,
    AVG(TIMESTAMPDIFF(MINUTE, created_at, NOW())) AS avg_age_minutes,
    AVG(sync_attempts) AS avg_attempts,
    MAX(sync_attempts) AS max_attempts,
    MIN(created_at) AS oldest_entry,
    MAX(last_sync_attempt) AS last_attempt,
    COUNT(DISTINCT error_message) AS unique_errors
FROM sync_queue
GROUP BY device_id, sync_status, table_name;

-- View 7: Data quality metrics
CREATE OR REPLACE VIEW v_data_quality AS
SELECT 
    device_id,
    DATE(timestamp) AS measurement_date,
    COUNT(*) AS total_measurements,
    AVG(data_quality) AS avg_quality,
    MIN(data_quality) AS min_quality,
    MAX(data_quality) AS max_quality,
    SUM(CASE WHEN data_quality >= 0.9 THEN 1 ELSE 0 END) AS excellent_count,
    SUM(CASE WHEN data_quality >= 0.7 AND data_quality < 0.9 THEN 1 ELSE 0 END) AS good_count,
    SUM(CASE WHEN data_quality >= 0.5 AND data_quality < 0.7 THEN 1 ELSE 0 END) AS fair_count,
    SUM(CASE WHEN data_quality < 0.5 THEN 1 ELSE 0 END) AS poor_count,
    SUM(CASE WHEN heart_rate IS NULL THEN 1 ELSE 0 END) AS missing_heart_rate,
    SUM(CASE WHEN spo2 IS NULL THEN 1 ELSE 0 END) AS missing_spo2,
    SUM(CASE WHEN temperature IS NULL THEN 1 ELSE 0 END) AS missing_temperature,
    SUM(CASE WHEN systolic_bp IS NULL OR diastolic_bp IS NULL THEN 1 ELSE 0 END) AS missing_bp,
    (COUNT(*) - SUM(CASE WHEN heart_rate IS NULL THEN 1 ELSE 0 END)) * 100.0 / COUNT(*) AS completeness_pct,
    AVG(heart_rate) AS avg_heart_rate,
    AVG(spo2) AS avg_spo2,
    AVG(temperature) AS avg_temperature,
    AVG(systolic_bp) AS avg_systolic_bp
FROM health_records
GROUP BY device_id, DATE(timestamp);

-- View 8: System status overview
CREATE OR REPLACE VIEW v_system_status AS
SELECT 
    'total_devices' AS metric_category,
    'count' AS metric_name,
    COUNT(*) AS metric_value,
    'devices' AS metric_unit
FROM devices
UNION ALL
SELECT 
    'active_devices' AS metric_category,
    'count' AS metric_name,
    COUNT(*) AS metric_value,
    'devices' AS metric_unit
FROM devices WHERE is_active = TRUE
UNION ALL
SELECT 
    'total_patients' AS metric_category,
    'count' AS metric_name,
    COUNT(*) AS metric_value,
    'patients' AS metric_unit
FROM patients
UNION ALL
SELECT 
    'total_health_records' AS metric_category,
    'count' AS metric_name,
    COUNT(*) AS metric_value,
    'records' AS metric_unit
FROM health_records
UNION ALL
SELECT 
    'active_alerts' AS metric_category,
    'count' AS metric_name,
    COUNT(*) AS metric_value,
    'alerts' AS metric_unit
FROM alerts WHERE resolved = FALSE
UNION ALL
SELECT 
    'pending_sync_items' AS metric_category,
    'count' AS metric_name,
    COUNT(*) AS metric_value,
    'items' AS metric_unit
FROM sync_queue WHERE sync_status = 'pending';

-- View 9: Daily summary statistics
CREATE OR REPLACE VIEW v_daily_summary AS
SELECT 
    CURDATE() AS summary_date,
    (SELECT COUNT(DISTINCT device_id) FROM health_records WHERE DATE(timestamp) = CURDATE()) AS active_devices,
    (SELECT COUNT(DISTINCT patient_id) FROM health_records WHERE DATE(timestamp) = CURDATE()) AS unique_patients,
    (SELECT COUNT(*) FROM health_records WHERE DATE(timestamp) = CURDATE()) AS total_records,
    (SELECT COUNT(*) FROM health_records WHERE DATE(timestamp) = CURDATE() AND sync_status = 'synced') AS synced_records,
    (SELECT COUNT(*) * 100.0 / NULLIF((SELECT COUNT(*) FROM health_records WHERE DATE(timestamp) = CURDATE()), 0)) AS sync_success_rate,
    (SELECT AVG(data_quality) FROM health_records WHERE DATE(timestamp) = CURDATE()) AS avg_data_quality,
    (SELECT COUNT(*) FROM health_records WHERE DATE(timestamp) = CURDATE() AND data_quality < 0.5) AS low_quality_count,
    (SELECT COUNT(*) FROM alerts WHERE DATE(timestamp) = CURDATE()) AS total_alerts,
    (SELECT COUNT(*) FROM alerts WHERE DATE(timestamp) = CURDATE() AND severity = 'critical') AS critical_alerts,
    (SELECT COUNT(*) FROM system_logs WHERE DATE(timestamp) = CURDATE() AND level IN ('ERROR', 'CRITICAL')) AS error_count;

-- View 10: Hourly activity patterns
CREATE OR REPLACE VIEW v_hourly_activity AS
SELECT 
    device_id,
    DATE(timestamp) AS activity_date,
    HOUR(timestamp) AS activity_hour,
    COUNT(*) AS record_count,
    COUNT(DISTINCT CASE WHEN heart_rate IS NOT NULL THEN 'heart_rate' END) +
    COUNT(DISTINCT CASE WHEN spo2 IS NOT NULL THEN 'spo2' END) +
    COUNT(DISTINCT CASE WHEN temperature IS NOT NULL THEN 'temperature' END) +
    COUNT(DISTINCT CASE WHEN systolic_bp IS NOT NULL THEN 'bp' END) AS vital_types_collected,
    AVG(data_quality) AS avg_quality,
    (SELECT COUNT(*) FROM alerts WHERE alerts.device_id = health_records.device_id AND DATE(alerts.timestamp) = DATE(health_records.timestamp) AND HOUR(alerts.timestamp) = HOUR(health_records.timestamp)) AS alerts_count
FROM health_records
GROUP BY device_id, DATE(timestamp), HOUR(timestamp);

-- View 11: Sync performance metrics
CREATE OR REPLACE VIEW v_sync_performance AS
SELECT 
    device_id,
    DATE(synced_at) AS sync_date,
    HOUR(synced_at) AS sync_hour,
    COUNT(*) AS total_records,
    SUM(CASE WHEN sync_status = 'synced' THEN 1 ELSE 0 END) AS synced_count,
    SUM(CASE WHEN sync_status = 'pending' THEN 1 ELSE 0 END) AS pending_count,
    SUM(CASE WHEN sync_status = 'failed' THEN 1 ELSE 0 END) AS conflict_count,
    (SUM(CASE WHEN sync_status = 'synced' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)) AS success_rate_pct,
    AVG(data_quality) AS avg_quality,
    MIN(data_quality) AS min_quality,
    MAX(data_quality) AS max_quality,
    SUM(CASE WHEN heart_rate IS NOT NULL THEN 1 ELSE 0 END) AS has_heart_rate,
    SUM(CASE WHEN spo2 IS NOT NULL THEN 1 ELSE 0 END) AS has_spo2,
    SUM(CASE WHEN temperature IS NOT NULL THEN 1 ELSE 0 END) AS has_temperature,
    SUM(CASE WHEN systolic_bp IS NOT NULL THEN 1 ELSE 0 END) AS has_blood_pressure,
    MIN(timestamp) AS first_record_time,
    MAX(timestamp) AS last_record_time
FROM health_records
WHERE synced_at IS NOT NULL
GROUP BY device_id, DATE(synced_at), HOUR(synced_at);

-- View 12: Device status summary
CREATE OR REPLACE VIEW v_device_status AS
SELECT 
    d.device_id,
    d.device_name,
    d.location,
    d.is_active,
    d.last_seen,
    COUNT(DISTINCT p.patient_id) AS patient_count,
    (SELECT COUNT(*) FROM health_records WHERE device_id = d.device_id) AS total_records,
    (SELECT MAX(timestamp) FROM health_records WHERE device_id = d.device_id) AS last_measurement
FROM devices d
LEFT JOIN patients p ON d.device_id = p.device_id
GROUP BY d.device_id, d.device_name, d.location, d.is_active, d.last_seen;

-- View 13: Error dashboard
CREATE OR REPLACE VIEW v_error_dashboard AS
SELECT 
    DATE(timestamp) AS error_date,
    HOUR(timestamp) AS error_hour,
    device_id,
    level,
    module,
    COUNT(*) AS error_count,
    COUNT(DISTINCT message) AS unique_errors,
    GROUP_CONCAT(DISTINCT SUBSTRING(message, 1, 100) ORDER BY timestamp DESC SEPARATOR ' | ') AS sample_messages,
    MIN(timestamp) AS first_occurrence,
    MAX(timestamp) AS last_occurrence
FROM system_logs
WHERE level IN ('ERROR', 'CRITICAL')
GROUP BY DATE(timestamp), HOUR(timestamp), device_id, level, module;

-- ============================================================
-- STORED PROCEDURES
-- ============================================================

-- Procedure 1: Cleanup old records (data retention)
DELIMITER //
CREATE PROCEDURE IF NOT EXISTS sp_cleanup_old_records(IN days_to_keep INT)
BEGIN
    DECLARE cutoff_date DATETIME;
    DECLARE deleted_health_records INT DEFAULT 0;
    DECLARE deleted_alerts INT DEFAULT 0;
    DECLARE deleted_logs INT DEFAULT 0;
    
    SET cutoff_date = DATE_SUB(NOW(), INTERVAL days_to_keep DAY);
    
    -- Delete old health records
    DELETE FROM health_records WHERE timestamp < cutoff_date;
    SET deleted_health_records = ROW_COUNT();
    
    -- Delete old resolved alerts
    DELETE FROM alerts WHERE timestamp < cutoff_date AND resolved = TRUE;
    SET deleted_alerts = ROW_COUNT();
    
    -- Delete old system logs
    DELETE FROM system_logs WHERE timestamp < cutoff_date AND level NOT IN ('ERROR', 'CRITICAL');
    SET deleted_logs = ROW_COUNT();
    
    -- Log cleanup summary
    INSERT INTO system_logs (level, message, module, additional_data)
    VALUES (
        'INFO',
        CONCAT('Cleanup completed: ', deleted_health_records, ' health records, ', deleted_alerts, ' alerts, ', deleted_logs, ' logs deleted'),
        'sp_cleanup_old_records',
        JSON_OBJECT('days_to_keep', days_to_keep, 'cutoff_date', cutoff_date, 'deleted_health_records', deleted_health_records, 'deleted_alerts', deleted_alerts, 'deleted_logs', deleted_logs)
    );
    
    SELECT deleted_health_records, deleted_alerts, deleted_logs;
END //
DELIMITER ;

-- Procedure 2: Patient statistics
DELIMITER //
CREATE PROCEDURE IF NOT EXISTS sp_patient_statistics(IN input_patient_id VARCHAR(50))
BEGIN
    SELECT 
        p.patient_id,
        p.name,
        p.age,
        p.gender,
        COUNT(hr.id) AS total_measurements,
        MIN(hr.timestamp) AS first_measurement,
        MAX(hr.timestamp) AS last_measurement,
        AVG(hr.heart_rate) AS avg_heart_rate,
        AVG(hr.spo2) AS avg_spo2,
        AVG(hr.temperature) AS avg_temperature,
        AVG(hr.systolic_bp) AS avg_systolic_bp,
        AVG(hr.diastolic_bp) AS avg_diastolic_bp,
        AVG(hr.data_quality) AS avg_data_quality,
        (SELECT COUNT(*) FROM alerts WHERE patient_id = input_patient_id) AS total_alerts,
        (SELECT COUNT(*) FROM alerts WHERE patient_id = input_patient_id AND severity = 'critical') AS critical_alerts,
        (SELECT COUNT(*) FROM alerts WHERE patient_id = input_patient_id AND resolved = FALSE) AS active_alerts
    FROM patients p
    LEFT JOIN health_records hr ON p.patient_id = hr.patient_id
    WHERE p.patient_id = input_patient_id
    GROUP BY p.patient_id, p.name, p.age, p.gender;
END //
DELIMITER ;

-- ============================================================
-- INITIAL DATA / DEFAULT THRESHOLDS
-- ============================================================

-- Insert default thresholds for common vital signs (will be copied per patient)
-- These serve as templates; actual thresholds are in patient_thresholds table

-- ============================================================
-- COMPLETION MESSAGE
-- ============================================================
SELECT '✅ MySQL Cloud Database Schema v2.0.0 created successfully!' AS status;
SELECT 'Tables: 9 core tables created' AS info;
SELECT 'Views: 13 analytical views created' AS info;
SELECT 'Procedures: 2 stored procedures created' AS info;
SELECT 'Next steps: Run migration script to transfer existing data' AS info;
