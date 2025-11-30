# Agent Instructions for IoT Health Monitor

This document provides guidelines for AI agents working on this codebase.

## 📜 General Rules
- **Follow existing conventions**: Adhere strictly to the code style, patterns, and instructions found in the codebase and in `.github/copilot-instructions.md`.
- **Language**: Respond in Vietnamese as specified in the instructions.
- **Safety**: Do not commit secrets. Use config files or environment variables. Validate all inputs.
- **File Structure**: Do not change the directory structure, API schemas (MQTT, REST), or database schemas without explicit permission.

## 🚀 Development Workflow
- **Dependencies**: Install dependencies from `requirements.txt` using `pip install -r requirements.txt`.
- **Linting**: Use `flake8` for checking style and `black` for formatting.
  - `flake8 .`
  - `black .`
- **Testing**: Use `pytest` to run tests.
  - Run all tests: `pytest`
  - Run a specific file: `pytest tests/test_database.py`
  - Run a single test function: `pytest tests/test_database.py::test_patient_operations`

## 💻 Code Style
- **Imports**: Group imports: 1. Standard library, 2. Third-party, 3. Source code.
- **Typing**: Use Python type hints for all function signatures (`def my_func(param: str) -> bool:`).
- **Naming**: `PascalCase` for classes, `snake_case` for functions and variables.
- **Error Handling**: Use `try...except` blocks for operations that can fail. Log errors using the `logging` module; avoid `print()`.
- **Docstrings**: Write clear docstrings for all public modules, classes, and functions.
# Copilot Instructions — IoT Health Monitor

## 🎯 Mục tiêu dự án

Hệ thống IoT giám sát sức khỏe trên Raspberry Pi:
- **Sensors**: MAX30102 (HR/SpO₂), MLX90614 (Temperature), HX710B (Blood Pressure)
- **Display**: Waveshare 3.5" LCD (480×320)
- **Audio**: MAX98357A I²S (TTS feedback)
- **Data**: SQLite local + MySQL cloud + **MQTT real-time**
- **UI**: Kivy/KivyMD (Pi) + Android App + Web Dashboard
- **TTS**: PiperTTS
- **OS**: Raspberry Pi OS Bookworm 64-bit
- **Communication**: **MQTT (primary)** for real-time + REST API (historical data)

---

Recent changes:
- Device-centric patient resolution: `patient_id` is no longer hardcoded. Devices publish using `device_id`; the cloud resolves `patient_id` via the devices/patients mapping and the local record may store `patient_id=NULL` until resolved by cloud sync.
- Cloud sync improvement: `sync_incremental()` now retries pending alerts and health records before delta-sync, preventing stuck pending items.
- Config guidance: Do not hardcode `patient_id` in `app_config.yaml`. Use environment variables for credentials; rely on cloud mapping for patient assignment.

## 📡 **MQTT COMMUNICATION ARCHITECTURE** (✅ CHỐT)

### **Broker Configuration**
```yaml
Broker: c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud (HiveMQ Cloud Singapore)
Port: 8883 (TLS required) / 8884 (WebSocket for web dashboard)
Protocol: MQTT v3.1.1
QoS Levels:
  - Vitals: QoS 1 (at least once)
  - Alerts: QoS 2 (exactly once)
  - Status: QoS 0 (fire and forget)
  - Commands: QoS 2 (exactly once)
```

### **Topic Structure (KHÔNG ĐỔI)**
```
iot_health/
├── device/{device_id}/
│   ├── vitals          # Pi → publish vitals (QoS 1)
│   ├── alerts          # Pi → publish alerts (QoS 2)
│   ├── status          # Pi → publish online/offline (QoS 0, retained)
│   └── commands        # Android/Web → subscribe commands (QoS 2)
│
└── patient/{patient_id}/
    ├── vitals          # Aggregate all devices for patient
    ├── alerts          # Aggregate alerts
    └── commands        # Android/Web → publish commands to Pi (QoS 2)
```

### **Message Payloads (JSON Schema - KHÔNG ĐỔI)**

