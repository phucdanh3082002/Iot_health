# 🗄️ IoT Health Monitor Database Schema

## 📋 Tổng quan

Hệ thống IoT Health Monitor sử dụng kiến trúc database hai tầng:
- **SQLite Local**: Cơ sở dữ liệu cục bộ trên Raspberry Pi (offline-first)
- **MySQL Cloud**: Cơ sở dữ liệu đám mây trên AWS RDS (sync từ local)

**Version**: 2.0.0 (Restructured & Optimized)  
**Date**: 2025-11-20  
**Engine**: MySQL 8.0+ (Cloud) / SQLite 3+ (Local)

---

## 🏗️ Kiến trúc Database

### **MySQL Cloud Schema (AWS RDS)**
```sql
Database: iot_health_cloud
Engine: InnoDB
Charset: utf8mb4_unicode_ci
Partitioning: health_records (by year), system_logs (by year)
```

### **SQLite Local Schema**
```python
Database: data/health_monitor.db
ORM: SQLAlchemy 2.0+
Dialect: SQLite with JSON support
```

---

## 📊 Cấu trúc Tables

### 1. **devices** - Device Registry
**Mục đích**: Quản lý tất cả thiết bị IoT trong hệ thống

| Column | Type (MySQL) | Type (SQLite) | Nullable | Description |
|--------|-------------|---------------|----------|-------------|
| id | INT AUTO_INCREMENT | Integer (PK, autoincrement) | NO | Primary key |
| device_id | VARCHAR(50) UNIQUE | String(50) UNIQUE | NO | Device identifier (rpi_bp_001) |
| device_name | VARCHAR(100) | String(100) | NO | Human-readable name |
| device_type | VARCHAR(50) | String(50) | YES | Device type (blood_pressure_monitor) |
| location | VARCHAR(200) | String(200) | YES | Physical location |
| ip_address | VARCHAR(45) | String(45) | YES | Current IP address |
| firmware_version | VARCHAR(20) | String(20) | YES | Firmware version |
| os_version | VARCHAR(50) | String(50) | YES | OS version |
| is_active | BOOLEAN | Boolean | YES | Active status |
| last_seen | DATETIME | DateTime | YES | Last heartbeat |
| pairing_code | VARCHAR(32) UNIQUE | String(32) UNIQUE | YES | Temporary pairing code |
| pairing_qr_data | TEXT | Text | YES | QR code data (JSON) |
| paired_by | VARCHAR(100) | String(100) | YES | User who paired |
| paired_at | DATETIME | DateTime | YES | Pairing timestamp |
| created_at | DATETIME | DateTime | YES | Creation timestamp |
| updated_at | DATETIME | DateTime | YES | Update timestamp |

**Indexes**: device_id, is_active, last_seen, pairing_code  
**Relationships**: 1:N với device_ownership, patients, health_records, alerts, calibrations, sync_queue, system_logs

---

### 2. **device_ownership** - Multi-User Access Control
**Mục đích**: Quản lý quyền truy cập thiết bị cho nhiều user

| Column | Type (MySQL) | Type (SQLite) | Nullable | Description |
|--------|-------------|---------------|----------|-------------|
| id | INT AUTO_INCREMENT | Integer (PK, autoincrement) | NO | Primary key |
| user_id | VARCHAR(100) | String(100) | NO | User identifier |
| device_id | VARCHAR(50) FK | String(50) FK | NO | Device identifier |
| role | VARCHAR(20) | Enum(UserRole) | YES | owner/caregiver/viewer |
| nickname | VARCHAR(100) | String(100) | YES | User-defined device name |
| added_at | DATETIME | DateTime | YES | Access granted time |
| last_accessed | DATETIME | DateTime | YES | Last access time |

**Indexes**: user_id, device_id  
**Foreign Keys**: device_id → devices.device_id (CASCADE)

---

### 3. **patients** - Patient Information
**Mục đích**: Thông tin bệnh nhân

