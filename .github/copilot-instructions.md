# Copilot Instructions — IoT Health (RPi + Waveshare 3.5" + MAX98357A + **HX710B**)

## Mục tiêu dự án

Xây dựng hệ thống IoT theo dõi sức khỏe: HR/SpO₂ (**MAX30102**), Nhiệt độ (**MLX90614/GY-906**), **Huyết áp dao động học** (cảm biến 0–40 kPa **với ADC HX710B**), UI Kivy 480×320 trên màn **Waveshare 3.5"**, phát hướng dẫn/kết quả/cảnh báo qua loa **MAX98357A I²S**, đồng bộ qua **MQTT/REST**, lưu **SQLite**, mở rộng AI (anomaly/trend/chat) trên server PC.

---

## QUY TẮC BẮT BUỘC

* **KHÔNG** tạo **dummy files**, **sample/mocked data**, asset giả (.wav/.jpg/.json) **khi chưa có yêu cầu**.
* **KHÔNG** tự ý sinh thêm thư mục; giữ nguyên cấu trúc dự án.
* **KHÔNG** thay đổi API/public schema (MQTT topics, REST endpoints, DB schema) nếu không có yêu cầu rõ.
* **KHÔNG** commit secrets (token, mật khẩu). Dùng biến môi trường / file cấu hình hiện có.
* Tuân thủ **OOP, module hóa**, Python 3.11+, PEP8, logging chuẩn của dự án.
* Tôn trọng kiến trúc **Hybrid**: Edge (Pi) ổn định; Server (PC) mở rộng.

---

