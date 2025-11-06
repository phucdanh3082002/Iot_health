# 📊 DATABASE WORKFLOW ANALYSIS - GUI Integration

**Ngày:** 5 Tháng 11, 2025  
**Phạm vi:** Phân tích database workflow trong GUI sau khi hoàn thành hardware integration

---

## ✅ TỔNG QUAN WORKFLOW HIỆN TẠI

### 1️⃣ **Data Flow Architecture**

```
┌─────────────────────────────────────────────────────────────────┐
│                        GUI SCREENS                               │
│  (Dashboard, HeartRate, Temperature, BP Measurement)             │
└───────────────────────┬─────────────────────────────────────────┘
                        │ Measurement completed
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│      main_app.save_measurement_to_database(measurement_data)     │
│  - Normalize data fields (hr/heart_rate, temp/temperature...)   │
│  - Extract metadata (SQI, CV, peak_count, duration)              │
│  - Convert timestamp to datetime object                          │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│         DatabaseManager.save_health_record(health_data)          │
│  - Insert to health_records table (SQLite local)                │
│  - Auto-commit transaction                                       │
│  - Return record_id                                              │
└───────────────────────┬─────────────────────────────────────────┘
                        │ After transaction commit
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│    CloudSyncManager.push_health_record(record) [AUTO CALLBACK]   │
│  - Sync to MySQL cloud (async)                                   │
│  - Store & Forward if connection fails                           │
└─────────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│      main_app._check_and_create_alert(patient_id, data, id)      │
│  - Check thresholds (HR, SpO2, Temp, BP)                         │
│  - Create alerts if thresholds exceeded                          │
│  - Save alerts to database                                       │
│  - Trigger TTS for high/critical severity                        │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│         DatabaseManager.save_alert(alert_data) [IF NEEDED]       │
│  - Insert to alerts table (SQLite local)                         │
│  - Auto-sync to MySQL cloud via CloudSyncManager callback       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔍 CHI TIẾT WORKFLOW TỪNG BƯỚC

### **STEP 1: Measurement Completion (GUI Screens)**

**Files:** 
- `src/gui/heart_rate_screen.py` (lines 980-995)
- `src/gui/temperature_screen.py` (line 385)
- `src/gui/bp_measurement_screen.py` (lines 554-578)

**Logic:**
```python
# Heart Rate Screen
measurement_data = {
    "timestamp": time.time(),
    "heart_rate": self.current_hr,
    "spo2": self.current_spo2,
    "measurement_type": "heart_rate_spo2",
}
self.app_instance.save_measurement_to_database(measurement_data)

# Temperature Screen
measurement_data = {
    'timestamp': time.time(),
    'temperature': self.current_temp,
    'measurement_type': 'temperature',
}
self.app_instance.save_measurement_to_database(measurement_data)

