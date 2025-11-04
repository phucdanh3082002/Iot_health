# 🗄️ SQLite Local Database Implementation

## **Tổng quan**

SQLite local database đã được implement đầy đủ cho IoT Health Monitoring System với các tính năng:

- ✅ **Full CRUD operations** cho tất cả models
- ✅ **Transaction management** với context managers
- ✅ **Data validation** và error handling
- ✅ **Backup/restore** functionality
- ✅ **Statistics** và aggregation
- ✅ **Auto cleanup** old records
- ✅ **Thread-safe** operations

---

## **📋 Database Schema**

### **Tables**

1. **patients** - Thông tin bệnh nhân
   - patient_id (unique)
   - name, age, gender
   - medical_conditions (JSON)
   - emergency_contact (JSON)
   - created_at, updated_at, is_active

2. **health_records** - Dữ liệu đo vital signs
   - patient_id (FK)
   - timestamp
   - heart_rate, spo2, temperature
   - systolic_bp, diastolic_bp, mean_arterial_pressure
   - sensor_data (JSON)
   - data_quality, measurement_context

3. **alerts** - Cảnh báo sức khỏe
   - patient_id (FK)
   - alert_type, severity, message
   - vital_sign, current_value, threshold_value
   - timestamp, acknowledged, resolved

4. **patient_thresholds** - Ngưỡng cá nhân hóa
   - patient_id (FK)
   - vital_sign
   - min_normal, max_normal
   - min_critical, max_critical
   - is_active

5. **sensor_calibrations** - Calibration sensors
   - sensor_name
   - calibration_type
   - reference_values, measured_values (JSON)
   - calibration_factors (JSON)
   - calibrated_at, is_active, notes

6. **system_logs** - System event logs
   - level, message
   - module, function, line_number
   - timestamp
   - additional_data (JSON)

---

## **🔧 DatabaseManager API**

### **Initialization**

```python
from src.data.database import DatabaseManager

config = {
    'database': {
        'path': 'data/health_monitor.db'
    }
}

db = DatabaseManager(config)
db.initialize()  # Create tables
```

### **Patient Operations**

```python
# Create patient
patient_data = {
    'patient_id': 'P12345',
    'name': 'Nguyễn Văn A',
    'age': 65,
    'gender': 'M',
    'medical_conditions': ['Hypertension'],
    'emergency_contact': {'name': 'Spouse', 'phone': '0901234567'}
}
patient_id = db.create_patient(patient_data)

# Get patient
patient = db.get_patient(patient_id)

# Update patient
db.update_patient(patient_id, {'age': 66})
```

### **Health Records**

```python
# Save health record
record_data = {
    'patient_id': 'P12345',
    'timestamp': datetime.now(),
    'heart_rate': 75.0,
    'spo2': 98.0,
    'temperature': 36.5,
    'systolic_bp': 120.0,
    'diastolic_bp': 80.0,
    'mean_arterial_pressure': 93.3,
    'data_quality': 0.95,
    'measurement_context': 'rest'
}
record_id = db.save_health_record(record_data)

# Get health records
records = db.get_health_records(
    patient_id='P12345',
    start_time=datetime.now() - timedelta(days=7),
    limit=100
)

# Get latest vitals
latest = db.get_latest_vitals('P12345')
```

### **Alerts**

```python
# Save alert
alert_data = {
    'patient_id': 'P12345',
    'alert_type': 'threshold',
    'severity': 'high',
    'message': 'Huyết áp cao: 145/95 mmHg',
    'vital_sign': 'blood_pressure',
    'current_value': 145.0,
    'threshold_value': 140.0
}
alert_id = db.save_alert(alert_data)

# Get active alerts
alerts = db.get_active_alerts('P12345')

# Acknowledge/resolve alert
db.acknowledge_alert(alert_id)
db.resolve_alert(alert_id)
```

### **Thresholds**

```python
# Save custom thresholds
thresholds = {
    'heart_rate': {
        'min_normal': 60.0,
        'max_normal': 100.0,
        'min_critical': 40.0,
        'max_critical': 150.0
    },
    'systolic_bp': {
        'min_normal': 90.0,
        'max_normal': 140.0,
        'min_critical': 70.0,
        'max_critical': 180.0
    }
}
db.save_patient_thresholds('P12345', thresholds)

# Get thresholds
thresholds = db.get_patient_thresholds('P12345')
```

