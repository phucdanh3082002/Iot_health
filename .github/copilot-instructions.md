# Copilot Instructions — IoT Health Monitor

## Mục tiêu dự án
Hệ thống IoT giám sát sức khỏe trên Raspberry Pi:
- Sensors: MAX30102 (HR/SpO2), MLX90614 (Temperature), HX710B (Blood Pressure)
- UI: Kivy/KivyMD trên LCD 480x320
- Data: SQLite local + MySQL cloud + MQTT realtime
- Audio/TTS: PiperTTS
- OS: Raspberry Pi OS Bookworm 64-bit

## Tóm tắt kiến trúc
- Sensors: `src/sensors/`
- GUI: `src/gui/`
- Communication: `src/communication/` (MQTT + REST + sync)
- Data/DB: `src/data/`
- Alerts/AI: `src/ai/`
- Utils: `src/utils/`

## Cấu hình & file liên quan (map nhanh)
- **Sensors** (config `sensors.*`):
  - `src/sensors/max30102_sensor.py`
  - `src/sensors/mlx90614_sensor.py`
  - `src/sensors/hx710b_sensor.py`
  - `src/sensors/blood_pressure_sensor.py`
- **GUI**:
  - `src/gui/main_app.py`
  - `src/gui/dashboard_screen.py`
  - `src/gui/heart_rate_screen.py`
  - `src/gui/temperature_screen.py`
  - `src/gui/bp_measurement_screen.py`
- **MQTT** (config `communication.mqtt.*`):
  - `src/communication/mqtt_client.py`
  - `src/communication/mqtt_payloads.py`
- **REST API** (config `communication.rest_api.*`):
  - `src/communication/rest_client.py`
  - `scripts/api.py`
- **Cloud Sync** (config `cloud.*`, `communication.store_forward.*`):
  - `src/communication/cloud_sync_manager.py`
  - `src/communication/store_forward.py`
  - `src/communication/sync_scheduler.py`
  - `src/data/models.py`
  - `src/data/database.py`
- **Database** (config `database.*`):
  - `src/data/database.py`
  - `src/data/models.py`
  - `src/data/database_extensions.py`
  - `scripts/migrate_database.py`
  - `scripts/migrate_sqlite_device_centric.py`
  - `scripts/migrate_sqlite_ai_thresholds.py`
  - `scripts/query_database.py`
  - `scripts/mysql_cloud_schema.sql`
- **Alerts/Thresholds** (config `threshold_management.*`):
  - `src/ai/alert_system.py`
  - `scripts/ai_threshold_generator.py`
  - `docs/THRESHOLD_AI_GENERATION_ANALYSIS.md`
- **TTS/Audio** (config `audio.*`):
  - `src/utils/tts_manager.py`
  - `src/utils/export_tts_assets.py`
- **Device-centric**:
  - `docs/DEVICE_CENTRIC_APPROACH.md`
- **Database cloud structure**:
  - `docs/scripts/Database_mysql.sql`
- **Server Instance**:
  IP: 47.130.193.237
  key : /home/pi/Desktop/IoT_health/key-server/iot-health-api-key.pem
## MQTT Communication (không đổi nếu chưa được yêu cầu)

Broker: c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud (HiveMQ Cloud Singapore)
Port: 8883 (TLS required) / 8884 (WebSocket for web dashboard)
Protocol: MQTT v3.1.1

- Broker: HiveMQ Cloud, TLS bắt buộc (port 8883)
- QoS: Vitals=1, Alerts=2, Status=0, Commands=2
- Topic template:
  - `iot_health/device/{device_id}/vitals`
  - `iot_health/device/{device_id}/alerts`
  - `iot_health/device/{device_id}/status`
  - `iot_health/patient/{patient_id}/commands`
- Payload schemas: xem `src/communication/mqtt_payloads.py`

## Quy tắc bắt buộc
### Code Quality
- OOP rõ ràng; docstring cho class/method
- PEP8 + type hints
- Chỉ thêm comment khi logic không tự giải thích

### Documentation & Tests
- Không tạo file documents tóm tắt , tóm tắt trong câu trả lời
- Không tạo file .md mới nếu chưa được yêu cầu
- Không tạo test file mới nếu chưa được yêu cầu

### Project Structure
- Không đổi cấu trúc thư mục khi chỉ sửa code
- Không đổi API/schema (MQTT topics, REST endpoints, DB) nếu chưa được hỏi
- Không tạo dummy/mock data

### Security
- Không commit secrets
- Dùng config/env cho credentials
## App android
Repo android: https://github.com/danhsidoi1234/Iot_app
### Communication
- Trả lời bằng tiếng Việt (được dùng thuật ngữ kỹ thuật tiếng Anh)
- Nếu yêu cầu chưa rõ, phải hỏi lại

## 💬 Workflow khi nhận yêu cầu

1. **Đọc yêu cầu kỹ**: Hiểu đầy đủ trước khi code
2. **Hỏi lại nếu không rõ**: "Bạn muốn thay đổi X hay Y?"
3. **Kiểm tra file hiện có**: Đọc code liên quan trước
4. **Đề xuất giải pháp**: Giải thích approach trước khi implement
5. **Code theo quy tắc**: OOP, comments, organization
6. **Test suggestion**: "Hãy test bằng cách..."
7. **Không tạo docs**: Trừ khi được yêu cầu
---
## ✨ Definition of Done

* Không sinh file rác; repo sạch.
* UI mượt (ví dụ: không lag >100ms trong đo BP; phản hồi touch <50ms); driver HX710B bền; an toàn đo (limit/timeout/xả khẩn).
* MQTT/REST/SQLite đúng schema hiện có; log đầy đủ cho debug (mức INFO/ERROR với timestamp, context); không lộ secrets.
* Tuân thủ BaseSensor pattern và callback architecture.
* Tích hợp với existing testing framework.