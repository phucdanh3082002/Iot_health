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
- [ ] MQTT client implementation
- [ ] REST API integration
- [ ] Store-forward offline support

### Phase 3 - Advanced Features
- [ ] Blood pressure measurement
- [ ] AI anomaly detection
- [ ] Android app integration
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
      P_GPIO27["GPIO27 → Bơm (LED 4N35)"]
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
      O1["4N35 (Pump)\npin1←GPIO27 qua 330Ω; pin2→GND Pi\npin5←+6V; pin4→R_gate→Gate Q1"]
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
- MQTT: localhost:1883 (configurable)
- REST API: http://localhost:8000
- Store-forward: SQLite queue

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

## Đóng góp
Dự án đồ án tốt nghiệp - IoT Health Monitoring System