# BP Measurement Screen
measurement_data = {
    'timestamp': time.time(),
    'systolic': self.last_result.systolic,
    'diastolic': self.last_result.diastolic,
    'map_value': self.last_result.map_value,
    'heart_rate': self.last_result.heart_rate,
    'measurement_type': 'blood_pressure',
    'quality': self.last_result.quality,
    'confidence': self.last_result.confidence
}
self.app_instance.save_measurement_to_database(measurement_data)
```

**✅ Strengths:**
- Consistent pattern across all screens
- Includes `measurement_type` for tracking
- Captures metadata (quality, confidence, SQI, CV)

**⚠️ Issues:**
- No data validation before saving
- No user feedback on save success/failure
- Hardcoded patient_id in main_app (not from GUI)

---

### **STEP 2: Data Normalization (main_app.py)**

**File:** `src/gui/main_app.py` (lines 904-1014)

**Logic:**
```python
def save_measurement_to_database(self, measurement_data: Dict[str, Any]):
    # Get patient_id from config
    patient_id = self.config_data.get('patient', {}).get('id', 'patient_001')
    
    # Convert timestamp to datetime
    timestamp_value = measurement_data.get('timestamp', time.time())
    if isinstance(timestamp_value, (int, float)):
        timestamp_dt = datetime.fromtimestamp(timestamp_value)
    elif isinstance(timestamp_value, datetime):
        timestamp_dt = timestamp_value
    else:
        timestamp_dt = datetime.now()
    
    # Normalize field names (multiple aliases)
    health_data = {
        'patient_id': patient_id,
        'timestamp': timestamp_dt,
        'heart_rate': measurement_data.get('heart_rate') or measurement_data.get('hr'),
        'spo2': measurement_data.get('spo2'),
        'temperature': (
            measurement_data.get('temperature') 
            or measurement_data.get('temp')
            or measurement_data.get('object_temperature')
        ),
        'systolic_bp': measurement_data.get('systolic') or measurement_data.get('blood_pressure_systolic'),
        'diastolic_bp': measurement_data.get('diastolic') or measurement_data.get('blood_pressure_diastolic'),
        'mean_arterial_pressure': measurement_data.get('map') or measurement_data.get('map_bp'),
    }
    
    # Extract metadata (Phase 2 enhancement)
    metadata = {}
    if 'signal_quality_index' in measurement_data:
        metadata['signal_quality_index'] = measurement_data['signal_quality_index']
    if 'spo2_cv' in measurement_data:
        metadata['spo2_cv'] = measurement_data['spo2_cv']
    if 'peak_count' in measurement_data:
        metadata['peak_count'] = measurement_data['peak_count']
    if 'measurement_elapsed' in measurement_data:
        metadata['measurement_duration'] = measurement_data['measurement_elapsed']
    if 'measurement_type' in measurement_data:
        metadata['measurement_type'] = measurement_data['measurement_type']
    if 'ambient_temperature' in measurement_data:
        metadata['ambient_temperature'] = measurement_data['ambient_temperature']
    if 'hr_valid' in measurement_data:
        metadata['hr_valid'] = measurement_data['hr_valid']
    if 'spo2_valid' in measurement_data:
        metadata['spo2_valid'] = measurement_data['spo2_valid']
    
    if metadata:
        health_data['sensor_data'] = metadata  # JSON column
    
    # Call DatabaseManager
    record_id = self.database.save_health_record(health_data)
    
    if record_id:
        self.logger.info(f"✅ Measurement saved (record_id={record_id})")
        self._check_and_create_alert(patient_id, health_data, record_id)
    else:
        self.logger.warning("DatabaseManager returned None - falling back")
```

**✅ Strengths:**
- Comprehensive field mapping (handles multiple aliases)
- Metadata extraction for data quality tracking
- Proper datetime conversion
- Fallback to local vitals.db if DatabaseManager fails
- Auto-triggers alert checking

**⚠️ Issues:**
- **CRITICAL:** `patient_id` hard-coded from config, không lấy từ GUI
- No validation of measurement values (e.g., HR 0-300, SpO2 0-100)
- No error feedback to user (only logs)
- Fallback logic duplicates code (could be refactored)

---

### **STEP 3: Database Persistence (DatabaseManager)**

**File:** `src/data/database.py` (method `save_health_record`)

**Logic:**
```python
def save_health_record(self, health_data: Dict[str, Any]) -> Optional[int]:
    """
    Save health record to SQLite local database
    Auto-triggers cloud sync callback after transaction commit
    
    Returns:
        record_id if successful, None otherwise
    """
    with self.Session() as session:
        try:
            # Create HealthRecord model instance
            record = HealthRecord(
                patient_id=health_data['patient_id'],
                timestamp=health_data['timestamp'],
                heart_rate=health_data.get('heart_rate'),
                spo2=health_data.get('spo2'),
                temperature=health_data.get('temperature'),
                systolic_bp=health_data.get('systolic_bp'),
                diastolic_bp=health_data.get('diastolic_bp'),
                mean_arterial_pressure=health_data.get('mean_arterial_pressure'),
                sensor_data=health_data.get('sensor_data'),  # JSON metadata
                data_quality=health_data.get('data_quality', 1.0)
            )
            
            session.add(record)
            session.commit()
            record_id = record.id
            
        except Exception as e:
            session.rollback()
            self.logger.error(f"Failed to save health record: {e}")
            return None
    
    # AFTER transaction commit - trigger cloud sync callback
    if record_id and self.cloud_sync_manager:
        try:
            self.cloud_sync_manager.push_health_record(record)
        except Exception as e:
            self.logger.error(f"Cloud sync callback failed: {e}")
    
    return record_id
