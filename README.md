# IoT Health Monitoring System

## Mô tả dự án
Hệ thống IoT theo dõi sức khỏe cho người cao tuổi, đo nhịp tim, SpO2, nhiệt độ, huyết áp với giao diện cải tiến 480x320 trên màn hình SPI 3.5", cảnh báo qua loa và giám sát từ xa qua Android/Web.

### Tính năng mới (v2.0)
- **Giao diện cải tiến**: Dashboard với 3 khối cảm biến lớn, dễ sử dụng trên màn hình cảm ứng
- **Màn hình đo chi tiết**: Giao diện riêng cho từng loại cảm biến với animation và gauge
- **Tối ưu cho touchscreen**: Interface 480x320 với button lớn, text rõ ràng
- **Hoàn toàn bằng tiếng Việt**: Toàn bộ giao diện và thông báo TTS

## Cấu trúc thư mục

```
IoT_health/
├── main.py                 # Entry point chính của ứng dụng
├── requirements.txt        # Danh sách thư viện Python cần thiết
├── .env                   # Biến môi trường
├── README.md              # Tài liệu dự án
├── config/                # Thư mục cấu hình
│   └── app_config.yaml    # File cấu hình chính
├── src/                   # Mã nguồn chính
│   ├── __init__.py
│   ├── sensors/           # Module cảm biến
│   │   ├── __init__.py
│   │   ├── base_sensor.py          # Abstract base class cho sensors
│   │   ├── max30102_sensor.py      # Driver cho MAX30102 (HR/SpO2) - với tích hợp thư viện
│   │   ├── temperature_sensor.py   # Driver cho DS18B20/MLX90614
│   │   └── blood_pressure_sensor.py # Driver cho huyết áp
│   ├── gui/               # Giao diện người dùng (Kivy)
│   │   ├── __init__.py
│   │   ├── main_app.py            # Main Kivy application
│   │   ├── dashboard_screen.py    # Màn hình chính
│   │   ├── bp_measurement_screen.py # Màn hình đo huyết áp
│   │   └── settings_screen.py     # Màn hình cài đặt
│   ├── communication/     # Module liên lạc
│   │   ├── __init__.py
│   │   ├── mqtt_client.py         # MQTT client
│   │   ├── rest_client.py         # REST API client
│   │   └── store_forward.py       # Store-and-forward mechanism
│   ├── data/             # Quản lý dữ liệu
│   │   ├── __init__.py
│   │   ├── models.py             # Database models
│   │   ├── database.py           # Database manager
│   │   └── processor.py          # Data processing
│   ├── ai/               # AI và phân tích
│   │   ├── __init__.py
│   │   ├── alert_system.py       # Hệ thống cảnh báo
│   │   ├── anomaly_detector.py   # Phát hiện bất thường
│   │   ├── trend_analyzer.py     # Phân tích xu hướng
│   │   └── chatbot_interface.py  # Interface chatbot
│   └── utils/            # Tiện ích chung
│       ├── __init__.py
│       ├── logger.py             # Logging utilities
│       ├── config_loader.py      # Configuration loader
│       ├── validators.py         # Data validators
│       └── decorators.py         # Utility decorators
├── data/                 # Thư mục dữ liệu
├── logs/                 # Thư mục log files
└── tests/                # Test cases
    └── __init__.py
```

## Kiến trúc hệ thống

### 1. Sensors Module
- **BaseSensor**: Abstract base class với interface thống nhất
- **MAX30102Sensor**: Đo nhịp tim và SpO2 - **với tích hợp MAX30102 và HRCalc libraries**
- **TemperatureSensor**: Đo nhiệt độ (DS18B20/MLX90614)
- **BloodPressureSensor**: Đo huyết áp oscillometric

#### MAX30102 Library Integration
- **MAX30102Hardware**: Tích hợp trực tiếp từ max30102.py - I2C communication và hardware control
- **HRCalculator**: Tích hợp trực tiếp từ hrcalc.py - Peak detection và SpO2 calculation algorithms
- **Loại bỏ external dependencies**: Không cần cài đặt max30102.py và hrcalc.py riêng biệt

### 2. GUI Module (Kivy)
- **HealthMonitorApp**: Main application controller
- **DashboardScreen**: Hiển thị dashboard chính
- **BPMeasurementScreen**: Màn hình đo huyết áp
- **SettingsScreen**: Cài đặt và cấu hình

### 3. Communication Module
- **MQTTClient**: Real-time data transmission
- **RESTClient**: API calls cho prediction/chat
- **StoreForwardManager**: Offline data management

### 4. Data Module
- **DatabaseManager**: SQLite database operations
- **DataProcessor**: Signal processing và feature extraction
- **Models**: Data models cho Patient, HealthRecord, Alert

### 5. AI Module
- **AlertSystem**: Rule-based và threshold alerts
- **AnomalyDetector**: IsolationForest/LOF cho anomaly detection
- **TrendAnalyzer**: Phân tích xu hướng dài hạn
- **ChatbotInterface**: AI chatbot tư vấn

### 6. Utils Module
- **Logger**: Logging configuration
- **ConfigLoader**: YAML config management
- **DataValidator**: Input validation
- **Decorators**: Retry, timing utilities

