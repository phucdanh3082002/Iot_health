# 🚀 PHASE 3 ROADMAP - HARDWARE INTEGRATION & PRODUCTION

**Ngày:** 5 Tháng 11, 2025  
**Trạng thái Phase 2:** ✅ HOÀN THÀNH 100%

---

## 📊 TỔNG QUAN PHASE 2 (COMPLETED)

### ✅ Đã hoàn thành:
1. **MySQL Cloud Database**
   - 8 tables với partitioning (YEAR-based)
   - Indexes, foreign keys, constraints
   - Schema version 1.4 deployed successfully
   
2. **Cloud Sync Infrastructure**
   - `CloudSyncManager` (750+ lines)
   - Bidirectional sync: SQLite ↔ MySQL
   - Store & Forward mechanism
   - Conflict resolution (cloud wins)
   
3. **Auto-Sync System**
   - `SyncScheduler` background thread
   - Auto-sync every 300s
   - Graceful shutdown handling
   - Transaction timing fixed
   
4. **Monitoring Dashboard**
   - Python script `monitoring_dashboard.py`
   - 10 MySQL views (system status, device health, sync performance, errors, alerts, data quality)
   - Health check automation
   
5. **Full Test Suite**
   - 6/6 tests passing
   - Coverage: health records, alerts, calibrations, full/incremental sync
   - Device registration verified

### 📈 Metrics:
- Cloud connection: `192.168.2.15:3306` ✅
- Device ID: `rasp_pi_001` ✅
- Auto-sync interval: 300s ✅
- Data synced: Health records, alerts, sensor calibrations ✅

---

## 🎯 PHASE 3: MỤC TIÊU & PHẠM VI

### 🔬 Mục tiêu chính:
1. **Hardware Integration** - Tích hợp cảm biến thật vào hệ thống
2. **GUI Enhancement** - Hoàn thiện giao diện Kivy với real sensors
3. **Blood Pressure System** - Hoàn chỉnh hệ thống đo huyết áp (HX710B + bơm/van)
4. **Production Ready** - Chuẩn bị triển khai thực tế (security, backup, monitoring)

### 📦 Deliverables:
- ✅ Sensors hoạt động ổn định với hardware thật
- ✅ GUI hiển thị real-time data từ sensors
- ✅ Blood pressure measurement hoàn chỉnh & calibrated
- ✅ Production deployment package (security, backup, monitoring)

---

## 🛠️ PHASE 3: ROADMAP CHI TIẾT

### **TRACK 1: HARDWARE VALIDATION & INTEGRATION** (Ưu tiên cao)

#### 1.1 Kiểm tra Hardware hiện tại
**File liên quan:** `tests/test_sensors.py`, `src/sensors/*.py`

**Công việc:**
- [ ] Chạy I²C scan kiểm tra MAX30102 (0x57) và MLX90614 (0x5A)
- [ ] Test MAX30102: finger detection, HR/SpO2 reading
- [ ] Test MLX90614: object/ambient temperature
- [ ] Test HX710B: GPIO6 (DOUT), GPIO5 (SCK) - raw counts reading
- [ ] Test bơm/van: GPIO26 (pump), GPIO16 (valve) via optocoupler

**Lệnh test:**
```bash
cd /home/pi/Desktop/IoT_health
python3 tests/test_sensors.py
# Menu: 1 (I2C scan), 2 (MAX30102), 3 (MLX90614), 4 (HX710B), 5 (Pump/Valve)
```

**Kết quả mong đợi:**
- MAX30102 phát hiện được ngón tay, đọc HR (60-100 bpm), SpO2 (95-100%)
- MLX90614 đọc nhiệt độ vật (35-37.5°C), môi trường (~25°C)
- HX710B đọc counts (pressure), không timeout
- Bơm/van điều khiển được qua GPIO

**Action items:**
```bash
# 1. Scan I2C
python3 -c "import smbus; bus=smbus.SMBus(1); print([hex(x) for x in range(3,120) if not bus.read_byte(x) or True])"

# 2. Test sensors
python3 tests/test_sensors.py

# 3. Check GPIO states
gpio readall
```

---

#### 1.2 Calibration & Data Quality
**File liên quan:** `tests/bp_calib_tool.py`, `tests/calibrate_offset.py`, `config/app_config.yaml`

