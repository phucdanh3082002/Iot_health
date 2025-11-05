# 🔧 MySQL Schema Fix - Partitioning & Foreign Keys

## ❌ **PROBLEM**

MySQL không hỗ trợ Foreign Keys trong Partitioned Tables:
```
Error Code: 1506. Foreign keys are not yet supported in conjunction with partitioning
```

## ✅ **SOLUTION**

Đã fix script `mysql_schema.sql` bằng cách:
1. **Bỏ Foreign Keys** khỏi partitioned tables
2. **Giữ lại Partitioning** (quan trọng cho performance)
3. **Referential integrity** được enforce ở application level (CloudSyncManager)

---

## 📋 **CÁC BẢNG ĐÃ SỬA**

### **1. health_records (partitioned by year)**
- ❌ Removed: `FOREIGN KEY (patient_id) REFERENCES patients(patient_id)`
- ❌ Removed: `FOREIGN KEY (device_id) REFERENCES devices(device_id)`
- ✅ Kept: Partitioning by YEAR(timestamp)
- ✅ Kept: All indexes

### **2. alerts**
- ❌ Removed: `FOREIGN KEY (health_record_id) REFERENCES health_records(id)`
  - Vì `health_records` là partitioned table
- ✅ Kept: FK to `patients` và `devices` (non-partitioned)

### **3. system_logs (partitioned by month)**
- ❌ Removed: `FOREIGN KEY (device_id) REFERENCES devices(device_id)`
- ✅ Kept: Partitioning by UNIX_TIMESTAMP(timestamp)

---

## 🚀 **DEPLOYMENT STEPS**

### **Bước 1: DROP DATABASE CŨ (Nếu đã tạo)**

```sql
-- TRONG MYSQL WORKBENCH:

-- Check xem database có tồn tại không
SHOW DATABASES LIKE 'iot_health_cloud';

-- Nếu có, drop để tạo lại (WARNING: Xóa hết data!)
DROP DATABASE IF EXISTS iot_health_cloud;
```

### **Bước 2: RUN FIXED SCRIPT**

**Option A: Trong MySQL Workbench**
1. File → Open SQL Script
2. Chọn: `/path/to/IoT_health/scripts/mysql_schema.sql` (đã fix)
3. Click ⚡ **Execute**
4. Verify không có error

**Option B: Command Line**
```bash
# Trên PC (nếu có mysql command)
mysql -u root -p < C:\path\to\mysql_schema.sql
```

### **Bước 3: VERIFY TABLES CREATED**

```sql
USE iot_health_cloud;

-- Check all tables created
SHOW TABLES;
-- Expected: 8 tables
-- devices, patients, health_records, alerts, 
-- patient_thresholds, sensor_calibrations, system_logs, sync_queue

-- Check partitions
SELECT TABLE_NAME, PARTITION_NAME, PARTITION_ORDINAL_POSITION, TABLE_ROWS
FROM INFORMATION_SCHEMA.PARTITIONS
WHERE TABLE_SCHEMA = 'iot_health_cloud' 
  AND TABLE_NAME IN ('health_records', 'system_logs')
ORDER BY TABLE_NAME, PARTITION_ORDINAL_POSITION;

-- Expected output:
-- health_records: p2024, p2025, p2026, p2027, pmax
-- system_logs: p202411, p202412, p202501, p202502, pmax
```

### **Bước 4: CREATE USER (Nếu chưa có)**

```sql
CREATE USER 'iot_sync_user'@'%' 
IDENTIFIED BY 'IotSync@2025!';

GRANT SELECT, INSERT, UPDATE ON iot_health_cloud.* 
TO 'iot_sync_user'@'%';

GRANT EXECUTE ON PROCEDURE iot_health_cloud.sp_cleanup_old_records 
TO 'iot_sync_user'@'%';

GRANT EXECUTE ON PROCEDURE iot_health_cloud.sp_patient_statistics 
TO 'iot_sync_user'@'%';

FLUSH PRIVILEGES;
```

---

## 🔍 **VERIFICATION QUERIES**

### **1. Check Foreign Keys (should be minimal)**

```sql
SELECT 
    TABLE_NAME,
    CONSTRAINT_NAME,
    REFERENCED_TABLE_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'iot_health_cloud'
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME;

-- Expected:
-- patients → devices (OK)
-- alerts → patients, devices (OK)
-- patient_thresholds → patients (OK)
-- sensor_calibrations → devices (OK)
-- sync_queue → devices (OK)
-- health_records, system_logs: NONE (partitioned)
```

### **2. Check Indexes**

```sql
SELECT 
    TABLE_NAME,
    INDEX_NAME,
    GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS COLUMNS
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'iot_health_cloud'
  AND TABLE_NAME IN ('health_records', 'alerts', 'system_logs')
GROUP BY TABLE_NAME, INDEX_NAME
ORDER BY TABLE_NAME, INDEX_NAME;

-- All indexes should exist
```

