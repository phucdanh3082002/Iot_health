# Copilot Instructions — IoT Health Monitor

## 🎯 Mục tiêu dự án

Hệ thống IoT giám sát sức khỏe trên Raspberry Pi:
- **Sensors**: MAX30102 (HR/SpO₂), MLX90614 (Temperature), HX710B (Blood Pressure)
- **Display**: Waveshare 3.5" LCD (480×320)
- **Audio**: MAX98357A I²S (TTS feedback)
- **Data**: SQLite local + MQTT/REST sync
- **UI**: Kivy/KivyMD
- **TTS**: PiperTTS
- **TTS**: pi os bookworm 64 bit
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
config/               # app_config.yaml (ngưỡng, mqtt, rest…)
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

1. **GUI Kivy 480×320** (fullscreen borderless): Dashboard (HR/SpO₂/Temp/BP), đo BP, lịch sử, cài đặt; **không block** UI.
2. **Driver HX710B**: bit-banged, **thread-safe**, non-blocking; API rõ ràng:
   * `start() / stop()` theo pattern BaseSensor;
   * `set_data_callback()` push vào callback `{ts, counts, pressure_mmhg}`;
   * timeout khi không có data-ready; xử lý lỗi gọn.
3. **Chuyển đổi áp**: lớp xử lý ánh xạ `counts → mmHg` qua **calibration** (offset/slope) lấy từ config; **không hardcode**.
4. **Thu pha xả**: đảm bảo tần suất đọc theo khả năng HX710B (10–80 SPS), **đo thời gian chuẩn** để tính mmHg/s.
5. **Cảnh báo**: popup + **TTS** (PiperTTS)  **debounce** alert.
6. **MQTT/REST**: dùng client sẵn trong `communication/`; schema/topics **không đổi**.
7. **SQLite**: ghi `ts, hr, spo2, temp, bp_sys, bp_dia, bp_map, alert`; **không** ghi dữ liệu giả.
8. **Config**: đọc `config/app_config.yaml`; **không** sinh file cấu hình mới khi chưa yêu cầu.

---

---

## 🚫 CÁC HÀNH ĐỘNG CẤM TUYỆT ĐỐI

* Không sinh **file giả**, **mẫu dữ liệu**, **test asset**.
* Không đổi sơ đồ chân I²S/SPI/I²C/HX710B.
* Không tự ý chuyển sang ADC khác (ADS1115/ADS1220…) nếu chưa có yêu cầu.
* Không thay đổi BaseSensor interface hoặc callback pattern hiện có.

---

## ⚙️ Tham số cấu hình bắt buộc (thêm vào app_config.yaml)

```yaml
# Thêm vào sensors section
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