### **Sensor Calibration**

```python
# Save calibration
calibration_data = {
    'sensor_name': 'HX710B',
    'calibration_type': 'two_point',
    'reference_values': [0.0, 200.0],
    'measured_values': [1300885, 7900123],
    'calibration_factors': {
        'offset_counts': 1300885,
        'slope_mmhg_per_count': 3.5765e-05
    },
    'notes': 'Calibrated with reference manometer'
}
cal_id = db.save_sensor_calibration(calibration_data)

# Get active calibration
calibration = db.get_sensor_calibration('HX710B')
```

### **Statistics**

```python
# Get health statistics
stats = db.get_health_statistics('P12345', time_range='7d')

# Result:
{
    'time_range': '7d',
    'record_count': 42,
    'heart_rate': {
        'avg': 75.5,
        'min': 65.0,
        'max': 95.0,
        'count': 42
    },
    'systolic_bp': {
        'avg': 125.3,
        'min': 110.0,
        'max': 145.0,
        'count': 42
    }
}
```

### **Backup & Restore**

```python
# Backup database
db.backup_database('backups/health_monitor_20251103.db')

# Restore database
db.restore_database('backups/health_monitor_20251103.db')

# Cleanup old records (older than 90 days)
deleted_count = db.cleanup_old_records(days_to_keep=90)
```

### **Database Info**

```python
# Get database information
info = db.get_database_info()

# Result:
{
    'db_path': 'data/health_monitor.db',
    'db_size_mb': 2.5,
    'tables': {
        'patients': 5,
        'health_records': 1250,
        'alerts': 18,
        'thresholds': 25,
        'calibrations': 3,
        'system_logs': 450
    }
}
```

---

## **🛠️ Utility Scripts**

### **1. Initialize Database**

```bash
# Create database and default patient
python scripts/init_database.py
```

Output:
- Creates all tables
- Creates default patient from config
- Saves initial HX710B calibration
- Shows database summary

### **2. Query Database**

```bash
# Show database info
python scripts/query_database.py --info

# Show all patients
python scripts/query_database.py --patients

# Show health records for patient
python scripts/query_database.py --records -p P12345 --limit 20

# Show statistics (7 days)
python scripts/query_database.py --stats -p P12345 --range 7d

# Show active alerts
python scripts/query_database.py --alerts -p P12345

# Show sensor calibrations
python scripts/query_database.py --calibrations

# Show everything
python scripts/query_database.py --patients --records --stats --alerts --calibrations
```

---

## **🧪 Testing**

### **Run Full Test Suite**

```bash
python tests/test_database.py
```

Tests cover:
1. Database initialization
2. Patient CRUD operations
3. Health records operations
4. Alert management
5. Sensor calibration
6. Backup/restore
7. System logging
8. Cleanup operations

### **Test Results**

```
✅ ALL TESTS PASSED!

Database: data/test_health_monitor.db
Size: 0.03 MB

Table Counts:
  - patients: 1
  - health_records: 3
  - alerts: 2
  - thresholds: 5
  - calibrations: 2
  - system_logs: 3
```

---

## **📊 Integration với Main App**

### **Trong main.py**

```python
from src.data.database import DatabaseManager

class HealthMonitorSystem:
    def __init__(self):
        # ... existing code ...
        
        # Initialize database
        self.database = DatabaseManager(self.config)
        self.database.initialize()
    
    def _initialize_sensors(self):
        # ... sensor init code ...
        
        # Load HX710B calibration from database
        hx710b_cal = self.database.get_sensor_calibration('HX710B')
        if hx710b_cal:
            self.sensors['blood_pressure'].set_calibration(hx710b_cal)
```

### **Trong BP Measurement Screen**