| Column | Type (MySQL) | Type (SQLite) | Nullable | Description |
|--------|-------------|---------------|----------|-------------|
| id | INT AUTO_INCREMENT | Integer (PK, autoincrement) | NO | Primary key |
| patient_id | VARCHAR(50) UNIQUE | String(50) UNIQUE | NO | Patient identifier |
| device_id | VARCHAR(50) FK | String(50) FK | YES | Associated device |
| name | VARCHAR(100) | String(100) | NO | Patient name |
| age | INT | Integer | YES | Patient age |
| gender | VARCHAR(1) | String(1) | YES | M/F/O |
| medical_conditions | JSON | JSON | YES | Medical conditions |
| emergency_contact | JSON | JSON | YES | Emergency contact |
| is_active | BOOLEAN | Boolean | YES | Active status |
| created_at | DATETIME | DateTime | YES | Creation timestamp |
| updated_at | DATETIME | DateTime | YES | Update timestamp |

**Indexes**: patient_id, device_id, is_active  
**Foreign Keys**: device_id → devices.device_id (SET NULL)

---

### 4. **health_records** - Vital Signs Measurements
**Mục đích**: Lưu trữ các phép đo dấu hiệu sinh tồn

| Column | Type (MySQL) | Type (SQLite) | Nullable | Description |
|--------|-------------|---------------|----------|-------------|
| id | BIGINT AUTO_INCREMENT | Integer (PK, autoincrement) | NO | Primary key |
| patient_id | VARCHAR(50) FK | String(50) FK | NO | Patient identifier |
| device_id | VARCHAR(50) FK | String(50) FK | NO | Device identifier |
| timestamp | DATETIME | DateTime | NO | Measurement timestamp |
| heart_rate | FLOAT | Float | YES | Heart rate (BPM) |
| spo2 | FLOAT | Float | YES | SpO2 percentage |
| temperature | FLOAT | Float | YES | Body temperature (°C) |
| systolic_bp | FLOAT | Float | YES | Systolic BP (mmHg) |
| diastolic_bp | FLOAT | Float | YES | Diastolic BP (mmHg) |
| mean_arterial_pressure | FLOAT | Float | YES | MAP (mmHg) |
| sensor_data | JSON | JSON | YES | Raw sensor data |
| data_quality | FLOAT | Float | YES | Data quality score (0-1) |
| measurement_context | VARCHAR(50) | String(50) | YES | Context (rest/activity) |
| sync_status | VARCHAR(20) | Enum(SyncStatus) | YES | pending/synced/failed |
| synced_at | DATETIME | DateTime | YES | Sync timestamp |

**Indexes**: patient_id, device_id, timestamp, data_quality, sync_status  
**Foreign Keys**: patient_id → patients.patient_id (CASCADE), device_id → devices.device_id (CASCADE)  
**Partitioning**: MySQL partitioned by YEAR(timestamp)

---

### 5. **alerts** - Alert Events
**Mục đích**: Lưu trữ các cảnh báo và thông báo

| Column | Type (MySQL) | Type (SQLite) | Nullable | Description |
|--------|-------------|---------------|----------|-------------|
| id | BIGINT AUTO_INCREMENT | Integer (PK, autoincrement) | NO | Primary key |
| patient_id | VARCHAR(50) FK | String(50) FK | NO | Patient identifier |
| device_id | VARCHAR(50) FK | String(50) FK | NO | Device identifier |
| health_record_id | BIGINT | Integer | YES | Associated health record |
| alert_type | VARCHAR(50) | String(50) | NO | threshold/anomaly/critical |
| severity | VARCHAR(20) | Enum(AlertSeverity) | NO | low/medium/high/critical |
| vital_sign | VARCHAR(50) | String(50) | YES | Affected vital sign |
| message | TEXT | Text | NO | Alert message |
| current_value | FLOAT | Float | YES | Current value |
| threshold_value | FLOAT | Float | YES | Threshold value |
| timestamp | DATETIME | DateTime | YES | Alert timestamp |
| acknowledged | BOOLEAN | Boolean | YES | Acknowledged status |
| acknowledged_at | DATETIME | DateTime | YES | Acknowledgment time |
| acknowledged_by | VARCHAR(100) | String(100) | YES | Who acknowledged |
| resolved | BOOLEAN | Boolean | YES | Resolved status |
| resolved_at | DATETIME | DateTime | YES | Resolution time |
| notification_sent | BOOLEAN | Boolean | YES | Notification sent |
| notification_method | VARCHAR(50) | String(50) | YES | Notification method |