#### **1. Vitals Payload** (Pi → Android/Web)
```json
{
  "timestamp": 1699518000.123,
  "device_id": "rpi_bp_001",
  "patient_id": "patient_001",
  "measurements": {
    "heart_rate": {
      "value": 78,
      "unit": "bpm",
      "valid": true,
      "metadata": {
        "signal_quality_index": 89.5,
        "peak_count": 18,
        "measurement_duration": 24.5
      }
    },
    "spo2": {
      "value": 97,
      "unit": "%",
      "valid": true,
      "metadata": {
        "cv": 1.8,
        "signal_quality": "good"
      }
    },
    "temperature": {
      "object_temp": 36.7,
      "ambient_temp": 24.2,
      "unit": "celsius"
    },
    "blood_pressure": {
      "systolic": 120,
      "diastolic": 80,
      "map": 93,
      "unit": "mmHg"
    }
  }
}
```

#### **2. Alert Payload** (Pi → Android/Web)
```json
{
  "timestamp": 1699518000.123,
  "device_id": "rpi_bp_001",
  "patient_id": "patient_001",
  "alert_type": "high_heart_rate",
  "severity": "high",
  "message": "Nhịp tim cao: 125 BPM (ngưỡng: 60-100)",
  "vital_sign": "heart_rate",
  "current_value": 125,
  "threshold_value": 100
}
```

#### **3. Status Payload** (Pi → Android/Web)
```json
{
  "timestamp": 1699518000.123,
  "device_id": "rpi_bp_001",
  "status": "online",
  "uptime_seconds": 86400,
  "battery_level": 85,
  "wifi_signal": -45
}
```

#### **4. Command Payload** (Android/Web → Pi)
```json
{
  "command_id": "cmd_1699518000",
  "timestamp": 1699518000.123,
  "issuer": "android_app",
  "command": "start_measurement",
  "parameters": {
    "measurement_type": "blood_pressure",
    "patient_id": "patient_001"
  }
}
```

### **Client Platform Requirements**

#### **Raspberry Pi (Python - Paho MQTT)**
- **Publisher**: Vitals (every 5s when measuring), Alerts (on threshold breach), Status (LWT)
- **Subscriber**: Commands từ Android/Web
- **Implementation**: `src/communication/mqtt_client.py` (✅ ĐÃ CÓ)
- **Auto-reconnect**: Exponential backoff (5s, 10s, 30s, 60s)
- **Store-forward**: Queue messages khi offline → gửi khi online

#### **Android App (Kotlin - Paho Android)**
- **Subscriber**: Vitals, Alerts, Status từ device(s) đã pair
- **Publisher**: Commands (start/stop measurement, set thresholds)
- **Cache**: Room DB cache vitals for offline viewing
- **Notification**: Push notification cho critical alerts
- **Implementation**: `MqttManager.kt` (⏳ CHỜ IMPLEMENT)

#### **Web Dashboard (JavaScript - MQTT.js)**
- **Subscriber**: Vitals, Alerts, Status từ tất cả devices
- **Publisher**: Commands (remote control, config updates)
- **Real-time Chart**: Live update chart khi nhận vitals
- **Alert Sound**: Browser notification + sound cho critical alerts
- **Implementation**: `mqtt-client.js` (⏳ CHỜ IMPLEMENT)

### **Security (Production)**
```yaml
TLS: Bắt buộc (port 8883)
Authentication: Username + password (per device)
Authorization: ACL rules:
  - Pi devices: PUBLISH vitals/alerts/status, SUBSCRIBE commands
  - Android/Web: SUBSCRIBE vitals/alerts/status, PUBLISH commands
  - Admin: Full access
Certificates: Let's Encrypt (HiveMQ Cloud managed)
```

### **QoS Strategy**
- **QoS 0 (Status)**: Không quan trọng nếu mất, sẽ có message tiếp theo
- **QoS 1 (Vitals)**: Đảm bảo nhận ít nhất 1 lần, chấp nhận duplicate
- **QoS 2 (Alerts/Commands)**: Exactly once, không duplicate, không mất

---

## ⚠️ QUY TẮC BẮT BUỘC

