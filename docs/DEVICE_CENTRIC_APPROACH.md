# Device-Centric Approach - IoT Health Monitor

## 🎯 **Vấn đề gốc**

**Patient-Centric Approach (cũ):**
- Pi cần biết `patient_id` cứng từ config
- Khi tạo patient mới trên Android, phải sync `patient_id` về Pi
- Phức tạp khi nhiều user share 1 device hoặc đổi patient

**Ví dụ lỗi:**
```
Pi config: patient_id = "patient_001"
Android tạo patient mới: patient_id = "patient_abc123xyz"
→ Data không match, lịch sử bị tách rời
```

---

## ✅ **Giải pháp: Device-Centric Approach**

### **Nguyên tắc:**
1. **Pi chỉ cần biết `device_id`** (cố định, không đổi)
2. **`patient_id` được resolve tự động** từ database khi cần
3. **Data luôn gắn với `device_id`**, `patient_id` là optional

### **Flow hoạt động:**

#### **1. Pi Push Data (Local → Cloud)**
```python
# Pi chỉ cần device_id
record = {
    'device_id': 'rpi_bp_001',  # Cố định từ config
    'patient_id': None,          # Không cần biết
    'heart_rate': 78,
    'timestamp': datetime.now()
}

# CloudSyncManager tự động resolve patient_id
patient_id = query_patient_from_device('rpi_bp_001')
# → patient_id = 'patient_abc123xyz' (từ patients table)

# Push lên cloud với patient_id đã resolve
push_to_cloud(record)
```

#### **2. Android Query Data (Cloud → App)**
```kotlin
// Android query theo device_id (đã pair)
GET /api/health-records?user_id=user123&device_id=rpi_bp_001

// Backend tự động LEFT JOIN patients table
SELECT hr.*, p.name as patient_name
FROM health_records hr
JOIN devices d ON hr.device_id = d.device_id
LEFT JOIN patients p ON hr.patient_id = p.patient_id
WHERE d.device_id = 'rpi_bp_001'

// Response bao gồm cả records chưa có patient
[
  {
    "device_id": "rpi_bp_001",
    "patient_id": "patient_abc123xyz",  // Có patient
    "patient_name": "Nguyễn Văn A",
    "heart_rate": 78
  },
  {
    "device_id": "rpi_bp_001",
    "patient_id": null,                 // Chưa có patient
    "patient_name": null,
    "heart_rate": 82
  }
]
```

#### **3. Link Patient (Android → Cloud)**
```kotlin
// User tạo patient mới trên Android
POST /api/patients
{
  "user_id": "user123",
  "name": "Nguyễn Văn A",
  "age": 45
}
// → patient_id = "patient_abc123xyz" (auto-generate)

// Gán device cho patient
POST /api/patients/patient_abc123xyz/assign-device
{
  "user_id": "user123",
  "device_id": "rpi_bp_001"
}

// MySQL trigger tự động update orphan records
CALL sp_link_patient_to_records();
// → Tất cả records cũ có device_id = 'rpi_bp_001' 
//   sẽ được gán patient_id = 'patient_abc123xyz'
```

---

## 🔧 **Implementation Changes**

### **1. Database Schema (MySQL)**

#### **Migration: Allow patient_id NULL**
```sql
-- health_records table
ALTER TABLE health_records
MODIFY COLUMN patient_id VARCHAR(50) DEFAULT NULL;

-- alerts table
ALTER TABLE alerts
MODIFY COLUMN patient_id VARCHAR(50) DEFAULT NULL;

-- Foreign keys with ON DELETE SET NULL
ALTER TABLE health_records
ADD CONSTRAINT fk_health_records_patient
FOREIGN KEY (patient_id) REFERENCES patients(patient_id) 
ON DELETE SET NULL ON UPDATE CASCADE;
```

#### **Auto-Link Stored Procedure**
```sql
CREATE PROCEDURE sp_link_patient_to_records()
BEGIN
    UPDATE health_records hr
    JOIN patients p ON hr.device_id = p.device_id
    SET hr.patient_id = p.patient_id
    WHERE hr.patient_id IS NULL;
END;
```

### **2. Pi Code (cloud_sync_manager.py)**

#### **Auto-Resolve Patient ID**
```python
def push_health_record(self, record_id: int):
    # Get local record
    record = local_db.get_record(record_id)
    
    # Device-centric: Auto-resolve patient_id from cloud
    patient_id = record.patient_id  # Có thể là None
    
    if not patient_id:
        # Query từ cloud: SELECT patient_id FROM patients 
        #                  WHERE device_id = 'rpi_bp_001'
        patient_id = self.resolve_patient_from_device()
    
    # Push với patient_id (có thể NULL)
    push_to_cloud({
        'device_id': self.device_id,      # Required
        'patient_id': patient_id,         # Optional (NULL OK)
        'heart_rate': record.heart_rate
    })
```

### **3. REST API (api.py)**

#### **Device-Centric Queries**
```python
@app.route('/api/health-records')
def get_health_records():
    # Query theo device_id (primary filter)
    query = """
        SELECT hr.*, p.name as patient_name
        FROM health_records hr
        JOIN devices d ON hr.device_id = d.device_id
        JOIN device_ownership do ON d.device_id = do.device_id
        LEFT JOIN patients p ON hr.patient_id = p.patient_id
        WHERE do.user_id = :user_id
          AND d.device_id = :device_id  -- Device-centric filter
    """
    
    # Response bao gồm cả NULL patient_id
    return {
        "device_id": "rpi_bp_001",
        "patient_id": None,  # NULL OK
        "heart_rate": 78
    }
```