**Công việc:**
- [ ] HX710B calibration: offset + slope (counts → mmHg)
- [ ] MAX30102: verify IR threshold, LED amplitude
- [ ] MLX90614: temperature offset correction
- [ ] Lưu calibration data vào MySQL qua `CloudSyncManager.push_sensor_calibration()`

**Calibration workflow:**
```bash
# HX710B offset (no pressure)
python3 tests/calibrate_offset.py

# HX710B slope (với reference pressure)
python3 tests/bp_calib_tool.py
```

**Cập nhật config:**
```yaml
sensors:
  hx710b:
    calibration:
      offset_counts: [VALUE từ test]
      slope_mmhg_per_count: [VALUE từ test]
```

---

#### 1.3 Blood Pressure System Integration
**File liên quan:** 
- `src/sensors/hx710b_driver.py` (HX710B bit-bang driver)
- `src/sensors/hx710b_sensor.py` (Sensor wrapper)
- `src/sensors/blood_pressure_sensor.py` (BP measurement logic)
- `tests/test_full_bp_measurement.py`

**Công việc:**
- [ ] Verify HX710B driver: non-blocking, thread-safe
- [ ] Test inflate phase: pump ON, target 165 mmHg, soft limit 200 mmHg
- [ ] Test deflate phase: PWM valve control, 3 mmHg/s rate
- [ ] Test oscillometric detection: bandpass filter 0.5-5 Hz, envelope extraction
- [ ] Estimate SYS/DIA/MAP: MAP at max amplitude, SYS at 55%, DIA at 80%
- [ ] Safety checks: emergency stop, relief valve, timeout

**Test workflow:**
```bash
# Full BP measurement test
python3 tests/test_full_bp_measurement.py

# Bơm/van manual control
python3 tests/test_bom_van.py
```

**Expected output:**
```
✅ Inflate: 0 → 165 mmHg (25s)
✅ Deflate: 165 → 40 mmHg (40s, 3 mmHg/s)
✅ Oscillations detected: 15-20 peaks
✅ MAP: ~95 mmHg (max amplitude)
✅ SYS: ~135 mmHg (55% ratio)
✅ DIA: ~85 mmHg (80% ratio)
```

**Safety checklist:**
- Emergency stop nếu pressure > 200 mmHg
- Timeout inflate (25s), deflate (90s)
- NO valve default state (xả khi mất nguồn)
- Relief valve ~300 mmHg (cơ khí)

---

### **TRACK 2: GUI ENHANCEMENT** (Ưu tiên trung bình)

#### 2.1 Real Sensor Integration vào Kivy GUI
**File liên quan:**
- `src/gui/main_app.py` (Main Kivy app)
- `src/gui/dashboard_screen.py` (Dashboard với 3 khối sensor)
- `src/gui/heart_rate_screen.py` (HR/SpO2 detail screen)
- `src/gui/temperature_screen.py` (Temperature detail screen)
- `src/gui/bp_measurement_screen.py` (BP measurement screen)

**Công việc:**
- [ ] Thay mock data bằng real sensor callbacks
- [ ] Dashboard: update HR/SpO2/Temp real-time từ MAX30102/MLX90614
- [ ] Heart Rate Screen: animation gauge theo HR thực, SpO2 progress bar
- [ ] Temperature Screen: thermometer widget theo temp thực
- [ ] BP Screen: progress bar inflate/deflate, oscillation waveform, final result

**Code changes:**
```python
# main_app.py - thay mock bằng real sensors
def on_start(self):
    # Initialize sensors
    self.max30102 = MAX30102Sensor(self.config['sensors']['max30102'])
    self.mlx90614 = MLX90614Sensor(self.config['sensors']['mlx90614'])
    self.bp_sensor = BloodPressureSensor(self.config['sensors']['blood_pressure'])
    
    # Set callbacks
    self.max30102.set_data_callback(self.on_hr_spo2_data)
    self.mlx90614.set_data_callback(self.on_temp_data)
    
    # Start sensors
    self.max30102.start()
    self.mlx90614.start()

def on_hr_spo2_data(self, data):
    # Update dashboard
    self.dashboard_screen.update_hr(data['heart_rate'])
    self.dashboard_screen.update_spo2(data['spo2'])
    self.dashboard_screen.update_quality(data['signal_quality'])
```

**GUI features to implement:**
- Real-time data update (Kivy Clock.schedule_interval)
- Signal quality indicator (color-coded: green/yellow/red)
- Finger detection status (MAX30102)
- Alert popup khi vượt ngưỡng (AlertSystem integration)
- TTS feedback (PiperTTS integration)