### 1. **Code Quality & Style**
- ✅ **OOP**: Dùng classes, inheritance, encapsulation
- ✅ **Comments**: Docstring cho mọi class/method (tiếng Việt hoặc tiếng Anh)
- ✅ **Organization**: Nhóm methods theo chức năng, thêm comment phân đoạn
- ✅ **PEP8**: Follow Python style guide
- ✅ **Type hints**: Dùng typing cho parameters và return values

### 2. **Documentation**
- ❌ **KHÔNG tạo file .md** (summary documentation,README, CHANGELOG, summary) nếu CHƯA được yêu cầu
- ❌ **KHÔNG tạo test files** tự động
- ✅ **Inline comments**: Giải thích logic phức tạp trong code
- ✅ **Hỏi lại** nếu không hiểu rõ yêu cầu

### 3. **Project Structure**
- ❌ **KHÔNG tạo dummy/mock data** (.wav, .json, sample files)
- ❌ **KHÔNG thay đổi cấu trúc thư mục** khi chỉ sửa code
- ❌ **KHÔNG thay đổi API/schema** (MQTT topics, REST endpoints, DB) mà không hỏi
- ✅ **Giữ nguyên** file paths, imports, dependencies hiện có

### 4. **Security**
- ❌ **KHÔNG commit secrets** (passwords, tokens, API keys)
- ✅ **Dùng** config files hoặc environment variables
- ✅ **Validate** user inputs

### 5. **Communication**
- ✅ **Trả lời bằng tiếng Việt** (có thể dùng thuật ngữ tiếng Anh kỹ thuật)
- ✅ **Hỏi lại** nếu yêu cầu không rõ ràng
- ✅ **Giải thích** lý do khi đề xuất thay đổi lớn
- ❌ **KHÔNG giả định** requirements nếu chưa được nói rõ

### 6. **Error Handling**
- ✅ **Try-except blocks**: Xử lý exceptions properly
- ✅ **Logging**: Dùng logger thay vì print()
- ✅ **Graceful degradation**: Fallback khi hardware fail
- ✅ **Meaningful messages**: Error messages giúp debug

### 7. **Performance**
- ✅ **Non-blocking**: Không làm treo UI (dùng threads/async khi cần)
- ✅ **Resource cleanup**: Close files, connections, sensors properly
- ✅ **Memory efficient**: Tránh memory leaks trong loops
- ❌ **KHÔNG optimize sớm**: Ưu tiên correctness trước performance

### 8. **Hardware Integration**
- ✅ **Safe defaults**: Sensor fail → hệ thống vẫn chạy
- ✅ **Calibration**: Dùng config files cho sensor calibration
- ✅ **Testing**: Hỏi user test trên hardware thật
- ❌ **KHÔNG giả định** hardware hoạt động hoàn hảo

---

## 📁 Cấu trúc thư mục (giữ nguyên)