```python
def _handle_result_on_main_thread(self, result: BloodPressureMeasurement):
    """Save BP measurement to database"""
    app = MDApp.get_running_app()
    
    # Save to database
    record_data = {
        'patient_id': app.config['patient']['id'],
        'timestamp': result.timestamp,
        'systolic_bp': result.systolic,
        'diastolic_bp': result.diastolic,
        'mean_arterial_pressure': result.map_value,
        'sensor_data': result.metadata,
        'data_quality': result.confidence,
        'measurement_context': 'bp_measurement'
    }
    
    record_id = app.database.save_health_record(record_data)
    
    # Check for alerts
    if result.systolic > 140 or result.diastolic > 90:
        alert_data = {
            'patient_id': app.config['patient']['id'],
            'alert_type': 'threshold',
            'severity': 'high',
            'message': f'Huyết áp cao: {result.systolic:.0f}/{result.diastolic:.0f} mmHg',
            'vital_sign': 'blood_pressure',
            'current_value': result.systolic,
            'threshold_value': 140.0
        }
        app.database.save_alert(alert_data)
```

### **Trong Dashboard Screen**

```python
def update_history_chart(self):
    """Update chart with data from database"""
    app = MDApp.get_running_app()
    
    # Get last 7 days of records
    end_time = datetime.now()
    start_time = end_time - timedelta(days=7)
    
    records = app.database.get_health_records(
        patient_id=app.config['patient']['id'],
        start_time=start_time,
        end_time=end_time,
        limit=1000
    )
    
    # Process for chart
    timestamps = [r['timestamp'] for r in records]
    hr_values = [r['heart_rate'] for r in records if r['heart_rate']]
    bp_sys = [r['systolic_bp'] for r in records if r['systolic_bp']]
    
    # Update chart...
```

---

## **⚠️ Important Notes**

### **Thread Safety**

DatabaseManager sử dụng:
- SQLAlchemy sessions với thread-safe sessionmaker
- Context managers (`get_session()`) để auto-commit/rollback
- Timeout 30s cho database locks

```python
# Thread-safe usage
with db.get_session() as session:
    # Your operations here
    pass  # Auto-commit on success, rollback on exception
```

### **Data Validation**

Tự động validate vital signs ranges:
- HR: 30-200 BPM
- SpO2: 0-100%
- Temperature: 30-45°C
- BP: 50-250 mmHg (systolic), 30-150 mmHg (diastolic)

Invalid values trigger warnings nhưng vẫn save (để review sau).

### **Performance**

- Indexing: Auto-indexed trên patient_id, timestamp
- Query optimization: Sử dụng limits và time filters
- Cleanup: Schedule cleanup_old_records() định kỳ

### **Backup Strategy**

Recommended:
1. Auto backup mỗi ngày (cronjob)
2. Keep backups 30 days
3. Test restore định kỳ

```bash
# Cronjob example (daily backup)
0 2 * * * cd /home/pi/Desktop/IoT_health && .venv/bin/python -c "from src.data.database import DatabaseManager; import yaml; config = yaml.safe_load(open('config/app_config.yaml')); db = DatabaseManager(config); db.backup_database(f'backups/health_monitor_{datetime.now().strftime(\"%Y%m%d\")}.db')"
```

---

## **🔮 Next Steps: MySQL Cloud Sync**

Để sync với MySQL cloud (PC cá nhân):

1. **MySQL Server Setup** (trên PC)
   - Install MySQL Server
   - Create database schema (tương tự SQLite)
   - Configure remote access

2. **Cloud Sync Module** (trên Raspberry Pi)
   - Implement `CloudSyncManager`
   - Periodic sync (every 1 hour)
   - Conflict resolution (cloud wins)
   - Offline queue

3. **Sync Strategy**
   - Upload new records to cloud
   - Download updates from cloud
   - Keep local copy for offline operation
   - Sync sensor calibrations

File to create:
- `src/communication/cloud_sync.py`
- `scripts/sync_to_cloud.py`

---

## **✅ Implementation Checklist**

- ✅ Database models defined (SQLAlchemy ORM)
- ✅ DatabaseManager với full CRUD operations
- ✅ Transaction management và error handling
- ✅ Data validation
- ✅ Backup/restore functionality
- ✅ Statistics và aggregation
- ✅ System logging to database
- ✅ Initialization script
- ✅ Query utility script
- ✅ Comprehensive testing
- ✅ Documentation

**SQLite Local Database: COMPLETE! 🎉**

---

## **📚 References**

- SQLAlchemy docs: https://docs.sqlalchemy.org/
- SQLite docs: https://www.sqlite.org/docs.html
- Python datetime: https://docs.python.org/3/library/datetime.html