---

#### 2.2 TTS Integration
**File liên quan:** `src/utils/tts_manager.py`, `config/app_config.yaml`

**Công việc:**
- [ ] Verify PiperTTS model path: `/home/pi/piper_models/vi_VN-vais1000-medium.onnx`
- [ ] Test audio output qua MAX98357A I²S (GPIO18/19/21)
- [ ] Integration vào alerts: "Nhịp tim cao 120 bpm", "Nhiệt độ thấp 35.5°C"
- [ ] BP measurement feedback: "Đang bơm", "Đang đo", "Kết quả 135/85"

**Test TTS:**
```bash
python3 tests/test_speak.py
```

**Config verify:**
```yaml
audio:
  tts_engine: piper
  piper:
    model_path: /home/pi/piper_models/vi_VN-vais1000-medium.onnx
    config_path: /home/pi/piper_models/vi_VN-vais1000-medium.onnx.json
```

---

### **TRACK 3: PRODUCTION DEPLOYMENT** (Ưu tiên thấp, làm sau)

#### 3.1 Security Hardening

**Công việc:**
- [ ] Tạo MySQL user `iot_sync_user` với privileges giới hạn:
  ```sql
  CREATE USER 'iot_sync_user'@'192.168.2.%' IDENTIFIED BY 'strong_password';
  GRANT SELECT, INSERT, UPDATE ON iot_health_cloud.* TO 'iot_sync_user'@'192.168.2.%';
  FLUSH PRIVILEGES;
  ```
- [ ] Update `config/app_config.yaml`: `user: iot_sync_user`, `password_env: MYSQL_SYNC_PASSWORD`
- [ ] SSL/TLS (optional):
  ```yaml
  cloud:
    mysql:
      ssl_enabled: true
      ssl_ca: /path/to/ca-cert.pem
  ```

---

#### 3.2 Backup & Recovery

**Công việc:**
- [ ] MySQL automated backup script:
  ```bash
  # Backup daily at 2 AM
  0 2 * * * mysqldump -u root -p iot_health_cloud > /backup/iot_health_$(date +\%Y\%m\%d).sql
  ```
- [ ] SQLite local backup:
  ```bash
  # Backup hourly
  0 * * * * cp /home/pi/Desktop/IoT_health/data/health_monitor.db /backup/health_monitor_$(date +\%Y\%m\%d_\%H).db
  ```
- [ ] Recovery procedure documentation

---

#### 3.3 Monitoring & Alerts

**Công việc:**
- [ ] Setup cron job cho monitoring dashboard:
  ```bash
  # Check every 5 minutes
  */5 * * * * cd /home/pi/Desktop/IoT_health && python3 scripts/monitoring_dashboard.py >> logs/monitor.log 2>&1
  ```
- [ ] Email/SMS alerts khi critical errors (optional):
  ```python
  # In monitoring_dashboard.py
  health = dashboard.get_health_check()
  if health['status'] == 'critical':
      send_alert_email(health['errors'])
  ```
- [ ] Grafana/Prometheus integration (advanced, optional)

---

#### 3.4 System Service Setup

**Công việc:**
- [ ] Tạo systemd service để auto-start:
  ```bash
  # /etc/systemd/system/iot-health.service
  [Unit]
  Description=IoT Health Monitor
  After=network.target
  
  [Service]
  Type=simple
  User=pi
  WorkingDirectory=/home/pi/Desktop/IoT_health
  ExecStart=/usr/bin/python3 /home/pi/Desktop/IoT_health/main.py
  Restart=on-failure
  RestartSec=10
  
  [Install]
  WantedBy=multi-user.target
  ```
- [ ] Enable service:
  ```bash
  sudo systemctl daemon-reload
  sudo systemctl enable iot-health.service
  sudo systemctl start iot-health.service
  ```

---

## 📅 TIMELINE ƯỚC LƯỢNG

### Week 1: Hardware Validation (5-7 ngày)
- Day 1-2: I²C scan, MAX30102/MLX90614 testing
- Day 3-4: HX710B calibration, bơm/van testing
- Day 5-7: Full BP measurement testing & debugging

### Week 2: GUI Integration (5-7 ngày)
- Day 1-2: Real sensor callbacks vào dashboard
- Day 3-4: Detail screens (HR, Temp, BP)
- Day 5-7: TTS integration, alert system