```
config/               # app_config.yaml (ngưỡng, mqtt, 
)
data/                 # SQLite thực (không chứa dữ liệu giả)
logs/
src/
  ai/
  communication/      # mqtt_client, rest_client, store_forward
  data/               # database, models, processor
  gui/                # Kivy app/screens (480×320), TTS integration
  sensors/            # max30102_sensor, mlx90614_sensor, blood_pressure_sensor (HX710B)
  utils/
tests/                # chỉ thêm test khi có yêu cầu; không tạo dữ liệu giả
main.py
README.md
requirements.txt


---

## 🛠️ Phần cứng đã chốt

* **Raspberry Pi 4B sử dụng pi os bookworm 64 bit**, **Waveshare 3.5" SPI** (fbcp mirror).
* **Âm thanh**: **MAX98357A I²S** (BCLK=GPIO18, LRCLK=GPIO19, DIN=GPIO21) → loa 3–5 W / 4–8 Ω (BTL OUT+ / OUT−; không nối loa xuống GND).
* **Cảm biến**:
  * **MAX30102 (I²C 0x57)**: HR/SpO₂.
  * **MLX90614/GY-906 (I²C 0x5A)**: Nhiệt độ.
  * **Huyết áp**: Cảm biến 0–40 kPa **+ HX710B (24-bit, 2 dây DOUT/SCK, không I²C)**.
* **Khí nén**: Cuff; **bơm 5/12 V**; **van xả NO**; **van relief ~300 mmHg**.
* **Driver công suất**: MOSFET + diode flyback + opto; nguồn riêng cho bơm/van; GND chung.
---

## Gợi ý chân GPIO (tham khảo, không thay nếu chưa có yêu cầu)

| Khối      | Tín hiệu           | GPIO (Pin)                    |
| --------- | ------------------ | ----------------------------- |
| HX710B    | DOUT (in)          | GPIO17 (6)                   |
| HX710B    | SCK  (out)         | GPIO5 (5)                    |
| I²S       | BCLK / LRCLK / DIN | 18 (12) / 19 (35) / 21 (40)   |
| I²C       | SDA / SCL          | 2 (3) / 3 (5)                 |
| Bơm / Van | EN                 | Bơm (GPIO 26), Van (GPIO 16) → (opto) → MOSFET |

> HX710B **cấp 3.3 V** để tương thích mức logic GPIO. DOUT có thể cần pull-up nếu board không tích hợp.

---

## 🔬 Yêu cầu kỹ thuật cho **HX710B** (quan trọng)

* **Không phải I²C**. Giao tiếp kiểu **bit-bang** 2 dây: **DOUT** (data ready) và **SCK** (clock/PD).
* **Tốc độ lấy mẫu (SPS)**: phụ thuộc chế độ/board; nhiều module nằm khoảng **10–80 SPS**.
* **Yêu cầu dự án**:
  * Thu **áp cuff** tin cậy trong pha xả (để xác định **MAP** và ước lượng **SYS/DIA** bằng tỷ lệ).
  * Nếu SPS < 100, **envelope dao động** sẽ thưa → chấp nhận độ chính xác SYS/DIA **kém hơn**; **không** tự ý đổi phần cứng.
* **Driver yêu cầu**:
  * Non-blocking: **không** khóa UI thread; dùng thread riêng / asyncio + Queue.
  * **Debounce/timeout** khi chờ DOUT "data ready".
  * **Average/median** nhẹ để giảm nhiễu, **không** làm mờ dao động quá mức.
  * Trả về **counts** (int) kèm timestamp; chuyển đổi sang **mmHg** qua **calibration** (offset/slope).

---


## 💻 Yêu cầu phần mềm (Copilot phải tuân thủ)

### **Raspberry Pi (Python)**
1. **GUI Kivy 480×320** (fullscreen borderless): Dashboard (HR/SpO₂/Temp/BP), đo BP, lịch sử, cài đặt; **không block** UI.
2. **Driver HX710B**: bit-banged, **thread-safe**, non-blocking; API rõ ràng:
   * `start() / stop()` theo pattern BaseSensor;
   * `set_data_callback()` push vào callback `{ts, counts, pressure_mmhg}`;
   * timeout khi không có data-ready; xử lý lỗi gọn.
3. **Chuyển đổi áp**: lớp xử lý ánh xạ `counts → mmHg` qua **calibration** (offset/slope) lấy từ config; **không hardcode**.
4. **Thu pha xả**: đảm bảo tần suất đọc theo khả năng HX710B (10–80 SPS), **đo thời gian chuẩn** để tính mmHg/s.
5. **Cảnh báo**: popup + **TTS** (PiperTTS) + **MQTT publish alert**; **debounce** alert.
6. **MQTT Client**: 
   * Publish vitals (QoS 1, every 5s khi đo) + alerts (QoS 2) + status (QoS 0, LWT)
   * Subscribe commands từ Android/Web (QoS 2)
   * Auto-reconnect với exponential backoff
   * Store-forward queue khi offline
   * **KHÔNG ĐỔI** topics/payloads đã định nghĩa
7. **MySQL Sync**: CloudSyncManager auto-sync mỗi 5 phút (batch 100 records)
8. **SQLite**: ghi `ts, hr, spo2, temp, bp_sys, bp_dia, bp_map, alert, hr_sqi, spo2_cv, peak_count, measurement_duration`; **không** ghi dữ liệu giả.
9. **Config**: đọc `config/app_config.yaml`; **không** sinh file cấu hình mới khi chưa yêu cầu.

### **Android App (Kotlin + Jetpack Compose)**
1. **MQTT Client**:
   * Subscribe vitals/alerts/status từ devices đã pair (QoS 1/2)
   * Publish commands (start/stop measurement, set thresholds) (QoS 2)
   * Auto-reconnect, handle connection state
   * Debounce vitals updates (max 1 UI update/second)
2. **Room Database**: Cache vitals/alerts cho offline viewing
3. **Real-time UI**: 
   * Dashboard với live chart (update khi nhận MQTT message)
   * Device cards với color-coded status (🟢 Online, 🔴 Critical, ⚫ Offline)
   * Push notification cho critical alerts
4. **QR Pairing**: Scan QR từ Pi GUI → verify pairing_code với MySQL → subscribe MQTT topics
5. **History Screen**: Query MySQL REST API → show list với filter/pagination

### **Web Dashboard (React/Vue + MQTT.js)**
1. **MQTT Client**:
   * Subscribe vitals/alerts/status từ tất cả devices (admin view)
   * Publish commands (remote control devices)
   * WebSocket fallback nếu MQTT over WebSocket không khả dụng
2. **Real-time Chart**: Line chart với live update (Chart.js/D3.js)
3. **Alert Management**: 
   * Table view tất cả alerts (sort by severity/time)
   * Mark as resolved → publish command tới Pi
   * Browser notification + sound cho critical alerts
4. **Multi-device View**: Grid layout hiển thị nhiều Pi devices cùng lúc

---

---

## 🚫 CÁC HÀNH ĐỘNG CẤM TUYỆT ĐỐI

* Không sinh **file giả**, **mẫu dữ liệu**, **test asset**.
* Không đổi sơ đồ chân I²S/SPI/I²C/HX710B.
* Không tự ý chuyển sang ADC khác (ADS1115/ADS1220…) nếu chưa có yêu cầu.
* Không thay đổi BaseSensor interface hoặc callback pattern hiện có.
* **Không đổi MQTT topics, payloads, QoS levels** đã định nghĩa mà không hỏi.
* **Không hardcode broker credentials** - dùng config/environment variables.

---

## ⚙️ Tham số cấu hình bắt buộc (thêm vào app_config.yaml)

```yaml
# ============================================================
# MQTT Configuration (HiveMQ Cloud - Production)
# ============================================================
communication:
  mqtt:
    broker: c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud  # HiveMQ Cloud Singapore
    port: 8883  # TLS required
    use_tls: true  # TLS encryption required
    keepalive: 60

    # Device identification
    device_id: rpi_bp_001

    # QoS levels per message type
    qos:
      vitals: 1    # At least once
      alerts: 2    # Exactly once
      status: 0    # Fire and forget
      commands: 2  # Exactly once

    # Topics (với placeholders)
    topics:
      vitals: iot_health/device/{device_id}/vitals
      alerts: iot_health/device/{device_id}/alerts
      status: iot_health/device/{device_id}/status
      commands: iot_health/patient/{patient_id}/commands

    # Reconnection
    reconnect_delay: 5
    max_reconnect_attempts: 10

    # Last Will & Testament
    last_will:
      topic: iot_health/device/{device_id}/status
      message: '{"status": "offline", "reason": "unexpected_disconnect"}'
      qos: 1
      retain: true

