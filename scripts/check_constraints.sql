-- Check foreign key constraint names before migration
USE iot_health_cloud;

SELECT
    TABLE_NAME,
    COLUMN_NAME,
    CONSTRAINT_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE TABLE_NAME IN ('health_records', 'alerts')
  AND COLUMN_NAME = 'patient_id'
  AND REFERENCED_TABLE_NAME = 'patients';