## Demo giao diện mới

### Chạy demo GUI với logic cảm biến
```bash
# Demo cơ bản với mock sensors
python demo_enhanced_gui.py

# Test logic tích hợp cảm biến (RECOMMENDED)
python test_sensor_logic.py
```

### Tính năng demo:
- **Dashboard chính**: 3 khối cảm biến với logic thực từ MAX30102/MLX90614
- **MAX30102 Logic**: Finger detection, HR/SpO2 validation, signal quality, buffer management - với tích hợp libraries
- **MLX90614 Logic**: Object/ambient temperature, status codes, smoothing filters
- **Realistic Simulation**: Dữ liệu theo đúng range và validation của sensor thật
- **Status Color Coding**: Màu sắc theo trạng thái critical/warning/normal/partial
- **Measurement Screens**: Logic đo chính xác với stability checking

## Cài đặt và chạy

### Yêu cầu hệ thống
- Raspberry Pi 4B 8GB
- Raspberry Pi OS 64-bit Bookworm
- Python 3.9+
- SPI LCD 3.5" Waveshare

### Cài đặt dependencies
```bash
pip install -r requirements.txt
```

### Cấu hình hardware
1. Kết nối sensors theo schema trong config
2. Enable SPI và I2C trong raspi-config
3. Cấu hình SPI LCD overlay

### Chạy ứng dụng
```bash
python main.py
```

## Tính năng chính

### Phase 1 - Core Foundation
- [x] Cấu trúc project và architecture
- [ ] Basic sensor reading (MAX30102, DS18B20)
- [ ] Simple GUI display
- [ ] Threshold-based alerts

### Phase 2 - Communication
- [x] MQTT client implementation (test.mosquitto.org:1883)
- [x] MQTT payload schemas (VitalsPayload, AlertPayload, DeviceStatusPayload)
- [x] REST API client framework
- [x] Store-forward offline support
- [x] Cloud sync with MySQL (192.168.2.15:3306)

### Phase 3 - Advanced Features
- [x] Blood pressure measurement (HX710B oscillometric method)
- [x] AI anomaly detection (IsolationForest framework)
- [x] Android app design (Kotlin + Jetpack Compose)
- [x] Multi-device management (QR code pairing)
- [ ] Android app implementation (in progress)
- [ ] Web dashboard

### Phase 4 - Optimization
- [ ] Performance tuning
- [ ] Security hardening
- [ ] Clinical validation

### Phase 4 - Optimization
- [ ] Performance tuning
- [ ] Security hardening
- [ ] Clinical validation

## Cấu hình Hardware

### 1. Sơ đồ khối & chức năng

* **Raspberry Pi 4B (3.3 V, logic):**
  Điều khiển bơm/van qua **optocoupler 4N35** (cách ly), đọc áp suất từ **HX710B (24-bit)**.
* **Miền công suất 6 V (cách ly Pi):**
  **4N35 → MOSFET N (IRLZ44N/FQP30N06L)** đóng/ngắt **bơm 6 V** & **van xả 6 V**.
  Có **diode flyback SS14**, **tụ lọc tổng 1000 µF + 100 nF** và **tụ cục bộ sát bơm**.
* **Khí nén:** Bơm → **van 1 chiều (→ cuff)** → T → cuff & nhánh cảm biến → **van xả** ra môi trường; **van relief (250–300 mmHg)** (khuyên dùng).

### 2. Mapping chân GPIO (BCM) – phiên bản mới

| Khối            | Tín hiệu            |       GPIO (BCM) | Ghi chú                         |
| --------------- | ------------------- | ---------------: | ------------------------------- |
| **Bơm (Q1)**    | Điều khiển LED 4N35 |       **GPIO26** | Output, mặc định LOW            | 
| **Van xả (Q2)** | Điều khiển LED 4N35 |       **GPIO16** | Output, mặc định LOW            |
| **HX710B**      | OUT (data ready)    |        **GPIO6** | Input (có thể dùng pull-up nhẹ) |
| **HX710B**      | SCK (clock)         |        **GPIO5** | Output                          |
| **HX710B**      | VCC/GND             | **3V3 / GND Pi** | Cùng miền 3.3 V với Pi          |

> Miền **6 V công suất** (bơm/van/MOSFET) **không** nối GND với Pi (đã cách ly qua 4N35).
> Chỉ riêng **HX710B** là chung GND với Pi.

### 3. Đi dây điện – chuẩn kỹ thuật

#### 3.1 Cách ly điều khiển (mỗi kênh bơm/van)

* **GPIO → R_LED 330 Ω → 4N35 pin1 (Anode); 4N35 pin2 (Cathode) → GND Pi.**
* **4N35 pin5 (Collector) → +6 V BUS** ; **pin4 (Emitter) → R_gate 100–220 Ω → Gate MOSFET**.
* **Gate MOSFET → R_pull-down 68–150 kΩ → GND6** (mặc định OFF).

#### 3.2 MOSFET & tải

* **MOSFET (mặt chữ): G–D–S.**
  **S → GND6**, **D → cực "−" của tải** (bơm/van), **cực "+" tải → +6 V BUS**.