# ============================================================
# Sensors Configuration
# ============================================================
sensors:
  hx710b:
    enabled: true
    gpio_dout: 6    # BCM GPIO6
    gpio_sck: 5     # BCM GPIO5
    sps_hint: 50    # Expected samples per second
    calibration:
      offset_counts: 0      # Zero offset
      slope_mmhg_per_count: 0.001  # Conversion factor
    timeout_ms: 1000
    
  blood_pressure:
    enabled: true
    inflate_target_mmhg: 165
    deflate_rate_mmhg_s: 3.0
    max_pressure_mmhg: 200
    pump_gpio: 26    # BCM GPIO26 via optocoupler
    valve_gpio: 16   # BCM GPIO16 via optocoupler
    ratio:
      sys_frac: 0.5   # SYS at 50% of max amplitude
      dia_frac: 0.8   # DIA at 80% of max amplitude

# ============================================================
# Cloud Sync (MySQL - AWS RDS)
# ============================================================
cloud:
  enabled: true
  mysql:
    host: database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com
    port: 3306
    database: iot_health_cloud
    user: pi_sync  # Limited user for Pi operations (SELECT/INSERT/UPDATE)
    # user: android_app  # Limited user for mobile app (SELECT only)
  sync:
    mode: auto
    interval_seconds: 300  # Sync every 5 minutes
    batch_size: 100