**Indexes**: patient_id, device_id, severity, timestamp  
**Foreign Keys**: patient_id → patients.patient_id (CASCADE), device_id → devices.device_id (CASCADE)

---

### 6. **patient_thresholds** - Personalized Thresholds
**Mục đích**: Ngưỡng cá nhân hóa cho từng bệnh nhân

| Column | Type (MySQL) | Type (SQLite) | Nullable | Description |
|--------|-------------|---------------|----------|-------------|
| id | INT AUTO_INCREMENT | Integer (PK, autoincrement) | NO | Primary key |
| patient_id | VARCHAR(50) FK | String(50) FK | NO | Patient identifier |
| vital_sign | VARCHAR(50) | String(50) | NO | Vital sign name |
| min_normal | FLOAT | Float | YES | Minimum normal value |
| max_normal | FLOAT | Float | YES | Maximum normal value |
| min_critical | FLOAT | Float | YES | Minimum critical value |
| max_critical | FLOAT | Float | YES | Maximum critical value |
| created_at | DATETIME | DateTime | YES | Creation timestamp |
| updated_at | DATETIME | DateTime | YES | Update timestamp |

**Indexes**: patient_id, vital_sign  
**Foreign Keys**: patient_id → patients.patient_id (CASCADE)

---

### 7. **sensor_calibrations** - Sensor Calibration Data
**Mục đích**: Dữ liệu hiệu chuẩn cảm biến

| Column | Type (MySQL) | Type (SQLite) | Nullable | Description |
|--------|-------------|---------------|----------|-------------|
| id | INT AUTO_INCREMENT | Integer (PK, autoincrement) | NO | Primary key |
| device_id | VARCHAR(50) FK | String(50) FK | NO | Device identifier |
| sensor_name | VARCHAR(50) | String(50) | NO | Sensor name (HX710B, MAX30102) |
| calibration_type | VARCHAR(50) | String(50) | NO | Calibration type |
| reference_values | JSON | JSON | YES | Reference values |
| measured_values | JSON | JSON | YES | Measured values |
| calibration_factors | JSON | JSON | YES | Calibration factors |
| calibrated_at | DATETIME | DateTime | YES | Calibration timestamp |
| is_active | BOOLEAN | Boolean | YES | Active status |
| notes | TEXT | Text | YES | Calibration notes |

**Indexes**: device_id, sensor_name, is_active  
**Foreign Keys**: device_id → devices.device_id (CASCADE)

---

### 8. **sync_queue** - Store-and-Forward Queue
**Mục đích**: Queue đồng bộ offline cho dữ liệu chưa sync

| Column | Type (MySQL) | Type (SQLite) | Nullable | Description |
|--------|-------------|---------------|----------|-------------|
| id | BIGINT AUTO_INCREMENT | Integer (PK, autoincrement) | NO | Primary key |
| device_id | VARCHAR(50) FK | String(50) FK | NO | Device identifier |
| table_name | VARCHAR(50) | String(50) | NO | Target table name |
| operation | VARCHAR(20) | Enum(SyncOperation) | NO | INSERT/UPDATE/DELETE |
| record_id | VARCHAR(100) | String(100) | NO | Record identifier |
| data_snapshot | JSON | JSON | YES | Data snapshot |
| priority | INT | Integer | YES | Sync priority |
| created_at | DATETIME | DateTime | YES | Creation timestamp |
| retry_count | INT | Integer | YES | Retry attempts |
| last_error | TEXT | Text | YES | Last error message |
| next_retry_at | DATETIME | DateTime | YES | Next retry time |
| sync_status | VARCHAR(20) | Enum(SyncStatus) | YES | pending/synced/failed |

