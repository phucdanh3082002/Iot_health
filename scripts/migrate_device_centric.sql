-- ============================================================
-- MIGRATION: Device-Centric Approach
-- Allow patient_id to be NULL in health_records and alerts
-- Pi chỉ cần biết device_id, patient_id tự động resolve từ patients table
-- ============================================================

USE iot_health_cloud;

-- 1. Modify health_records table: Allow patient_id = NULL
ALTER TABLE health_records
MODIFY COLUMN patient_id VARCHAR(50) DEFAULT NULL COMMENT 'Patient identifier (NULL if device not assigned to patient)';

-- 2. Modify alerts table: Allow patient_id = NULL
ALTER TABLE alerts
MODIFY COLUMN patient_id VARCHAR(50) DEFAULT NULL COMMENT 'Patient identifier (NULL if device not assigned to patient)';

-- 3. Drop foreign key constraints (chỉ alerts table có constraint)
-- Health_records có thể chưa có foreign key hoặc đã được modify trước đó

-- Drop alerts foreign key
SET @constraint_name_alerts = (
    SELECT CONSTRAINT_NAME
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
    WHERE TABLE_NAME = 'alerts'
      AND COLUMN_NAME = 'patient_id'
      AND REFERENCED_TABLE_NAME = 'patients'
    LIMIT 1
);

-- Chỉ drop nếu constraint tồn tại
SET @sql_alerts = IF(@constraint_name_alerts IS NOT NULL,
    CONCAT('ALTER TABLE alerts DROP FOREIGN KEY ', @constraint_name_alerts),
    'SELECT "No alerts constraint to drop" as message'
);
PREPARE stmt_alerts FROM @sql_alerts;
EXECUTE stmt_alerts;
DEALLOCATE PREPARE stmt_alerts;

-- 4. Recreate foreign keys với ON DELETE SET NULL (khi xóa patient, data vẫn giữ với device_id)
-- Note: Health_records có partitioning nên không thể có foreign key
-- Chỉ tạo foreign key cho alerts table

-- Health_records: Không tạo foreign key vì có partitioning
-- Alerts: Tạo foreign key với ON DELETE SET NULL
ALTER TABLE alerts
ADD CONSTRAINT fk_alerts_patient
FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
ON DELETE SET NULL
ON UPDATE CASCADE;

-- 5. Create index for device-centric queries (optimize query by device_id)
-- Note: Index đã tồn tại từ schema gốc
-- CREATE INDEX idx_device_timestamp ON health_records(device_id, timestamp DESC);
-- CREATE INDEX idx_device_timestamp_alerts ON alerts(device_id, timestamp DESC);

-- 6. Create stored procedure to auto-link patient_id for orphan records
DELIMITER $$

CREATE PROCEDURE IF NOT EXISTS sp_link_patient_to_records()
BEGIN
    -- Note: Health_records không có foreign key vì partitioning
    -- Chỉ link alerts với patient_id từ patients table
    UPDATE alerts a
    JOIN patients p ON a.device_id = p.device_id AND p.is_active = 1
    SET a.patient_id = p.patient_id
    WHERE a.patient_id IS NULL;
    
    SELECT 
        (SELECT COUNT(*) FROM alerts WHERE patient_id IS NULL) as orphan_alerts;
END$$

DELIMITER ;

-- 7. Run auto-link procedure
CALL sp_link_patient_to_records();

-- ============================================================
-- VERIFICATION QUERIES
-- ============================================================

-- Check NULL patient_id records
SELECT 
    'health_records' as table_name,
    COUNT(*) as null_patient_count,
    COUNT(DISTINCT device_id) as affected_devices
FROM health_records
WHERE patient_id IS NULL

UNION ALL

SELECT 
    'alerts' as table_name,
    COUNT(*) as null_patient_count,
    COUNT(DISTINCT device_id) as affected_devices
FROM alerts
WHERE patient_id IS NULL;

-- Check device → patient mapping
SELECT 
    d.device_id,
    d.device_name,
    p.patient_id,
    p.name as patient_name,
    COUNT(hr.id) as total_records
FROM devices d
LEFT JOIN patients p ON d.device_id = p.device_id AND p.is_active = 1
LEFT JOIN health_records hr ON d.device_id = hr.device_id
GROUP BY d.device_id, p.patient_id
ORDER BY d.device_id;

-- ============================================================
-- ROLLBACK SCRIPT (nếu cần revert)
-- ============================================================
/*
ALTER TABLE health_records
MODIFY COLUMN patient_id VARCHAR(50) NOT NULL COMMENT 'Patient identifier';

ALTER TABLE alerts
MODIFY COLUMN patient_id VARCHAR(50) NOT NULL COMMENT 'Patient identifier';

DROP INDEX idx_device_timestamp ON health_records;
DROP INDEX idx_device_timestamp_alerts ON alerts;

DROP PROCEDURE IF EXISTS sp_link_patient_to_records;
*/