# ============================================================
# Database Schema (MySQL Cloud + SQLite Local)
# ============================================================

## **MySQL Cloud Schema (AWS RDS)**
- **Engine**: MySQL 8.0.44 với partitioning và foreign keys
- **Charset**: utf8mb4_unicode_ci
- **Tables**: 9 core tables + 15 analytical views + stored procedures

### **Core Tables:**
- `devices` - Device registry (device_id, device_name, location, pairing_code, device_type)
- `device_ownership` - Multi-user access control (user_id, device_id, role, nickname)
- `patients` - Patient info (patient_id, name, age, gender, device_id, emergency_contact)
- `health_records` - Vitals history (id, patient_id, device_id, timestamp, heart_rate, spo2, temperature, systolic_bp, diastolic_bp, mean_arterial_pressure, sensor_data, data_quality, measurement_context, synced_at, sync_status)
- `alerts` - Alert history (id, patient_id, device_id, alert_type, severity, message, vital_sign, current_value, threshold_value, timestamp, acknowledged, resolved, notification_sent, notification_method)
- `patient_thresholds` - Personalized thresholds (patient_id, vital_sign, min_normal, max_normal, min_critical, max_critical)
- `sensor_calibrations` - Calibration data (device_id, sensor_name, calibration_type, reference_values, measured_values, calibration_factors)
- `sync_queue` - Store-and-forward (device_id, table_name, operation, record_id, data_snapshot, sync_status, sync_attempts)
- `system_logs` - Event logs với partitioning (device_id, level, message, module, timestamp, additional_data)

### **Analytical Views:**
- `v_active_alerts`, `v_alert_summary`, `v_daily_summary`, `v_data_quality`, `v_device_health`, `v_device_status`, `v_error_dashboard`, `v_hourly_activity`, `v_latest_vitals`, `v_patient_vitals_trend`, `v_sync_performance`, `v_sync_queue_status`, `v_system_status`

### **Stored Procedures:**
- `sp_cleanup_old_records(days_to_keep)` - Data retention
- `sp_patient_statistics(patient_id)` - Patient analytics

## **SQLite Local Schema**
- **Path**: data/health_monitor.db
- **Purpose**: Offline cache (7 days), simplified schema
- **Tables**: alerts, health_records, patients, patient_thresholds, sensor_calibrations, system_logs
- **Sync Strategy**: Auto-sync mỗi 5 phút, conflict resolution (cloud wins)
```

---

## 💬 Workflow khi nhận yêu cầu

1. **Đọc yêu cầu kỹ**: Hiểu đầy đủ trước khi code
2. **Hỏi lại nếu không rõ**: "Bạn muốn thay đổi X hay Y?"
3. **Kiểm tra file hiện có**: Đọc code liên quan trước
4. **Đề xuất giải pháp**: Giải thích approach trước khi implement
5. **Code theo quy tắc**: OOP, comments, organization
6. **Test suggestion**: "Hãy test bằng cách..."
7. **Không tạo docs**: Trừ khi được yêu cầu
---

## ✅ Kiểm thử thủ công (không sinh dữ liệu giả)

* Dùng phần cứng thật: bơm/van/hx710b/cuff; xác nhận inflate/deflate, an toàn (soft-limit, NO, relief).
* Test với `tests/test_sensors.py` menu system.
* Xem log: driver HX710B không timeout quá lâu; tốc độ đọc phù hợp SPS thực.
* Nghe TTS rõ khi bơm chạy (nguồn sạch, không clip).
---

## ✨ Definition of Done

* Không sinh file rác; repo sạch.
* UI mượt (ví dụ: không lag >100ms trong đo BP; phản hồi touch <50ms); driver HX710B bền; an toàn đo (limit/timeout/xả khẩn).
* MQTT/REST/SQLite đúng schema hiện có; log đầy đủ cho debug (mức INFO/ERROR với timestamp, context); không lộ secrets.
* Tuân thủ BaseSensor pattern và callback architecture.
* Tích hợp với existing testing framework.

## 📅 Review định kỳ
Cập nhật file README.md khi dự án thay đổi (e.g., thêm sensor mới, thay đổi phần cứng, hoặc yêu cầu mới từ user)

---

## 📱 **ANDROID APP - MQTT IMPLEMENTATION**

### **Architecture Pattern**
```
MVVM + Clean Architecture + Hilt DI