**Indexes**: device_id, table_name, priority, created_at, sync_status  
**Foreign Keys**: device_id → devices.device_id (CASCADE)

---

### 9. **system_logs** - System Event Logs
**Mục đích**: Log các sự kiện hệ thống

| Column | Type (MySQL) | Type (SQLite) | Nullable | Description |
|--------|-------------|---------------|----------|-------------|
| id | BIGINT AUTO_INCREMENT | Integer (PK, autoincrement) | NO | Primary key |
| device_id | VARCHAR(50) FK | String(50) FK | YES | Device identifier |
| level | VARCHAR(20) | String(20) | NO | DEBUG/INFO/WARNING/ERROR/CRITICAL |
| message | TEXT | Text | NO | Log message |
| module | VARCHAR(100) | String(100) | YES | Module name |
| function_name | VARCHAR(100) | String(100) | YES | Function name |
| line_number | INT | Integer | YES | Line number |
| timestamp | DATETIME | DateTime | NO | Log timestamp |
| additional_data | JSON | JSON | YES | Additional data |

**Indexes**: device_id, level, module, timestamp  
**Foreign Keys**: device_id → devices.device_id (SET NULL)  
**Partitioning**: MySQL partitioned by YEAR(timestamp)

---

## 🔗 Relationships & Constraints

### **Foreign Key Relationships**
```
devices (1) ──── (N) device_ownership
devices (1) ──── (N) patients
devices (1) ──── (N) health_records
devices (1) ──── (N) alerts
devices (1) ──── (N) sensor_calibrations
devices (1) ──── (N) sync_queue
devices (1) ──── (N) system_logs

patients (1) ──── (N) health_records
patients (1) ──── (N) alerts
patients (1) ──── (N) patient_thresholds
```

### **Cascade Rules**
- **CASCADE DELETE**: health_records, alerts, patient_thresholds khi xóa patient
- **CASCADE DELETE**: tất cả records khi xóa device
- **SET NULL**: device_id trong patients, system_logs khi xóa device

---

## 📈 Analytical Views (MySQL Only)

### **v_latest_vitals** - Latest Vital Signs per Patient
```sql
SELECT patient_id, device_id, timestamp, heart_rate, spo2, temperature,
       systolic_bp, diastolic_bp, mean_arterial_pressure, data_quality
FROM health_records hr1
WHERE timestamp = (SELECT MAX(timestamp) FROM health_records hr2
                   WHERE hr1.patient_id = hr2.patient_id)
```

### **v_active_alerts** - Active Alerts
```sql
SELECT * FROM alerts WHERE resolved = FALSE ORDER BY severity DESC, timestamp DESC
```

### **v_device_health** - Device Health Status
```sql
SELECT d.device_id, d.device_name, d.last_seen,
       COUNT(hr.id) as record_count_24h,
       AVG(hr.data_quality) as avg_quality_24h
FROM devices d
LEFT JOIN health_records hr ON d.device_id = hr.device_id
    AND hr.timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY d.device_id
```

### **v_patient_vitals_trend** - Vital Signs Trends
```sql
SELECT patient_id, DATE(timestamp) as date,
       AVG(heart_rate) as avg_hr, MIN(heart_rate) as min_hr, MAX(heart_rate) as max_hr,
       AVG(spo2) as avg_spo2, AVG(temperature) as avg_temp,
       AVG(systolic_bp) as avg_sbp, AVG(diastolic_bp) as avg_dbp
FROM health_records
WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY patient_id, DATE(timestamp)
ORDER BY patient_id, date
```

### **v_sync_performance** - Sync Performance Metrics
```sql
SELECT device_id, sync_status,
       COUNT(*) as record_count,
       AVG(TIMESTAMPDIFF(SECOND, timestamp, synced_at)) as avg_sync_delay
FROM health_records
WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY device_id, sync_status
```