```

**✅ Strengths:**
- Transaction management (commit/rollback)
- Auto-sync callback AFTER commit (Phase 2 fix)
- JSON metadata storage in `sensor_data` column
- Error handling with logging

**⚠️ Issues:**
- No validation before insert (relies on caller)
- Cloud sync error doesn't affect return value (silent failure)
- No retry mechanism if cloud sync fails (relies on Store & Forward)

---

### **STEP 4: Cloud Sync (CloudSyncManager)**

**File:** `src/communication/cloud_sync_manager.py`

**Logic:**
```python
def push_health_record(self, record):
    """
    Push health record to MySQL cloud database
    Triggered by DatabaseManager callback after local save
    """
    try:
        with self.engine.connect() as conn:
            # Build INSERT/UPDATE query
            health_data = {
                'device_id': self.device_id,
                'patient_id': record.patient_id,
                'timestamp': record.timestamp,
                'heart_rate': record.heart_rate,
                'spo2': record.spo2,
                'temperature': record.temperature,
                'systolic_bp': record.systolic_bp,
                'diastolic_bp': record.diastolic_bp,
                'mean_arterial_pressure': record.mean_arterial_pressure,
                'sensor_data': record.sensor_data,  # JSON
                'data_quality': record.data_quality,
                'synced_at': datetime.now()
            }
            
            # Check if record exists (by timestamp + patient_id)
            check_sql = text("""
                SELECT id FROM health_records 
                WHERE patient_id = :patient_id 
                  AND timestamp = :timestamp 
                LIMIT 1
            """)
            existing = conn.execute(check_sql, {
                'patient_id': record.patient_id,
                'timestamp': record.timestamp
            }).fetchone()
            
            if existing:
                # UPDATE existing record
                update_sql = text("""
                    UPDATE health_records 
                    SET heart_rate=:heart_rate, spo2=:spo2, 
                        temperature=:temperature, systolic_bp=:systolic_bp,
                        diastolic_bp=:diastolic_bp, map=:mean_arterial_pressure,
                        sensor_data=:sensor_data, data_quality=:data_quality,
                        synced_at=:synced_at
                    WHERE id=:id
                """)
                health_data['id'] = existing[0]
                conn.execute(update_sql, health_data)
            else:
                # INSERT new record
                insert_sql = text("""
                    INSERT INTO health_records 
                    (device_id, patient_id, timestamp, heart_rate, spo2, 
                     temperature, systolic_bp, diastolic_bp, map, 
                     sensor_data, data_quality, synced_at)
                    VALUES (:device_id, :patient_id, :timestamp, :heart_rate, 
                            :spo2, :temperature, :systolic_bp, :diastolic_bp, 
                            :mean_arterial_pressure, :sensor_data, :data_quality, :synced_at)
                """)
                conn.execute(insert_sql, health_data)
            
            conn.commit()
            self.logger.info(f"✅ Cloud sync: health_record pushed (patient={record.patient_id})")
            
    except Exception as e:
        self.logger.error(f"Cloud sync failed: {e}")
        # Store & Forward will retry later
        self._add_to_sync_queue('health_record', record.id)