### Week 3: Production Prep (3-5 ngày, optional)
- Day 1-2: Security (MySQL user, SSL/TLS)
- Day 3-4: Backup automation, monitoring
- Day 5: System service setup, documentation

**Total estimate:** 13-19 ngày (2-3 tuần)

---

## 🚦 NEXT ACTIONS (IMMEDIATE)

### 🔥 Priority 1: Hardware Validation
```bash
# 1. Test sensors ngay
cd /home/pi/Desktop/IoT_health
python3 tests/test_sensors.py

# 2. Kiểm tra kết quả
# - MAX30102: HR/SpO2 đọc được?
# - MLX90614: Temperature đọc được?
# - HX710B: Counts/pressure đọc được?
# - Bơm/van: GPIO điều khiển được?

# 3. Report issues
# - List sensors hoạt động
# - List sensors có vấn đề
# - Error logs từ logs/test_sensors.log
```

### 🔥 Priority 2: Calibration (nếu sensors OK)
```bash
# HX710B offset
python3 tests/calibrate_offset.py

# HX710B slope (với reference)
python3 tests/bp_calib_tool.py

# Update config/app_config.yaml với values mới
```

### 🔥 Priority 3: Full BP Test (nếu calibration OK)
```bash
# Test đo huyết áp hoàn chỉnh
python3 tests/test_full_bp_measurement.py

# Verify:
# - Inflate smooth đến 165 mmHg
# - Deflate controlled 3 mmHg/s
# - Oscillations detected
# - SYS/DIA/MAP reasonable (e.g., 120/80/93)
```

---

## ❓ QUYẾT ĐỊNH CẦN USER INPUT

### 1. **Hardware Status**
   - ❓ Tất cả sensors đã kết nối chưa? (MAX30102, MLX90614, HX710B, bơm/van)
   - ❓ Cuff, ống khí đã setup đúng chưa?
   - ❓ Power supply 6V cho bơm/van đã sẵn sàng?

### 2. **Scope Phase 3**
   - ❓ Ưu tiên hardware integration trước hay GUI enhancement?
   - ❓ Production deployment (security, backup) có cần làm ngay không?
   - ❓ Timeline mong muốn: 2 tuần hay 3 tuần?

### 3. **Testing Approach**
   - ❓ Test từng sensor riêng lẻ trước, hay test tích hợp luôn?
   - ❓ BP measurement: test với cuff thật hay dùng dummy load (bóng khí)?

---

## 📝 CHECKLIST HOÀN THÀNH PHASE 3

### Track 1: Hardware
- [ ] I²C scan pass (MAX30102 0x57, MLX90614 0x5A detected)
- [ ] MAX30102: HR/SpO2 đọc chính xác
- [ ] MLX90614: Temperature đọc chính xác
- [ ] HX710B: Pressure đọc chính xác (after calibration)
- [ ] Bơm/van: Điều khiển ổn định
- [ ] Full BP measurement: SYS/DIA/MAP accuracy ±10 mmHg

### Track 2: GUI
- [ ] Dashboard real-time update từ sensors
- [ ] Heart Rate Screen: animation + real data
- [ ] Temperature Screen: thermometer + real data
- [ ] BP Screen: inflate/deflate progress + waveform
- [ ] TTS alerts hoạt động (PiperTTS)
- [ ] Alert system trigger đúng thresholds

### Track 3: Production
- [ ] MySQL user `iot_sync_user` created
- [ ] Backup automation setup
- [ ] Monitoring dashboard running
- [ ] System service enabled
- [ ] Documentation complete

---

## 📚 REFERENCES

### Documentation
- `/home/pi/Desktop/IoT_health/README.md` - Project overview
- `/home/pi/Desktop/IoT_health/.github/copilot-instructions.md` - Development guidelines
- `/home/pi/Desktop/IoT_health/docs/DATABASE_IMPLEMENTATION.md` - Cloud sync architecture

### Key Files
- `tests/test_sensors.py` - Hardware validation
- `src/sensors/blood_pressure_sensor.py` - BP measurement logic
- `src/gui/main_app.py` - GUI entry point
- `config/app_config.yaml` - Configuration
- `scripts/monitoring_dashboard.py` - Cloud monitoring

### External Resources
- MAX30102 datasheet
- MLX90614 datasheet
- HX710B datasheet
- Raspberry Pi GPIO pinout

---

**Prepared by:** GitHub Copilot  
**Date:** November 5, 2025  
**Status:** READY FOR PHASE 3 KICKOFF 🚀