* **Diode SS14:** **Cathode (vạch trắng) → +6 V BUS**, **Anode → nút Drain/tải −**.
* **Tụ:** **1000 µF // 100 nF** tại **BUS 6 V**; (khuyên) **470–1000 µF // 100 nF** **sát cọc bơm** (nếu dây dài).

#### 3.3 HX710B (3.3 V domain)

* **VCC → 3V3**, **GND → GND Pi**, **OUT → GPIO6**, **SCK → GPIO5**, **100 nF (104)** sát **VCC–GND** của module.
* Ống khí cảm biến **ngắn & kín**.

### 4. Khí nén – đúng chiều

* **Bơm OUT → van 1 chiều (mũi tên hướng → cuff) → T → cuff**
* Nhánh **T → cổng cảm biến HX710B** (ống ngắn).
* **Cuff → van xả JQF1-6A** ra môi trường.
* **Relief 250–300 mmHg** song song cuff (khuyến nghị an toàn cứng).

### 5. Sơ đồ tổng thể (Mermaid – mapping mới)

```mermaid
graph TD
    subgraph Pi["Raspberry Pi 4B (3.3 V logic)"]
      P_GPIO26["GPIO26 → Bơm (LED 4N35)"]
      P_GPIO16["GPIO16 → Van (LED 4N35)"]
      P_GPIO6["GPIO6 ← HX710B OUT"]
      P_GPIO5["GPIO5 → HX710B SCK"]
      P_3V3["3V3"]
      P_GND["GND Pi"]
    end

    subgraph HX["HX710B (3.3 V domain)"]
      HX_VCC["VCC ← 3V3"]
      HX_GND["GND ← GND Pi"]
      HX_OUT["OUT → GPIO6"]
      HX_SCK["SCK ← GPIO5"]
      HX_CAP["100 nF (104) sát VCC–GND"]
    end

    subgraph Power6V["BUS 6 V (cách ly)"]
      BUS["+6 V BUS"]
      GND6["GND6"]
      Cbulk["1000 µF // 100 nF tại BUS"]
    end

    subgraph PumpCh["Kênh Bơm 6 V"]
      O1["4N35 (Pump)\npin1←GPIO26 qua 330Ω; pin2→GND Pi\npin5←+6V; pin4→R_gate→Gate Q1"]
      Q1["MOSFET N Q1 (IRLZ44N/FQP30N06L)\nG-D-S (S→GND6)"]
      D1["SS14: Cathode(vạch)→+6V; Anode→nút Drain"]
      Pump["+ Bơm: (+)→+6V; (−)→Drain"]
      Rpd1["Gate→100 kΩ→GND6"]
      Cnear["(Khuyên) 470–1000 µF // 100 nF sát bơm"]
    end

    subgraph ValveCh["Kênh Van 6 V"]
      O2["4N35 (Valve)\npin1←GPIO16 qua 330Ω; pin2→GND Pi\npin5←+6V; pin4→R_gate→Gate Q2"]
      Q2["MOSFET N Q2 (IRLZ44N/FQP30N06L)\nG-D-S (S→GND6)"]
      D2["SS14: Cathode(vạch)→+6V; Anode→nút Drain"]
      Valve["Van 6 V: 1 dây→+6V; 1 dây→Drain"]
      Rpd2["Gate→100 kΩ→GND6"]
      Cv0["100 nF sát cuộn van"]
    end

    subgraph Air["Khí nén"]
      BPUMP["Bơm OUT → Van 1 chiều (→) → T → Cuff"]
      Sense["T → Ống ngắn → HX710B"]
      Vent["Cuff → Van xả → môi trường"]
      Relief["(Khuyên) Relief 250–300 mmHg song song cuff"]
    end

    %% Wiring
    P_3V3 --> HX_VCC
    P_GND --> HX_GND
    P_GPIO6 --> HX_OUT
    P_GPIO5 --> HX_SCK
    HX_VCC --- HX_CAP
    HX_GND --- HX_CAP

    BUS --- Cbulk
    BUS --> O1
    BUS --> O2

    O1 --> Q1
    O2 --> Q2
    Q1 --> D1 --> BUS
    Q2 --> D2 --> BUS
    Pump --> Q1
    Valve --> Q2
    Cnear --- BUS
    Cnear --- GND6
    Cv0 --- BUS
    Cv0 --- GND6
```

### 6. Kiểm tra trước khi cấp điện (tối quan trọng)

1. **Điện trở & diode:**
   Gate↔GND6 đo ~**68–150 kΩ**; **diode SS14** đo chiều thuận ~0.2–0.4 V, nghịch **không dẫn**; **vạch trắng** về **+6 V**.
2. **Tụ hóa:** **"+" → +6 V**, **"−" → GND6** (thân tụ vạch dấu "−").
3. **4N35:** LED đúng cực (**pin1 Anode**, **pin2 Cathode**); transistor **pin5 → +6 V**, **pin4 → Gate qua 100–220 Ω**.
4. **Nguồn:** Cấp **6 V** cho khối công suất (**Pi chưa cấp**) → bơm/van **không tự chạy**. Sau đó cấp **5 V** cho Pi.