### **3. Test INSERT**

```sql
-- Insert test device
INSERT INTO devices (device_id, device_name, location) 
VALUES ('test_device_001', 'Test Device', 'Lab');

-- Insert test patient
INSERT INTO patients (patient_id, device_id, name) 
VALUES ('patient_test', 'test_device_001', 'Test Patient');

-- Insert test health record (partitioned table)
INSERT INTO health_records 
(patient_id, device_id, timestamp, heart_rate, spo2, temperature) 
VALUES 
('patient_test', 'test_device_001', NOW(), 75.0, 98.0, 36.6);

-- Check inserted
SELECT * FROM health_records WHERE patient_id = 'patient_test';

-- Cleanup test data
DELETE FROM health_records WHERE patient_id = 'patient_test';
DELETE FROM patients WHERE patient_id = 'patient_test';
DELETE FROM devices WHERE device_id = 'test_device_001';
```

---

## 📊 **IMPACT ANALYSIS**

### **✅ ADVANTAGES**

1. **Performance**: Partitioning hoạt động → queries nhanh hơn
2. **Scalability**: Millions records vẫn OK
3. **Maintenance**: Easy pruning old partitions
4. **Standards**: Follow MySQL best practices

### **⚠️ TRADE-OFFS**

1. **No database-level RI**: Foreign key constraints bị bỏ
2. **Application responsibility**: CloudSyncManager phải validate
3. **Manual cleanup**: Orphaned records có thể tồn tại nếu app lỗi

### **🛡️ MITIGATIONS**

**CloudSyncManager đã handle:**
- Validate `patient_id` và `device_id` tồn tại trước khi insert
- Check referential integrity trong `push_*()` methods
- Transaction support để đảm bảo consistency

**Application-level checks:**
```python
# Example trong CloudSyncManager.push_health_record()
def push_health_record(self, record_id):
    # Get record from local SQLite
    record = self.local_db.get_health_record(record_id)
    
    # Validate patient exists in cloud
    cloud_patient = self.cloud_session.query(Patient).filter_by(
        patient_id=record['patient_id']
    ).first()
    
    if not cloud_patient:
        # Create patient first or skip
        logger.warning(f"Patient {record['patient_id']} not in cloud")
        return False
    
    # Validate device exists
    cloud_device = self.cloud_session.query(Device).filter_by(
        device_id=record['device_id']
    ).first()
    
    if not cloud_device:
        # Register device first
        self._register_device()
    
    # Now safe to insert health_record
    # ...
```

---

## 🔄 **FUTURE MAINTENANCE**

### **Add New Partitions (Yearly)**

```sql
-- Add partition for 2029
ALTER TABLE health_records 
ADD PARTITION (PARTITION p2028 VALUES LESS THAN (2029));
```

### **Add New Partitions (Monthly)**

```sql
-- Add partition for March 2025
ALTER TABLE system_logs 
ADD PARTITION (
    PARTITION p202503 VALUES LESS THAN (UNIX_TIMESTAMP('2025-04-01'))
);
```

### **Drop Old Partitions**

```sql
-- Drop 2024 data (if not needed)
ALTER TABLE health_records DROP PARTITION p2024;

-- Drop old logs
ALTER TABLE system_logs DROP PARTITION p202411;
```

---

## ✅ **CHECKLIST**

- [ ] DROP old database (if exists)
- [ ] Execute fixed mysql_schema.sql
- [ ] Verify 8 tables created
- [ ] Check partitions exist (health_records, system_logs)
- [ ] Create iot_sync_user
- [ ] Test INSERT into health_records
- [ ] Verify no FK errors
- [ ] Continue with Phase 2 checklist

---

## 📚 **REFERENCES**

- MySQL Partitioning Docs: https://dev.mysql.com/doc/refman/8.0/en/partitioning.html
- Partitioning Limitations: https://dev.mysql.com/doc/refman/8.0/en/partitioning-limitations.html
- Foreign Key Limitation: "Foreign keys are not supported for partitioned tables" (MySQL 8.0)

---

## 🆘 **STILL GETTING ERRORS?**

**Error: "Foreign keys are not yet supported..."**
→ Script chưa update, re-download từ Pi:
```bash
cat ~/Desktop/IoT_health/scripts/mysql_schema.sql
```

**Error: "Partition pmax already exists"**
→ Database đã tồn tại, DROP và tạo lại:
```sql
DROP DATABASE iot_health_cloud;
```

**Error: "Can't DROP database; database doesn't exist"**
→ OK, proceed với CREATE DATABASE

---

**Updated:** 2025-11-05  
**Version:** 1.1 (Fixed partitioning issue)