## Cấu trúc thư mục (giữ nguyên)

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
```

---

## Phần cứng đã chốt

* **Raspberry Pi 4B/5**, **Waveshare 3.5" SPI** (fbcp mirror).
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
| HX710B    | DOUT (in)          | GPIO17 (11)                   |
| HX710B    | SCK  (out)         | GPIO27 (13)                   |
| I²S       | BCLK / LRCLK / DIN | 18 (12) / 19 (35) / 21 (40)   |
| I²C       | SDA / SCL          | 2 (3) / 3 (5)                 |
| Bơm / Van | EN                 | GPIO bất kỳ → (opto) → MOSFET |

> HX710B **cấp 3.3 V** để tương thích mức logic GPIO. DOUT có thể cần pull-up nếu board không tích hợp.

---

## Yêu cầu kỹ thuật cho **HX710B** (quan trọng)

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

## Quy trình BP (oscillometric) – ràng buộc cho Copilot

* **State machine**: `IDLE → INFLATE → DEFLATE → PROCESS → DONE/ABORT`.
* **Inflate**: bơm nhanh đến ~160–170 mmHg; **soft-limit 200 mmHg**; luôn cho phép **xả khẩn**.
* **Deflate**: xả đều ~**2–4 mmHg/s** (điều khiển van bằng PWM/chu kỳ mở–đóng); **ghi áp liên tục** từ HX710B.
* **Process**:
  * Detrend áp nền giảm; **BPF 0.5–5 Hz** (nhẹ, biên độ không méo).
  * Tính **envelope** (ví dụ Hilbert/peak-to-peak window).
  * **MAP** tại biên độ cực đại; **SYS/DIA** từ **tỷ lệ** so với A_max (hệ số nằm trong config, hiệu chuẩn theo máy tham chiếu).
* **An toàn**:
  * Quá áp/timeout/rò khí → **ngắt bơm + mở van** ngay; log + alert.
  * **Van NO** + **van relief** là lớp bảo vệ cứng (phần mềm luôn nhường ưu tiên an toàn).

---

## Kiến trúc sensor hiện tại (tuân thủ)

### BaseSensor Pattern
```python
# Tất cả sensor kế thừa từ BaseSensor trong src/sensors/base_sensor.py
class HX710BSensor(BaseSensor):
    def __init__(self, config: Dict[str, Any]):
        super().__init__("HX710B", config)
        # GPIO setup cho DOUT/SCK
    
    def start(self) -> bool:
        # Khởi động thread đọc bit-bang
        
    def read_raw_data(self) -> Optional[Dict[str, Any]]:
        # Đọc 24-bit từ HX710B
        
    def process_data(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Chuyển đổi counts → mmHg
```

### Callback Pattern
```python
# Standard callback cho tất cả sensors
def sensor_callback(sensor_name: str, data: Dict[str, Any]):
    timestamp = data.get('timestamp')
    if sensor_name == 'HX710B':
        pressure_mmhg = data.get('pressure_mmhg')
        counts = data.get('raw_counts')
```

---

## Yêu cầu phần mềm (Copilot phải tuân thủ)

1. **GUI Kivy 480×320** (fullscreen borderless): Dashboard (HR/SpO₂/Temp/BP), đo BP, lịch sử, cài đặt; **không block** UI.
2. **Driver HX710B**: bit-banged, **thread-safe**, non-blocking; API rõ ràng:
   * `start() / stop()` theo pattern BaseSensor;
   * `set_data_callback()` push vào callback `{ts, counts, pressure_mmhg}`;
   * timeout khi không có data-ready; xử lý lỗi gọn.
3. **Chuyển đổi áp**: lớp xử lý ánh xạ `counts → mmHg` qua **calibration** (offset/slope) lấy từ config; **không hardcode**.
4. **Thu pha xả**: đảm bảo tần suất đọc theo khả năng HX710B (10–80 SPS), **đo thời gian chuẩn** để tính mmHg/s.
5. **Cảnh báo**: popup + **TTS** (espeak-ng) qua wrapper hiện có; **debounce** alert.
6. **MQTT/REST**: dùng client sẵn trong `communication/`; schema/topics **không đổi**.
7. **SQLite**: ghi `ts, hr, spo2, temp, bp_sys, bp_dia, bp_map, alert`; **không** ghi dữ liệu giả.
8. **Config**: đọc `config/app_config.yaml`; **không** sinh file cấu hình mới khi chưa yêu cầu.

---

## Testing Framework (giữ nguyên pattern)

* Sử dụng `tests/test_sensors.py` menu-driven interface
* Hardware validation với I²C scanning
* Không tạo mock data hoặc dummy files
* Test với phần cứng thật: HX710B DOUT/SCK, bơm/van

```bash
# Test HX710B driver
python tests/test_sensors.py  # Menu option cho HX710B
```

---

## Không được làm

* Không sinh **file giả**, **mẫu dữ liệu**, **test asset**.
* Không tự tạo thư mục `samples/`, `fixtures/`, `assets/`…
* Không đổi sơ đồ chân I²S/SPI/I²C/HX710B.
* Không tự ý chuyển sang ADC khác (ADS1115/ADS1220…) nếu chưa có yêu cầu.
* Không thay đổi BaseSensor interface hoặc callback pattern hiện có.

---

## Tham số cấu hình bắt buộc (thêm vào app_config.yaml)

```yaml
# Thêm vào sensors section
sensors:
  hx710b:
    enabled: true
    gpio_dout: 17
    gpio_sck: 27
    sps_hint: 50  # Expected samples per second
    calibration:
      offset_counts: 0      # Zero offset
      slope_mmhg_per_count: 0.001  # Conversion factor
    timeout_ms: 1000
    
  blood_pressure:
    enabled: true
    inflate_target_mmhg: 165
    deflate_rate_mmhg_s: 3.0
    max_pressure_mmhg: 200
    pump_gpio: 18
    valve_gpio: 19
    ratio:
      sys_frac: 0.5   # SYS at 50% of max amplitude
      dia_frac: 0.8   # DIA at 80% of max amplitude
```

---

## Mẫu prompt gợi ý dùng cho Copilot

* "Implement **HX710B** bit-bang driver inheriting from BaseSensor (DOUT/SCK) in background thread. Use existing callback pattern. **Do not** create test files or mock data."
* "Add BP deflate controller targeting **2–4 mmHg/s** using existing GPIO patterns; measure pressure change over time based on HX710B samples; keep UI responsive."
* "Convert HX710B counts to **mmHg** using calibration from app_config.yaml (offset/slope). Follow existing config loading pattern."
* "Compute oscillometric **envelope** (0.5–5 Hz band) to estimate **MAP**, then **SYS/DIA** via configured fractions; integrate with existing blood_pressure_sensor.py structure."
* "Wire **TTS** alerts using existing Vietnamese TTS wrapper for overpressure/timeout/leak and final results; add debounce."

---

## Import Pattern (tuân thủ)

```python
# Standard project root path resolution
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import existing modules
from src.sensors.base_sensor import BaseSensor
from src.utils.logger import setup_logger
```

---

## Commit message gợi ý

* `feat(hx710b): add non-blocking driver with BaseSensor inheritance, queue-based output`
* `feat(bp): deflate controller at 3 mmHg/s; compute MAP from envelope using HX710B`
* `fix(ui): avoid main-thread blocking during BP measurement with existing Kivy patterns`
* `chore(cfg): add bp.calibration and hx710b config to app_config.yaml (no new files)`

---

## Kiểm thử thủ công (không sinh dữ liệu giả)

* Chạy GUI trên HDMI/VNC 480×320; **không** tạo ảnh/video test.
* Dùng phần cứng thật: bơm/van/hx710b/cuff; xác nhận inflate/deflate, an toàn (soft-limit, NO, relief).
* Test với `tests/test_sensors.py` menu system.
* Xem log: driver HX710B không timeout quá lâu; tốc độ đọc phù hợp SPS thực.
* Nghe TTS rõ khi bơm chạy (nguồn sạch, không clip).

---

## Definition of Done

* Chạy ổn **với phần cứng thật**; không phụ thuộc dữ liệu giả.
* Không sinh file rác; repo sạch.
* UI mượt; driver HX710B bền; an toàn đo (limit/timeout/xả khẩn).
* MQTT/REST/SQLite đúng schema hiện có; log rõ ràng; không lộ secrets.
* Tuân thủ BaseSensor pattern và callback architecture.
* Tích hợp với existing testing framework.

---

**Tóm tắt cho Copilot:**
Hoàn thiện **đo huyết áp với HX710B** theo kiến trúc hiện tại: driver bit-bang non-blocking kế thừa BaseSensor, thu pha xả đúng tốc độ, xử lý oscillometric để ước lượng MAP → SYS/DIA từ calibration, UI Kivy 480×320, TTS qua MAX98357A, MQTT/REST, SQLite. **Không** tạo file/dữ liệu giả và **không** tự ý thay đổi kiến trúc. Tuân thủ patterns: BaseSensor inheritance, callback system, config loading, testing framework, Vietnamese TTS integration.