---

## 🔧 Stored Procedures (MySQL Only)

### **sp_cleanup_old_records**
```sql
DELIMITER //
CREATE PROCEDURE sp_cleanup_old_records(IN days_to_keep INT)
BEGIN
    -- Delete old health records
    DELETE FROM health_records
    WHERE timestamp < DATE_SUB(NOW(), INTERVAL days_to_keep DAY);

    -- Delete old alerts
    DELETE FROM alerts
    WHERE timestamp < DATE_SUB(NOW(), INTERVAL days_to_keep DAY);

    -- Delete old system logs
    DELETE FROM system_logs
    WHERE timestamp < DATE_SUB(NOW(), INTERVAL days_to_keep DAY);
END //
DELIMITER ;
```

### **sp_patient_statistics**
```sql
DELIMITER //
CREATE PROCEDURE sp_patient_statistics(IN p_patient_id VARCHAR(50))
BEGIN
    SELECT
        COUNT(*) as total_records,
        AVG(heart_rate) as avg_heart_rate,
        AVG(spo2) as avg_spo2,
        AVG(temperature) as avg_temperature,
        AVG(systolic_bp) as avg_systolic_bp,
        AVG(diastolic_bp) as avg_diastolic_bp,
        MIN(timestamp) as first_measurement,
        MAX(timestamp) as last_measurement
    FROM health_records
    WHERE patient_id = p_patient_id;
END //
DELIMITER ;
```

---

## 📊 Database Statistics

### **Current State (After Migration)**
- **Tables**: 9 core tables
- **Views**: 13 analytical views (MySQL only)
- **Procedures**: 2 stored procedures (MySQL only)
- **Total Columns**: ~80 columns
- **Relationships**: 15+ foreign key constraints
- **Indexes**: 25+ indexes for performance

### **Data Volume Estimates**
- **health_records**: High volume (measurements every 5s when active)
- **alerts**: Medium volume (triggered by thresholds)
- **system_logs**: Medium volume (events & errors)
- **Other tables**: Low volume (configuration data)

---

## 🔄 Sync Strategy

### **Store-and-Forward Pattern**
1. **Local First**: Data ghi vào SQLite trước
2. **Queue Management**: Sync queue cho offline resilience
3. **Batch Sync**: Sync theo batch 100 records mỗi 5 phút
4. **Conflict Resolution**: Cloud wins strategy
5. **Retry Logic**: Exponential backoff cho failed syncs

### **Sync Status Flow**
```
Local Write → sync_status='pending' → Cloud Sync → sync_status='synced'
                                      ↓ (fail) → sync_status='failed' → Retry Queue
```

---

## 🛡️ Security & Performance

### **Security Features**
- **TLS Encryption**: Required for cloud connections
- **Authentication**: Username/password per device
- **Authorization**: ACL rules per device type
- **Data Validation**: Input sanitization at application layer

### **Performance Optimizations**
- **Partitioning**: health_records và system_logs by year
- **Indexing**: Strategic indexes trên frequently queried columns
- **Connection Pooling**: SQLAlchemy connection pooling
- **Batch Operations**: Bulk inserts/updates cho sync

---

## 📝 Migration Notes

### **Version 2.0.0 Changes**
- ✅ Added device_id to all relevant tables
- ✅ Introduced Device and DeviceOwnership tables
- ✅ Added SyncQueue for offline resilience
- ✅ Standardized ID types (Integer for autoincrement)
- ✅ Added comprehensive indexing
- ✅ Created analytical views and stored procedures
- ✅ Implemented partitioning for large tables

### **Backward Compatibility**
- ⚠️ Schema changes are NOT backward compatible
- ⚠️ Migration script required for existing databases
- ✅ Data preservation during migration
- ✅ Automatic backup before migration

---

*Generated on: 2025-11-20*  
*Schema Version: 2.0.0*  
*Documentation: Comprehensive database schema reference*</content>
<parameter name="filePath">/home/pi/Desktop/IoT_health/DATABASE_SCHEMA.md