Layers:
├── Presentation (Jetpack Compose + ViewModels)
├── Domain (Use Cases)
└── Data (Repository + Room + MQTT + REST)
```

### **Key Components**

#### **1. MqttManager.kt** (Singleton via Hilt)
```kotlin
class MqttManager @Inject constructor(
    @ApplicationContext private val context: Context,
    private val gson: Gson
) {
    private var mqttClient: MqttAndroidClient? = null
    
    // StateFlows for real-time updates
    private val _vitalsFlow = MutableStateFlow<VitalsPayload?>(null)
    val vitalsFlow: StateFlow<VitalsPayload?> = _vitalsFlow.asStateFlow()
    
    private val _alertsFlow = MutableStateFlow<AlertPayload?>(null)
    val alertsFlow: StateFlow<AlertPayload?> = _alertsFlow.asStateFlow()
    
    fun connect(deviceId: String, patientId: String)
    fun subscribeToDevice(deviceId: String)
    fun publishCommand(command: String, params: Map<String, Any>)
    fun disconnect()
}
```

#### **2. Room Database Cache**
```kotlin
@Entity(tableName = "vitals_cache")
data class VitalsEntity(
    @PrimaryKey val id: String,
    val deviceId: String,
    val timestamp: Long,
    val heartRate: Int?,
    val spo2: Int?,
    val temperature: Double?,
    val systolic: Int?,
    val diastolic: Int?,
    val syncedToCloud: Boolean
)
```

#### **3. DevicesScreen (Compose)**
```kotlin
@Composable
fun DevicesScreen(viewModel: DevicesViewModel = hiltViewModel()) {
    val devices by viewModel.devices.collectAsState()
    val vitals by viewModel.liveVitals.collectAsState()
    
    LazyColumn {
        items(devices) { device ->
            DeviceCard(
                device = device,
                vitals = vitals[device.id],
                status = getDeviceStatus(device)
            )
        }
    }
}
```

#### **4. Critical Features**
- ✅ **Auto-reconnect**: ExponentialBackoff khi mất kết nối
- ✅ **Debounce**: Max 1 UI update/second để tránh lag
- ✅ **Offline mode**: Show data từ Room cache
- ✅ **Push notifications**: Firebase FCM cho critical alerts
- ✅ **QR Pairing**: ZXing scanner → verify với MySQL

### **Data Flow**
```
Pi → MQTT Broker → Android MqttManager
                    ↓
         StateFlow (vitalsFlow/alertsFlow)
                    ↓
              ViewModel observe
                    ↓
         Compose UI auto-recompose
                    ↓
         Room DB cache (background)
```

### **Testing Strategy**
- Unit tests: ViewModel logic với mock repositories
- Integration tests: MqttManager với test broker
- UI tests: Compose screens với ComposeTestRule
- E2E tests: Full flow từ Pi → Android

---

## 🌐 **WEB DASHBOARD - MQTT IMPLEMENTATION**

### **Tech Stack**
```
Frontend: React/Vue.js + TypeScript
MQTT Client: MQTT.js (WebSocket)
Chart: Chart.js / D3.js
State Management: Redux/Zustand
UI Framework: Material-UI / Ant Design
```

### **Key Components**

#### **1. MqttClient.ts**
```typescript
class MqttClient {
    private client: mqtt.MqttClient | null = null;
    
    // EventEmitter for real-time updates
    public vitalsEmitter = new EventEmitter();
    public alertsEmitter = new EventEmitter();
    