```

**✅ Strengths:**
- Upsert logic (INSERT or UPDATE)
- Conflict detection by timestamp + patient_id
- Store & Forward fallback on failure
- JSON metadata preserved in cloud

**⚠️ Issues:**
- No explicit retry count tracking
- Sync queue implementation incomplete (TODO in code)
- No notification to user when sync fails

---

### **STEP 5: Alert Generation (main_app.py)**

**File:** `src/gui/main_app.py` (lines 1015-1145)

**Logic:**
```python
def _check_and_create_alert(self, patient_id: str, health_data: Dict, record_id: int):
    """
    Check thresholds and create alerts automatically
    """
    # Get patient thresholds from database
    thresholds = self.database.get_patient_thresholds(patient_id)
    if not thresholds:
        return
    
    alerts = []
    
    # Check Heart Rate
    hr = health_data.get('heart_rate')
    if hr and hr > 0:
        hr_min = thresholds.get('heart_rate_min', 60)
        hr_max = thresholds.get('heart_rate_max', 100)
        if hr < hr_min:
            alerts.append({
                'type': 'low_heart_rate',
                'severity': 'medium',
                'message': f'Nhịp tim thấp: {hr:.0f} BPM (ngưỡng: {hr_min}-{hr_max})',
                'value': hr
            })
        elif hr > hr_max:
            alerts.append({
                'type': 'high_heart_rate',
                'severity': 'high',
                'message': f'Nhịp tim cao: {hr:.0f} BPM (ngưỡng: {hr_min}-{hr_max})',
                'value': hr
            })
    
    # Check SpO2
    spo2 = health_data.get('spo2')
    if spo2 and spo2 > 0:
        spo2_min = thresholds.get('spo2_min', 95)
        if spo2 < spo2_min:
            severity = 'critical' if spo2 < 90 else 'high'
            alerts.append({
                'type': 'low_spo2',
                'severity': severity,
                'message': f'SpO2 thấp: {spo2:.0f}% (ngưỡng tối thiểu: {spo2_min}%)',
                'value': spo2
            })
    
    # Check Temperature
    temp = health_data.get('temperature')
    if temp and temp > 0:
        temp_min = thresholds.get('temperature_min', 36.0)
        temp_max = thresholds.get('temperature_max', 37.5)
        if temp < temp_min:
            severity = 'high' if temp < 35.0 else 'medium'
            alerts.append({...})
        elif temp > temp_max:
            severity = 'critical' if temp > 39.0 else 'high'
            alerts.append({...})
    
    # Check Blood Pressure
    systolic = health_data.get('systolic_bp')
    diastolic = health_data.get('diastolic_bp')
    if systolic and diastolic and systolic > 0 and diastolic > 0:
        sys_min = thresholds.get('systolic_bp_min', 90)
        sys_max = thresholds.get('systolic_bp_max', 140)
        dia_min = thresholds.get('diastolic_bp_min', 60)
        dia_max = thresholds.get('diastolic_bp_max', 90)
        
        if systolic < sys_min or diastolic < dia_min:
            alerts.append({...})
        elif systolic > sys_max or diastolic > dia_max:
            severity = 'critical' if systolic > 180 or diastolic > 120 else 'high'
            alerts.append({...})
    
    # Save alerts to database
    for alert_data in alerts:
        alert_id = self.database.save_alert(
            patient_id=patient_id,
            alert_type=alert_data['type'],
            severity=alert_data['severity'],
            message=alert_data['message'],
            health_record_id=record_id,
            metadata={'value': alert_data['value']}
        )
        
        # TTS warning for high/critical severity
        if alert_data['severity'] in ('high', 'critical'):
            self.speak_text(alert_data['message'], force=True)
```

**✅ Strengths:**
- Comprehensive threshold checking (HR, SpO2, Temp, BP)
- Dynamic severity levels (critical/high/medium/low)
- Links alerts to health_record_id (foreign key)
- Auto-triggers TTS for critical alerts
- Stores metadata for tracking

**⚠️ Issues:**
- Thresholds hard-coded as fallback (should be from patient_thresholds table)
- No alert deduplication (multiple alerts for same condition)
- No alert acknowledgment workflow in GUI
- TTS could be annoying if multiple alerts triggered

---

### **STEP 6: History Loading (HistoryScreen)**

**File:** `src/gui/history_screen.py` (lines 480-540)

**Logic:**
```python
def _load_records(self):
    """Load records based on current filter (today/week/month)"""
    # Clear existing widgets
    self.records_list.clear_widgets()
    
    # Get date range
    now = datetime.now()
    if self.current_filter == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif self.current_filter == 'week':
        start_date = now - timedelta(days=7)
    elif self.current_filter == 'month':
        start_date = now - timedelta(days=30)
    else:
        start_date = None
    
    # Call main_app to fetch records
    records = self.app_instance.get_history_records(start_date, now, limit=200)
    
    if not records:
        # Show "No data" message
        no_records_card = MDCard(...)
        self.records_list.add_widget(no_records_card)
    else:
        # Add record widgets
        for record in records:
            record_widget = MeasurementRecord(record)
            self.records_list.add_widget(record_widget)
```

**Delegates to `main_app.get_history_records()`:**

**File:** `src/gui/main_app.py` (lines 844-900)

```python
def get_history_records(self, start_date, end_date, limit=100):
    """Fetch historical measurement records from database"""
    try:
        if self.database and hasattr(self.database, 'get_health_records'):
            # Use DatabaseManager
            records = self.database.get_health_records(
                patient_id=self.config_data.get('patient', {}).get('id', 'patient_001'),
                start_date=start_date,
                end_date=end_date,
                limit=limit
            )
            
            # Convert SQLAlchemy objects to dicts
            return [
                {
                    'timestamp': r.timestamp,
                    'heart_rate': r.heart_rate,
                    'spo2': r.spo2,
                    'temperature': r.temperature,
                    'systolic': r.systolic_bp,
                    'diastolic': r.diastolic_bp,
                    'alert': r.alerts[0].message if r.alerts else None
                }
                for r in records
            ]
        else:
            # Fallback to local vitals.db
            return self._load_from_local_vitals(start_date, end_date, limit)
            
    except Exception as e:
        self.logger.error(f"Database history retrieval failed: {e}")
        return []