## Cấu hình Sensors

### Sensors Configuration
- **MAX30102**: I2C address 0x57, INT pin GPIO4 (HR/SpO2 sensor)
- **MLX90614**: I2C address 0x5A (temperature sensor)
- **HX710B**: GPIO5 (SCK), GPIO6 (DOUT) - Blood pressure sensor
- **Blood Pressure Control**:
  - Pump: GPIO26 (via 4N35 optocoupler)
  - Valve: GPIO16 (via 4N35 optocoupler)
  - Power: 6V BUS (isolated from Pi)

### Display
- SPI LCD 3.5": /dev/fb1, resolution 480x320
- Kivy framebuffer rendering

### Communication

#### MQTT Configuration (HiveMQ Cloud - Production)
- **Broker**: c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud
- **Port**: 8883 (TLS required)
- **WebSocket Port**: 8884 (for web dashboard)
- **Region**: Singapore (Free Tier)
- **Credentials**: 
  - Pi Device: `rpi_bp_001` (username), password in .env
  - Android App: `android_app` (username), password in .env
  - Web Dashboard: `web_dashboard` (username) - *deferred*
- **Client ID**: rpi_bp_001 (device_id from config)
- **TLS**: Required (system CA certificates - Let's Encrypt)
- **QoS Levels**: 
  - Vitals: QoS 1 (at least once)
  - Alerts: QoS 2 (exactly once)
  - Status: QoS 0 (fire and forget)
  - Commands: QoS 2 (exactly once)
- **Last Will & Testament**: Enabled (offline notification)
- **Auto-reconnect**: Exponential backoff (5s, 10s, 20s, 40s, 60s max)

#### MQTT Topics Structure
```yaml
# Pi → Cloud/App (Publish)
iot_health/device/{device_id}/vitals:
  QoS: 1
  Payload: VitalsPayload (JSON với HR, SpO2, Temp, BP + raw metrics)
  Frequency: Mỗi lần đo xong

iot_health/device/{device_id}/alerts:
  QoS: 2
  Payload: AlertPayload (JSON với alert_type, severity, recommendations)
  Trigger: Khi vượt ngưỡng

iot_health/device/{device_id}/status:
  QoS: 0
  Payload: DeviceStatusPayload (JSON với sensors, battery, system health)
  Frequency: Heartbeat mỗi 60s

# Cloud/App → Pi (Subscribe)
iot_health/patient/{patient_id}/commands:
  QoS: 2
  Payload: CommandPayload (JSON với command, parameters)
  Examples: start_measurement, calibrate_sensor, emergency_deflate

iot_health/patient/{patient_id}/predictions:
  QoS: 1
  Payload: AI predictions từ cloud
```

#### REST API Server (Production - AWS EC2)
- **Server**: http://47.130.193.237:8000 (AWS EC2 Ubuntu)
- **Framework**: Flask + Gunicorn + systemd
- **Database**: MySQL 8.0.44 (AWS RDS)
- **Authentication**: None (planned JWT)
- **Rate Limiting**: None (planned)
- **CORS**: Enabled for Android/Web clients

#### REST API Endpoints

##### Health Check
```http
GET /api/health
```
**Response:**
```json
{
  "status": "ok",
  "database": "connected",
  "timestamp": "2025-11-18T10:30:00.000000",
  "version": "1.0.0"
}
```

##### Device Pairing
```http
POST /api/pair-device
Content-Type: application/json

{
  "pairing_code": "ABC123XY",
  "user_id": "user_001",
  "nickname": "Living Room Monitor"
}
```
**Success Response:**
```json
{
  "status": "success",
  "message": "Device paired successfully",
  "data": {
    "device_info": {
      "device_id": "rpi_bp_001",
      "device_name": "Living Room Monitor",
      "device_type": "raspberry_pi_4b",
      "location": "Home - Living Room",
      "nickname": "Living Room Monitor"
    },
    "patient_info": null,
    "mqtt_topics": {
      "vitals": "iot_health/device/rpi_bp_001/vitals",
      "alerts": "iot_health/device/rpi_bp_001/alerts",
      "status": "iot_health/device/rpi_bp_001/status",
      "commands": null
    },
    "thresholds": {}
  }
}
```

##### Add Patient Information
```http
POST /api/patient
Content-Type: application/json

{
  "device_id": "rpi_bp_001",
  "user_id": "user_001",
  "name": "Nguyễn Văn A",
  "age": 65,
  "gender": "M",
  "medical_conditions": {
    "hypertension": true,
    "diabetes": false,
    "heart_disease": false,
    "notes": "Cao huyết áp từ 2020"
  },
  "emergency_contact": {
    "name": "Nguyễn Thị B",
    "relationship": "Con gái",
    "phone": "0912345678"
  }
}
```
**Success Response:**
```json
{
  "status": "success",
  "message": "Patient information saved successfully",
  "data": {
    "patient_id": "patient_rpi_bp_001_user_001",
    "name": "Nguyễn Văn A",
    "age": 65,
    "gender": "M",
    "medical_conditions": {
      "hypertension": true,
      "diabetes": false,
      "heart_disease": false,
      "notes": "Cao huyết áp từ 2020"
    },
    "emergency_contact": {
      "name": "Nguyễn Thị B",
      "relationship": "Con gái",
      "phone": "0912345678"
    },
    "mqtt_commands_topic": "iot_health/patient/patient_rpi_bp_001_user_001/commands"
  }
}
```

##### Get User Devices
```http
GET /api/devices/{user_id}
```
**Success Response:**
```json
{
  "status": "success",
  "devices": [
    {
      "device_id": "rpi_bp_001",
      "device_name": "Living Room Monitor",
      "device_type": "raspberry_pi_4b",
      "location": "Home - Living Room",
      "nickname": "Living Room Monitor",
      "last_seen": "2025-11-18T08:00:00.000000",
      "is_active": 1,
      "patient_id": "patient_rpi_bp_001_user_001",
      "patient_name": "Nguyễn Văn A",
      "age": 65,
      "gender": "M"
    }
  ]
}
```

#### REST API Error Responses
```json
// 400 Bad Request
{
  "status": "error",
  "message": "Missing required fields: pairing_code, user_id, nickname"
}

// 403 Forbidden
{
  "status": "error",
  "message": "User does not own this device"
}

// 409 Conflict
{
  "status": "error",
  "message": "Device already paired with this user"
}

// 500 Internal Server Error
{
  "status": "error",
  "message": "Database error: Connection timeout"
}
```

#### Cloud Database (MySQL)
- **Host**: database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com:3306 (AWS RDS)
- **Database**: iot_health_cloud
- **Engine**: MySQL 8.0.44
- **Charset**: utf8mb4_unicode_ci
- **Tables**:

  **Core Tables:**
  - `devices` - Device registry với pairing fields (device_id, device_name, location, pairing_code, device_type)
  - `device_ownership` - Multi-user device access control (user_id, device_id, role, nickname)
  - `patients` - Patient information (patient_id, name, age, gender, device_id, emergency_contact)
  - `health_records` - Vitals history (id, patient_id, device_id, timestamp, heart_rate, spo2, temperature, systolic_bp, diastolic_bp, mean_arterial_pressure, sensor_data, data_quality, measurement_context, synced_at, sync_status)
  - `alerts` - Alert history với severity levels (id, patient_id, device_id, alert_type, severity, message, vital_sign, current_value, threshold_value, timestamp, acknowledged, resolved, notification_sent, notification_method)

  **Configuration Tables:**
  - `patient_thresholds` - Personalized vital sign thresholds (patient_id, vital_sign, min_normal, max_normal, min_critical, max_critical)
  - `sensor_calibrations` - Sensor calibration data (device_id, sensor_name, calibration_type, reference_values, measured_values, calibration_factors)

  **Sync & Logging Tables:**
  - `sync_queue` - Store-and-forward queue (device_id, table_name, operation, record_id, data_snapshot, sync_status, sync_attempts)
  - `system_logs` - System event logs với partitioning (device_id, level, message, module, timestamp, additional_data)

  **Views (Analytics):**
  - `v_active_alerts` - Active alerts with patient/device info
  - `v_alert_summary` - Alert statistics by date/severity
  - `v_daily_summary` - Daily system metrics
  - `v_data_quality` - Data quality analytics
  - `v_device_health` - Device status and health metrics
  - `v_device_status` - Device overview
  - `v_error_dashboard` - Error monitoring dashboard
  - `v_hourly_activity` - Hourly activity patterns
  - `v_latest_vitals` - Latest vital signs per patient
  - `v_patient_vitals_trend` - Vital trends analysis
  - `v_sync_performance` - Sync performance metrics
  - `v_sync_queue_status` - Sync queue monitoring
  - `v_system_status` - System health overview

  **Stored Procedures:**
  - `sp_cleanup_old_records(days_to_keep)` - Data retention management
  - `sp_patient_statistics(patient_id)` - Patient statistics calculation

#### Local Database (SQLite)
- **Path**: data/health_monitor.db
- **Purpose**: Local cache, offline mode (7 days)
- **Tables**: alerts, health_records, patients, patient_thresholds, sensor_calibrations, system_logs
- **Sync Strategy**: Auto-sync mỗi 5 phút, conflict resolution (cloud wins)
- **Note**: Simplified schema without partitioning, foreign keys optional

#### REST API (Planned)
- **Server**: http://localhost:8000 hoặc cloud endpoint
- **Endpoints**:
  - `GET /api/v1/devices` - List devices
  - `POST /api/v1/pair-device` - Device pairing
  - `GET /api/v1/health-records` - Historical data
  - `GET /api/v1/trend-analysis` - AI trend analysis
  - `POST /api/v1/chat-with-ai` - Chatbot interface

## Bảo mật
- MQTT over TLS
- JWT authentication cho REST API
- Input validation và sanitization
- Hardware safety interlocks

## Monitoring và Logging
- Structured logging với rotation
- Health metrics collection
- Error tracking và alerting
- Performance monitoring

## MQTT Payload Schemas

### VitalsPayload Example
```json
{
  "timestamp": 1699344000.5,
  "device_id": "rpi_bp_001",
  "patient_id": "patient_001",
  "measurements": {
    "heart_rate": {
      "value": 85,
      "unit": "bpm",
      "valid": true,
      "confidence": 0.95,
      "source": "MAX30102",
      "raw_metrics": {
        "ir_quality": 50000,
        "peak_count": 142,
        "sampling_rate": 50.0
      }
    },
    "spo2": {
      "value": 98,
      "unit": "%",
      "valid": true,
      "confidence": 0.92,
      "source": "MAX30102",
      "raw_metrics": {
        "r_value": 0.85,
        "ac_red": 48000,
        "dc_red": 1000000
      }
    },
    "temperature": {
      "object_temp": 36.8,
      "ambient_temp": 29.5,
      "unit": "celsius",
      "valid": true,
      "source": "MLX90614"
    },
    "blood_pressure": {
      "systolic": 120,
      "diastolic": 80,
      "map": 93,
      "unit": "mmHg",
      "valid": true,
      "quality": "good",
      "confidence": 0.88,
      "source": "HX710B",
      "raw_metrics": {
        "max_counts": 125000,
        "map_counts": 115000,
        "samples_collected": 450,
        "sampling_rate": 10.0,
        "oscillation_amplitude": 15.5,
        "envelope_quality": 0.85
      }
    }
  },
  "session": {
    "session_id": "session_20251108_143000",
    "measurement_sequence": 1,
    "total_duration": 45.2,
    "user_triggered": true
  }
}
```

### AlertPayload Example
```json
{
  "timestamp": 1699344100.5,
  "device_id": "rpi_bp_001",
  "patient_id": "patient_001",
  "alert_type": "high_blood_pressure",
  "severity": "critical",
  "priority": 1,
  "current_measurement": {
    "vital_sign": "blood_pressure",
    "systolic": 185,
    "diastolic": 95,
    "map": 125
  },
  "thresholds": {
    "systolic_max": 180,
    "diastolic_max": 90
  },
  "trend": {
    "direction": "increasing",
    "rate_of_change": 5.2
  },
  "actions": {
    "emergency_call_suggested": true,
    "medication_reminder": true
  },
  "recommendations": [
    "Uống thuốc huyết áp ngay",
    "Nghỉ ngơi và thư giãn",
    "Gọi bác sĩ nếu không giảm trong 30 phút"
  ],
  "metadata": {
    "alert_id": "alert_20251108_143100",
    "notification_sent": true,
    "tts_spoken": true
  }
}
```

## Android App Integration

### App Architecture
- **Language**: Kotlin
- **UI Framework**: Jetpack Compose
- **Architecture**: MVVM + Clean Architecture
- **DI**: Hilt
- **Local DB**: Room (SQLite cache)
- **MQTT**: Paho Android MQTT client
- **Charts**: MPAndroidChart
- **QR Scanner**: ZXing

### Key Features
- **Multi-device management**: Quản lý nhiều Raspberry Pi devices
- **QR code pairing**: Ghép nối device qua QR code (pairing_code)
- **Real-time monitoring**: MQTT wildcard subscription `iot_health/device/+/#`
- **Offline mode**: Room cache 7 ngày, auto-sync khi online
- **Push notifications**: Critical alerts qua Firebase Cloud Messaging
- **Charts & analytics**: Trends, statistics, export CSV/PDF
- **Role-based access**: Owner, Admin, Caregiver, Viewer

### Device Pairing Flow
1. Pi generates pairing_code (6-8 chars: ABC123XY)
2. Display QR code on Kivy GUI (Settings → Pairing)
3. Android app scan QR hoặc nhập code manual
4. **REST API call**: `POST /api/pair-device` với pairing_code, user_id, nickname
5. **Response**: device_info, mqtt_topics, patient_info=null, thresholds={}
6. **Optional**: Add patient info via `POST /api/patient`
7. Create ownership: `INSERT INTO device_ownership (user_id, device_id, role)`
8. Subscribe MQTT: `iot_health/device/{device_id}/#`
9. Start real-time monitoring

### Documentation
- **Implementation Guide**: `docs/ANDROID_APP_IMPLEMENTATION_GUIDE.md`
- **MySQL Setup**: `docs/MYSQL_SETUP_COMPLETED.md`
- **MQTT Test**: `tests/test_mqtt_connection.py`

## System Workflow

### Complete IoT Health Monitoring Flow

```mermaid
graph TB
    subgraph "Raspberry Pi (IoT Device)"
        subgraph "Sensors"
            MAX30102[MAX30102<br/>HR/SpO2]
            MLX90614[MLX90614<br/>Temperature]
            HX710B[HX710B<br/>Blood Pressure]
        end
        
        subgraph "Data Processing"
            SensorLogic[Sensor Logic<br/>Validation & Processing]
            AlertSystem[Alert System<br/>Threshold Checking]
        end
        
        subgraph "Communication"
            MQTTClient[MQTT Client<br/>Paho MQTT]
            RESTClient[REST Client<br/>For pairing]
        end
        
        subgraph "Local Storage"
            SQLite[(SQLite<br/>Local Cache)]
        end
        
        MAX30102 --> SensorLogic
        MLX90614 --> SensorLogic
        HX710B --> SensorLogic
        SensorLogic --> AlertSystem
        AlertSystem --> MQTTClient
        MQTTClient --> RESTClient
        SensorLogic --> SQLite
    end
    
    subgraph "Cloud Infrastructure"
        subgraph "MQTT Broker"
            HiveMQ[HiveMQ Cloud<br/>Singapore<br/>Port: 8883 (TLS)]
        end
        
        subgraph "REST API Server"
            FlaskAPI[Flask API<br/>AWS EC2<br/>Port: 8000]
        end
        
        subgraph "Database"
            MySQL[(MySQL 8.0.44<br/>AWS RDS<br/>iot_health_cloud)]
        end
        
        HiveMQ --> FlaskAPI
        FlaskAPI --> MySQL
    end
    
    subgraph "Android Mobile App"
        subgraph "UI Layer"
            ComposeUI[Jetpack Compose<br/>Material 3]
            QRScanner[QR Scanner<br/>ZXing]
        end
        
        subgraph "Business Logic"
            ViewModels[ViewModels<br/>MVVM]
            Repositories[Repositories<br/>Data Access]
        end
        
        subgraph "Data Layer"
            RoomDB[(Room DB<br/>SQLite Cache)]
            MQTTAndroid[MQTT Client<br/>Paho Android]
            Retrofit[Retrofit<br/>REST API]
        end
        
        subgraph "Services"
            FCM[Firebase Cloud<br/>Messaging]
            WorkManager[Work Manager<br/>Background Tasks]
        end
        
        ComposeUI --> ViewModels
        QRScanner --> ViewModels
        ViewModels --> Repositories
        Repositories --> RoomDB
        Repositories --> MQTTAndroid
        Repositories --> Retrofit
        MQTTAndroid --> FCM
        ViewModels --> WorkManager
    end
    
    %% Data Flow
    MQTTClient --> HiveMQ
    HiveMQ --> MQTTAndroid
    
    RESTClient --> FlaskAPI
    Retrofit --> FlaskAPI
    
    FlaskAPI --> MySQL
    RoomDB --> MySQL
    
    %% Status Flow
    MQTTClient -.->|Status Updates| HiveMQ
    HiveMQ -.->|Real-time Data| MQTTAndroid
    AlertSystem -.->|Alerts| FCM
    
    %% Pairing Flow
    QRScanner -.->|Scan QR Code| RESTClient
    RESTClient -.->|Pair Device| FlaskAPI
    FlaskAPI -.->|Device Info| Retrofit
    
    %% Patient Management
    ComposeUI -.->|Add Patient| Retrofit
    Retrofit -.->|Patient Data| FlaskAPI
    FlaskAPI -.->|Store Patient| MySQL
    
    %% Sync Flow
    SQLite -.->|Auto Sync| MySQL
    RoomDB -.->|Offline Cache| MySQL
```

### Detailed Workflow Steps

#### 1. Device Setup & Pairing
```mermaid
sequenceDiagram
    participant Pi as Raspberry Pi
    participant GUI as Kivy GUI
    participant API as REST API
    participant DB as MySQL DB
    participant App as Android App

    Pi->>GUI: Generate pairing_code (ABC123XY)
    GUI->>GUI: Display QR code
    App->>App: Scan QR code
    App->>API: POST /api/pair-device
    API->>DB: Verify pairing_code
    DB-->>API: Device info
    API->>DB: Create device_ownership
    API-->>App: device_info, mqtt_topics
    App->>App: Subscribe MQTT topics
    App->>API: POST /api/patient (optional)
    API->>DB: Create patient + thresholds
    API-->>App: patient_info, commands_topic
```

#### 2. Real-time Monitoring Flow
```mermaid
sequenceDiagram
    participant Pi as Raspberry Pi
    participant MQTT as HiveMQ Cloud
    participant App as Android App
    participant DB as MySQL DB

    loop Every measurement
        Pi->>Pi: Collect sensor data
        Pi->>Pi: Process & validate
        Pi->>Pi: Check thresholds
        Pi->>MQTT: Publish vitals (QoS 1)
        Pi->>MQTT: Publish alerts (QoS 2, if any)
        MQTT-->>App: Real-time vitals
        App->>App: Update UI
        App->>App: Store in Room DB
        App->>DB: Sync to cloud (background)
    end
    
    Pi->>MQTT: Publish status (QoS 0, every 60s)
    MQTT-->>App: Device status updates
```

#### 3. Alert & Notification Flow
```mermaid
sequenceDiagram
    participant Pi as Raspberry Pi
    participant MQTT as HiveMQ Cloud
    participant FCM as Firebase Cloud Messaging
    participant App as Android App

    Pi->>Pi: Detect critical vital signs
    Pi->>Pi: Generate alert payload
    Pi->>MQTT: Publish alert (QoS 2)
    MQTT-->>App: Alert notification
    App->>FCM: Trigger push notification
    FCM-->>App: Display critical alert
    App->>App: TTS voice alert (if enabled)
    App->>App: Emergency contact (if configured)
```

#### 4. Data Synchronization Flow
```mermaid
sequenceDiagram
    participant Pi as Raspberry Pi
    participant SQLite as Local SQLite
    participant API as REST API
    participant MySQL as Cloud MySQL
    participant App as Android App
    participant Room as Room DB

    Pi->>SQLite: Store measurements locally
    SQLite->>API: Auto-sync every 5 min
    API->>MySQL: Batch insert/update
    
    App->>Room: Cache received data
    Room->>API: Sync when online
    API->>MySQL: Update cloud database
    
    Note over Pi,MySQL: Conflict resolution: Cloud wins
```

### Data Flow Summary

| Component | Input | Processing | Output |
|-----------|-------|------------|--------|
| **Raspberry Pi** | Sensor data | Validation, Alert checking | MQTT vitals/alerts/status |
| **REST API** | HTTP requests | Business logic, DB operations | JSON responses |
| **MySQL DB** | SQL queries | Data persistence | Query results |
| **MQTT Broker** | MQTT messages | Message routing | Topic distribution |
| **Android App** | MQTT messages, API responses | UI updates, Local storage | User interactions |

### Error Handling & Recovery

#### Connection Failures
- **MQTT**: Auto-reconnect with exponential backoff (5s → 60s)
- **REST API**: Retry with circuit breaker pattern
- **Database**: Connection pooling, failover to local cache

#### Data Consistency
- **Optimistic locking** for concurrent updates
- **Store-and-forward** for offline scenarios
- **Conflict resolution** policies (cloud wins)

#### Monitoring & Alerts
- **Health checks** every 30 seconds
- **Error logging** with structured format
- **Performance metrics** collection
- **Automated recovery** procedures

---

## Testing

### HiveMQ Cloud Connection Test
```bash
# CRITICAL: Set MQTT password in .env first
nano .env
# Replace <REPLACE_WITH_YOUR_HIVEMQ_PASSWORD> with your actual password

# Test HiveMQ Cloud connectivity (3 tests)
python tests/test_hivemq_connection.py

# Expected output:
# ✅ Test 1: Basic Connection - Connects to HiveMQ Cloud, verifies TLS
# ✅ Test 2: Publish Vitals - Sends sample vitals payload to broker
# ✅ Test 3: Subscribe Commands - Listens for commands from Android/Web
```

### Legacy MQTT Test
```bash
# Test MQTT broker connectivity (test.mosquitto.org - deprecated)
python tests/test_mqtt_connection.py

## Deployment Checklist

### Raspberry Pi Setup
- [x] Hardware assembly (sensors, pump, valve, optocouplers)
- [x] GPIO configuration (HX710B: GPIO5/6, Pump: GPIO26, Valve: GPIO16)
- [x] I2C sensors (MAX30102: 0x57, MLX90614: 0x5A)
- [x] SPI LCD 3.5" (480x320, framebuffer /dev/fb1)
- [x] MQTT client (test.mosquitto.org:1883)
- [x] MySQL cloud sync (192.168.2.15:3306)
- [x] PiperTTS (vi_VN voice for audio alerts)

### Cloud Infrastructure
- [x] MySQL database (iot_health_cloud)
- [x] MQTT broker (HiveMQ Cloud - Singapore region, free tier)
- [x] TLS/SSL certificates (Let's Encrypt via HiveMQ)
- [x] Device credentials (rpi_bp_001, android_app)
- [x] **REST API server (Flask + AWS EC2 - http://47.130.193.237:8000)**
- [ ] Production MQTT ACL rules (HiveMQ dashboard)
- [ ] CI/CD pipeline (GitHub Actions - planned)

### Android App
- [x] Architecture design (MVVM + Clean)
- [x] UI/UX layouts (8 screens documented)
- [x] MQTT topics structure
- [x] Database schema (Room + MySQL)
- [ ] Implementation (Kotlin + Compose - in progress)
- [ ] Testing (Unit + Integration + UI tests)
- [ ] Play Store deployment

## Đóng góp
Dự án đồ án tốt nghiệp - IoT Health Monitoring System

### Team
- Hardware & Embedded: Raspberry Pi, Sensors, Blood Pressure measurement
- Backend: Python, MQTT, MySQL, Cloud Sync
- Mobile: Android (Kotlin + Jetpack Compose)
- AI/ML: Anomaly detection, Trend analysis

### Technologies
- **Embedded**: Python 3.9+, Kivy, smbus2, RPi.GPIO
- **Communication**: Paho MQTT, SQLAlchemy, Requests, **Flask + Gunicorn (REST API)**
- **Database**: SQLite, MySQL 8.0
- **Mobile**: Kotlin, Jetpack Compose, Hilt, Room, Retrofit
- **AI/ML**: scikit-learn, IsolationForest
- **Audio**: PiperTTS (Vietnamese TTS)
- **Cloud**: AWS EC2, AWS RDS, HiveMQ Cloud

### Contact
- GitHub: github.com/danhsidoi1234/Iot_health
- **REST API Server**: http://47.130.193.237:8000
- **MySQL Database**: database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com:3306
- **MQTT Broker**: c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud:8883
- Project Status: Active Development