    connect(broker: string, port: number): Promise<void>
    subscribeToAllDevices(): void
    subscribeToDevice(deviceId: string): void
    publishCommand(patientId: string, command: string): void
    disconnect(): void
}
```

#### **2. Real-time Dashboard**
```tsx
const Dashboard: React.FC = () => {
    const [devices, setDevices] = useState<Device[]>([]);
    const [vitals, setVitals] = useState<Map<string, Vitals>>(new Map());
    
    useEffect(() => {
        mqttClient.vitalsEmitter.on('data', (data) => {
            setVitals(prev => prev.set(data.device_id, data));
        });
        
        return () => mqttClient.vitalsEmitter.removeAllListeners();
    }, []);
    
    return (
        <Grid container spacing={2}>
            {devices.map(device => (
                <DeviceCard 
                    key={device.id} 
                    device={device}
                    vitals={vitals.get(device.id)}
                />
            ))}
        </Grid>
    );
};
```

#### **3. Live Chart Update**
```typescript
useEffect(() => {
    const updateChart = (data: VitalsPayload) => {
        setChartData(prev => ({
            labels: [...prev.labels, new Date(data.timestamp * 1000)],
            datasets: [{
                data: [...prev.datasets[0].data, data.measurements.heart_rate.value]
            }]
        }));
    };
    
    mqttClient.vitalsEmitter.on('data', updateChart);
    return () => mqttClient.vitalsEmitter.off('data', updateChart);
}, []);
```

#### **4. Critical Features**
- ✅ **Multi-device view**: Grid layout hiển thị nhiều Pi
- ✅ **Admin controls**: Remote start/stop measurements
- ✅ **Alert management**: Mark as resolved, filter by severity
- ✅ **Browser notifications**: Native notifications + sound
- ✅ **Export data**: CSV/PDF export với date range

### **Security Considerations**
```typescript
// WebSocket over TLS (wss://)
const mqttOptions = {
    protocol: 'wss',
    port: 8884,  // WSS port for HiveMQ Cloud
    username: 'web_dashboard',
    password: process.env.REACT_APP_MQTT_PASSWORD,
    clean: true,
    reconnectPeriod: 5000
};
```

---

## 🔐 **SECURITY BEST PRACTICES**

### **Production MQTT Setup**
1. **HiveMQ Cloud**: c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud (Singapore region, free tier)
2. **TLS encryption**: Port 8883 (TCP) / 8884 (WebSocket)
3. **Authentication**: Username/password per client (rpi_bp_001, android_app, web_dashboard)
4. **Authorization**: ACL rules configured in HiveMQ Cloud dashboard
5. **Certificates**: Let's Encrypt (managed by HiveMQ Cloud)

### **ACL Rules Example** (HiveMQ Cloud Dashboard)
```
# Pi devices (publish only)
user rpi_bp_001
topic write iot_health/device/rpi_bp_001/vitals
topic write iot_health/device/rpi_bp_001/alerts
topic write iot_health/device/rpi_bp_001/status
topic read iot_health/patient/+/commands

# Android app (subscribe + limited publish)
user android_app
topic read iot_health/device/+/vitals
topic read iot_health/device/+/alerts
topic read iot_health/device/+/status
topic write iot_health/patient/+/commands

# Web dashboard (admin access)
user web_dashboard
topic readwrite iot_health/#
```

### **Environment Variables** (KHÔNG commit vào git)
```bash
# Pi (.env)
MQTT_BROKER=c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud
MQTT_PORT=8883
MQTT_USERNAME=rpi_bp_001
MQTT_PASSWORD=<your_hivemq_password>
MYSQL_PASSWORD=<mysql_password>

# Android (local.properties)
mqtt.broker=c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud
mqtt.port=8883
mqtt.username=android_app
mqtt.password=<your_hivemq_password>

# Web (.env.production)
REACT_APP_MQTT_BROKER=c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud
REACT_APP_MQTT_PORT=8884
REACT_APP_MQTT_USERNAME=web_dashboard
REACT_APP_MQTT_PASSWORD=<your_hivemq_password>
```

---

## 📊 **MONITORING & DEBUGGING**

### **MQTT Monitoring Tools**
1. **MQTT Explorer**: Desktop GUI để monitor topics real-time
2. **HiveMQ Cloud Dashboard**: Web interface để monitor connections, topics, và metrics
3. **Custom dashboard**: Track message rates, errors, latency