```

**✅ Strengths:**
- Filter by date range (today/week/month)
- Fallback to local vitals.db if DatabaseManager unavailable
- Displays alerts inline with records
- Material Design UI with color-coded values

**⚠️ Issues:**
- **CRITICAL:** Hard-coded `patient_id` from config (same issue as save)
- No pagination (limit=200 could be slow for large datasets)
- No sorting options (only by date descending)
- No search/filter by vital sign type
- Alert display only shows first alert (what if multiple?)

---

## ⚠️ CRITICAL ISSUES FOUND

### 🔴 **ISSUE #1: Hard-coded Patient ID**

**Location:** 
- `src/gui/main_app.py` line 920
- `src/gui/main_app.py` line 851

**Problem:**
```python
# Hard-coded from config - không dynamic
patient_id = self.config_data.get('patient', {}).get('id', 'patient_001')
```

**Impact:**
- Không thể switch giữa nhiều patients trong GUI
- Multi-patient support không khả thi
- Production deployment sẽ cần manual config edit

**Solution:**
```python
# Option 1: Patient selection screen
class PatientSelectionScreen(Screen):
    def select_patient(self, patient_id):
        self.app_instance.current_patient_id = patient_id
        # Switch to dashboard

# Option 2: Settings screen patient selector
class SettingsScreen(Screen):
    def update_current_patient(self, patient_id):
        self.app_instance.current_patient_id = patient_id
        self.app_instance.config_data['patient']['id'] = patient_id

# Update main_app.py
def save_measurement_to_database(self, measurement_data):
    # Use dynamic patient_id
    patient_id = getattr(self, 'current_patient_id', 
                         self.config_data.get('patient', {}).get('id', 'patient_001'))
```

---

### 🟡 **ISSUE #2: No Data Validation**

**Location:** 
- `src/gui/main_app.py` (save_measurement_to_database)
- All measurement screens (before calling save)

**Problem:**
```python
# No validation - accepts any value
health_data = {
    'heart_rate': measurement_data.get('heart_rate'),  # Could be 0, 999, negative, None
    'spo2': measurement_data.get('spo2'),  # Could be 150, -10, etc.
}
```

**Impact:**
- Invalid data persisted to database
- Cloud sync propagates garbage data
- Analytics/trends skewed by outliers
- Alert system triggers on invalid values

**Solution:**
```python
class HealthDataValidator:
    """Validate health measurement data before saving"""
    
    VALID_RANGES = {
        'heart_rate': (30, 250),      # BPM
        'spo2': (50, 100),             # Percentage
        'temperature': (30.0, 45.0),   # Celsius
        'systolic_bp': (50, 250),      # mmHg
        'diastolic_bp': (30, 150),     # mmHg
    }
    
    @classmethod
    def validate(cls, measurement_data: Dict) -> Tuple[bool, List[str]]:
        """
        Validate measurement data
        Returns: (is_valid, list_of_errors)
        """
        errors = []
        
        for field, (min_val, max_val) in cls.VALID_RANGES.items():
            value = measurement_data.get(field)
            if value is not None and value > 0:
                if not (min_val <= value <= max_val):
                    errors.append(
                        f"{field}: {value} ngoài phạm vi hợp lệ ({min_val}-{max_val})"
                    )
        
        # Timestamp validation
        ts = measurement_data.get('timestamp')
        if ts:
            if isinstance(ts, (int, float)):
                # Check not too far in future/past
                now = time.time()
                if ts > now + 60 or ts < now - 86400*7:  # ±1 min future, ±7 days past
                    errors.append(f"timestamp: {ts} không hợp lệ")
        
        return (len(errors) == 0, errors)

# Usage in main_app.py
def save_measurement_to_database(self, measurement_data):
    # Validate before saving
    is_valid, errors = HealthDataValidator.validate(measurement_data)
    if not is_valid:
        self.logger.warning(f"Invalid measurement data: {errors}")
        # Show error to user
        self._show_validation_error(errors)
        return
    
    # Continue with save...
