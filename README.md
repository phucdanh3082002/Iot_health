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

## Cấu hình

### Sensors
- MAX30102: I2C address 0x57, INT pin GPIO4
- DS18B20: 1-Wire GPIO17
- Blood Pressure: MPX2050 + ADS1115

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