---

## 📊 **Data Flow Diagram**

```
┌─────────────────────────────────────────────────────────────┐
│ RASPBERRY PI (Local SQLite)                                 │
│                                                              │
│  HealthRecord {                                              │
│    device_id: "rpi_bp_001"  ✅ (Fixed, from config)         │
│    patient_id: NULL          ✅ (Optional, không cần biết)  │
│    heart_rate: 78                                            │
│  }                                                           │
└──────────────────────┬───────────────────────────────────────┘
                       │ CloudSyncManager.push_health_record()
                       │ Auto-resolve patient_id từ cloud
                       ↓
┌─────────────────────────────────────────────────────────────┐
│ MYSQL CLOUD (AWS RDS)                                        │
│                                                              │
│  patients table:                                             │
│  ┌──────────────┬─────────────┬───────────────────┐         │
│  │ patient_id   │ device_id   │ name              │         │
│  ├──────────────┼─────────────┼───────────────────┤         │
│  │ patient_abc  │ rpi_bp_001  │ Nguyễn Văn A      │         │
│  └──────────────┴─────────────┴───────────────────┘         │
│                                                              │
│  health_records table:                                       │
│  ┌──────────────┬─────────────┬─────────────┐               │
│  │ patient_id   │ device_id   │ heart_rate  │               │
│  ├──────────────┼─────────────┼─────────────┤               │
│  │ patient_abc  │ rpi_bp_001  │ 78          │ ← Auto-linked│
│  │ NULL         │ rpi_bp_001  │ 82          │ ← Orphan     │
│  └──────────────┴─────────────┴─────────────┘               │
└──────────────────────┬───────────────────────────────────────┘
                       │ REST API Query
                       ↓
┌─────────────────────────────────────────────────────────────┐
│ ANDROID APP                                                  │
│                                                              │
│  GET /api/health-records?device_id=rpi_bp_001               │
│                                                              │
│  Response:                                                   │
│  [                                                           │
│    { device_id: "rpi_bp_001",                                │
│      patient_id: "patient_abc",                              │
│      patient_name: "Nguyễn Văn A",                           │
│      heart_rate: 78 },                                       │
│                                                              │
│    { device_id: "rpi_bp_001",                                │
│      patient_id: null,        ← NULL OK                      │
│      patient_name: null,                                     │
│      heart_rate: 82 }                                        │
│  ]                                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## ✅ **Ưu điểm**

1. **Đơn giản hóa Pi config**: Không cần sync `patient_id`
2. **Flexible patient assignment**: User có thể tạo/đổi patient bất kỳ lúc nào
3. **Data không mất**: Orphan records vẫn giữ với `device_id`, auto-link khi gán patient
4. **Multi-user friendly**: Nhiều user có thể share 1 device dễ dàng
5. **Backward compatible**: Data cũ vẫn hoạt động (patient_id có sẵn)

---

## 🔄 **Migration Steps**

### **Step 1: Run Database Migration**
```bash
mysql -h database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com \
      -u admin -p iot_health_cloud \
      < scripts/migrate_device_centric.sql
```

### **Step 2: Update Pi Code**
- ✅ `cloud_sync_manager.py`: Auto-resolve patient_id
- ✅ Local SQLite: patient_id có thể NULL

### **Step 3: Update API**
- ✅ `api.py`: Device-centric queries (LEFT JOIN patients)
- ✅ Endpoints hỗ trợ patient_id = NULL

### **Step 4: Update Android App**
- Query theo `device_id` thay vì `patient_id`
- UI hiển thị "Unassigned" khi `patient_name = null`
- Cho phép user gán patient sau

---

## 📝 **Testing Checklist**

### **Test Case 1: New Device (Chưa có patient)**
```
1. Pi đo vitals → Push với patient_id = NULL
2. Android query theo device_id → Show records với "Unassigned"
3. User tạo patient → Gán device
4. Run sp_link_patient_to_records()
5. Query lại → Tất cả records đã có patient_name
```

### **Test Case 2: Device Đổi Patient**
```
1. Device gán cho Patient A
2. Pi push data → patient_id = "patient_A"
3. User unassign → device_id = NULL trong patients table
4. Pi push data mới → patient_id = NULL (orphan)
5. User gán Patient B → device_id = "rpi_bp_001"
6. Orphan records tự động link patient_id = "patient_B"
```

### **Test Case 3: Multiple Users Share Device**
```
1. User 1 pair device → device_ownership (user_1, device_id, role=owner)
2. User 2 pair device → device_ownership (user_2, device_id, role=viewer)
3. User 1 query → See all records (filter by device_id)
4. User 2 query → See all records (filter by device_id)
5. User 1 assign patient → Chỉ user 1 thấy patient info
```

---

## 🚨 **Important Notes**

1. **Foreign Key với ON DELETE SET NULL**: Khi xóa patient, data không mất (chỉ patient_id → NULL)
2. **Index optimization**: `idx_device_timestamp` để query nhanh theo device
3. **Stored procedure**: Chạy định kỳ để auto-link orphan records
4. **API backward compatible**: Vẫn hỗ trợ query theo patient_id (optional)

---

## 📚 **Related Files**

- `scripts/migrate_device_centric.sql` - Database migration script
- `src/communication/cloud_sync_manager.py` - Auto-resolve logic
- `scripts/api.py` - Device-centric API endpoints
- `config/app_config.yaml` - Pi config (chỉ cần device_id)