```

---

### 🟡 **ISSUE #3: No User Feedback on Save**

**Location:** All measurement screens

**Problem:**
```python
# Silent save - user doesn't know if successful
self.app_instance.save_measurement_to_database(measurement_data)
self.logger.info("Đã lưu kết quả...")  # Only in logs
```

**Impact:**
- User uncertainty (was data saved?)
- No indication if cloud sync fails
- Poor UX for production system

**Solution:**
```python
# Add toast/snackbar notification
from kivymd.uix.snackbar import Snackbar

def save_measurement_to_database(self, measurement_data):
    try:
        # ... existing save logic ...
        record_id = self.database.save_health_record(health_data)
        
        if record_id:
            # Success feedback
            self._show_save_success(record_id)
        else:
            # Failure feedback
            self._show_save_error("Không thể lưu dữ liệu")
            
    except Exception as e:
        self.logger.error(f"Save failed: {e}")
        self._show_save_error(f"Lỗi: {str(e)}")

def _show_save_success(self, record_id: int):
    """Show success notification"""
    Snackbar(
        text=f"✅ Đã lưu kết quả (ID: {record_id})",
        snackbar_x="10dp",
        snackbar_y="10dp",
        duration=2,
        bg_color=(0.0, 0.68, 0.57, 1)
    ).open()

def _show_save_error(self, message: str):
    """Show error notification"""
    Snackbar(
        text=f"❌ {message}",
        snackbar_x="10dp",
        snackbar_y="10dp",
        duration=3,
        bg_color=(0.96, 0.4, 0.3, 1)
    ).open()
```

---

### 🟡 **ISSUE #4: Alert Deduplication Missing**

**Location:** `src/gui/main_app.py` (_check_and_create_alert)

**Problem:**
```python
# Always creates new alerts - no check for existing unresolved alerts
for alert_data in alerts:
    alert_id = self.database.save_alert(...)  # Creates duplicate every time
```

**Impact:**
- Same alert created multiple times for same condition
- Database bloated with duplicate alerts
- User annoyed by repeated TTS warnings

**Solution:**
```python
def _check_and_create_alert(self, patient_id, health_data, record_id):
    # ... threshold checking logic ...
    
    for alert_data in alerts:
        # Check if similar unresolved alert exists
        existing_alert = self.database.get_unresolved_alert(
            patient_id=patient_id,
            alert_type=alert_data['type'],
            within_hours=1  # Within last 1 hour
        )
        
        if existing_alert:
            self.logger.debug(
                f"Skipping duplicate alert: {alert_data['type']} "
                f"(existing alert_id={existing_alert.id})"
            )
            continue
        
        # Create new alert only if no existing one
        alert_id = self.database.save_alert(...)
        
        # TTS only for NEW alerts
        if alert_data['severity'] in ('high', 'critical'):
            self.speak_text(alert_data['message'], force=True)
```

---

### 🟢 **ISSUE #5: History Pagination Missing**

**Location:** `src/gui/history_screen.py` (_load_records)

**Problem:**
```python
# Hard limit 200 - no pagination
records = self.app_instance.get_history_records(start_date, now, limit=200)
```

**Impact:**
- Slow loading for large datasets
- Memory issues if too many records
- Poor UX for long-term usage

**Solution:**
```python
class HistoryScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_page = 0
        self.page_size = 50
        self.total_records = 0
    
    def _load_records(self):
        # Load one page at a time
        offset = self.current_page * self.page_size
        records = self.app_instance.get_history_records(
            start_date, now, 
            limit=self.page_size, 
            offset=offset
        )
        
        # Get total count
        self.total_records = self.app_instance.get_history_count(start_date, now)
        
        # Update pagination controls
        self._update_pagination_controls()
    
    def _next_page(self):
        if (self.current_page + 1) * self.page_size < self.total_records:
            self.current_page += 1
            self._load_records()
    
    def _prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._load_records()
```

---

## ✅ RECOMMENDATIONS

### **Priority 1: Critical Fixes (Làm ngay)**

1. **Fix Hard-coded Patient ID**
   - Add `current_patient_id` attribute to main_app
   - Update save/load methods to use dynamic patient_id
   - Add patient selector in settings screen

2. **Add Data Validation**
   - Create `HealthDataValidator` class
   - Validate before saving to database
   - Show validation errors to user

3. **Add User Feedback**
   - Success/error toast notifications
   - Cloud sync status indicator
   - Progress bar for long operations

### **Priority 2: Enhancements (Làm sau)**

4. **Alert Deduplication**
   - Check for existing unresolved alerts
   - Skip duplicate alert creation
   - Add alert resolution workflow in GUI

5. **History Pagination**
   - Implement page-based loading
   - Add prev/next buttons
   - Show page count (e.g., "Page 1 of 5")

6. **Search & Filter**
   - Search by vital sign type
   - Filter by alert status
   - Sort by multiple columns

### **Priority 3: Advanced Features (Optional)**

7. **Data Export**
   - Implement CSV/JSON export
   - PDF report generation
   - Email/share functionality

8. **Statistics Dashboard**
   - Average/min/max calculations
   - Trend charts (HR/SpO2/Temp over time)
   - Alert frequency analysis

9. **Multi-patient Support**
   - Patient selection screen
   - Switch between patients
   - Patient profile management

---

## 📝 TESTING CHECKLIST

### **Database Workflow Tests**

- [ ] **Save Measurement (Heart Rate)**
  - Measure HR/SpO2 → Save button → Check SQLite record
  - Verify cloud sync (check MySQL table)
  - Check alert created if threshold exceeded

- [ ] **Save Measurement (Temperature)**
  - Measure temperature → Save → Check database
  - Verify metadata (ambient_temp, measurement_type)
  - Check alert if temp > 37.5°C or < 36.0°C

- [ ] **Save Measurement (Blood Pressure)**
  - Measure BP → Save → Check database
  - Verify SYS/DIA/MAP values
  - Check alert if BP > 140/90 or < 90/60

- [ ] **History Loading**
  - Open history screen → Verify records displayed
  - Test filters: today/week/month
  - Check alert indicators on records

- [ ] **Cloud Sync**
  - Save measurement → Wait 5-10s → Check MySQL table
  - Disconnect network → Save → Reconnect → Verify sync
  - Check sync statistics in monitoring dashboard

- [ ] **Alert System**
  - Create measurement with high HR (>120) → Verify alert created
  - Check TTS triggers for critical alerts
  - Verify alert linked to health_record_id

---

## 🚀 NEXT STEPS

### **Immediate Actions:**

1. **Test Current Workflow End-to-End:**
   ```bash
   # 1. Clear databases
   rm data/health_monitor.db
   mysql -u danhsidoi -p iot_health_cloud -e "TRUNCATE health_records; TRUNCATE alerts;"
   
   # 2. Run GUI
   python3 main.py
   
   # 3. Perform measurements:
   #    - Heart Rate: 75 BPM, SpO2 98%
   #    - Temperature: 37.2°C
   #    - Blood Pressure: 125/82
   
   # 4. Check SQLite
   sqlite3 data/health_monitor.db "SELECT * FROM health_records;"
   sqlite3 data/health_monitor.db "SELECT * FROM alerts;"
   
   # 5. Wait 5 minutes (auto-sync)
   # 6. Check MySQL
   mysql -u danhsidoi -p iot_health_cloud -e "SELECT * FROM health_records;"
   
   # 7. Check monitoring dashboard
   python3 scripts/monitoring_dashboard.py
   ```

2. **Implement Critical Fixes:**
   - Add `HealthDataValidator` class
   - Add toast notifications for save success/failure
   - Fix hard-coded patient_id (add dynamic selection)

3. **Update Documentation:**
   - Document database schema (tables, relationships)
   - Document alert thresholds (configurable?)
   - Document cloud sync behavior (retry, interval)

---

## 📚 RELATED FILES

### **Core Workflow Files:**
- `src/gui/main_app.py` - Central save/load logic
- `src/data/database.py` - DatabaseManager with SQLAlchemy
- `src/communication/cloud_sync_manager.py` - Cloud sync to MySQL
- `src/communication/sync_scheduler.py` - Auto-sync background thread

### **GUI Screens:**
- `src/gui/heart_rate_screen.py` - HR/SpO2 measurement
- `src/gui/temperature_screen.py` - Temperature measurement
- `src/gui/bp_measurement_screen.py` - Blood pressure measurement
- `src/gui/history_screen.py` - Historical records display

### **Configuration:**
- `config/app_config.yaml` - Patient ID, thresholds, cloud sync settings

### **Monitoring:**
- `scripts/monitoring_dashboard.py` - Real-time sync monitoring
- `scripts/create_monitoring_views.sql` - MySQL views for dashboard

---

**Prepared by:** GitHub Copilot  
**Date:** November 5, 2025  
**Status:** ANALYSIS COMPLETE - READY FOR FIXES 🔧
