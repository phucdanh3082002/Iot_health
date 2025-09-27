# IoT Health Monitoring System - GUI Interface

## Tổng quan

Giao diện người dùng được thiết kế đặc biệt cho màn hình cảm ứng 3.5 inch (480x320 pixels) với các tính năng:

### Màn hình chính (Dashboard)
- **Hiển thị real-time**: Nhịp tim, SpO2, nhiệt độ, huyết áp
- **Màu sắc trực quan**: 
  - 🟢 Xanh lá: Bình thường
  - 🟡 Vàng: Thấp
  - 🟠 Cam: Cao
  - 🔴 Đỏ: Nguy hiểm
  - ⚫ Xám: Không có tín hiệu
- **Thông tin bệnh nhân**: Tên, thời gian hiện tại
- **Điều hướng nhanh**: Đo huyết áp, Lịch sử, Cài đặt, Khẩn cấp

### Màn hình đo huyết áp
- **Quy trình tự động**: Hướng dẫn từng bước
- **Hiển thị tiến độ**: Thanh progress bar và trạng thái
- **Áp suất real-time**: Hiển thị áp suất hiện tại trong quá trình đo
- **Kết quả chi tiết**: Tâm thu/tâm trương với đánh giá màu sắc
- **Hướng dẫn giọng nói**: Tiếng Việt với espeak-ng

### Màn hình lịch sử
- **Bộ lọc thời gian**: Hôm nay, Tuần này, Tháng này, Tất cả
- **Bảng dữ liệu**: Thời gian, nhịp tim, SpO2, nhiệt độ, huyết áp
- **Màu sắc phân loại**: Theo mức độ bình thường của từng chỉ số
- **Xuất dữ liệu**: Tính năng export cho backup

### Màn hình cài đặt
- **Cấu hình cảm biến**: Bật/tắt, hiệu chỉnh, độ sáng LED
- **Cài đặt hiển thị**: Độ sáng màn hình, tần suất cập nhật
- **Cảnh báo**: Âm lượng, ngưỡng cảnh báo, test giọng nói
- **Thông tin hệ thống**: Tên bệnh nhân, backup dữ liệu

## Tính năng đặc biệt

### Thiết kế cho người cao tuổi
- **Font chữ lớn**: Dễ đọc trên màn hình nhỏ
- **Nút bấm lớn**: Phù hợp với màn hình cảm ứng
- **Màu sắc tương phản cao**: Dễ phân biệt trạng thái
- **Giao diện đơn giản**: Ít tính năng phức tạp trên một màn hình

### Hỗ trợ tiếng Việt
- **Giao diện**: Toàn bộ tiếng Việt
- **Giọng nói**: espeak-ng với voice tiếng Việt
- **Hướng dẫn**: Các thông báo và chỉ dẫn bằng tiếng Việt

### Tương thích hardware
- **Raspberry Pi 4B**: Tối ưu cho ARM processor
- **Màn hình Waveshare 3.5"**: Độ phân giải 480x320
- **Màn hình cảm ứng**: Hỗ trợ touch input
- **Audio**: espeak-ng cho text-to-speech

## Cài đặt và chạy

### Yêu cầu hệ thống
```bash
# Cài đặt Kivy dependencies
sudo apt-get update
sudo apt-get install python3-pip python3-dev
sudo apt-get install libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev
sudo apt-get install libgstreamer1.0-dev gstreamer1.0-plugins-base-dev

# Cài đặt espeak-ng cho tiếng Việt
sudo apt-get install espeak-ng espeak-ng-data

# Cài đặt Python packages
pip3 install kivy pygame numpy
```

### Chạy demo GUI
```bash
cd /home/pi/Desktop/IoT_health
python3 demo_gui.py
```

### Chạy với hardware thật
```bash
cd /home/pi/Desktop/IoT_health
python3 main.py
```

## Cấu trúc file

```
src/gui/
├── __init__.py              # Module exports
├── main_app.py              # Ứng dụng chính Kivy
├── dashboard_screen.py      # Màn hình dashboard
├── bp_measurement_screen.py # Màn hình đo huyết áp
├── history_screen.py        # Màn hình lịch sử
└── settings_screen.py       # Màn hình cài đặt
```

## API chính

### HealthMonitorApp
- `navigate_to_screen(screen_name)`: Chuyển màn hình
- `get_sensor_data()`: Lấy dữ liệu cảm biến hiện tại
- `save_measurement_to_database()`: Lưu phép đo vào database

### Sensor Callbacks
```python
def on_max30102_data(sensor_name: str, data: Dict[str, Any]):
    # Xử lý dữ liệu MAX30102 (nhịp tim, SpO2)
    
def on_temperature_data(sensor_name: str, data: Dict[str, Any]):
    # Xử lý dữ liệu nhiệt độ MLX90614
```

### Widget tùy chỉnh
- `VitalSignCard`: Hiển thị một chỉ số sinh hiệu
- `BloodPressureCard`: Hiển thị huyết áp (2 giá trị)
- `SettingSection`: Nhóm các cài đặt
- `MeasurementRecord`: Một dòng trong lịch sử

## Troubleshooting

### Lỗi màn hình
```bash
# Kiểm tra Kivy config
export KIVY_WINDOW=sdl2
export KIVY_GL_BACKEND=gl

# Chế độ fullscreen
export KIVY_GRAPHICS_WIDTH=480
export KIVY_GRAPHICS_HEIGHT=320
```

### Lỗi audio
```bash
# Kiểm tra espeak-ng
espeak-ng -v vi "Xin chào"

# Kiểm tra ALSA
aplay /usr/share/sounds/alsa/Front_Left.wav
```

### Lỗi cảm biến
```bash
# Kiểm tra I2C
sudo i2cdetect -y 1

# Test cảm biến
python3 tests/test_sensors.py
```

## Tùy chỉnh

### Thay đổi màu sắc
Chỉnh sửa trong từng file screen, ví dụ:
```python
status_colors = {
    'normal': (0.2, 0.8, 0.2, 1),      # Green
    'high': (1, 0.6, 0, 1),            # Orange  
    'critical': (1, 0.2, 0.2, 1),     # Red
}
```

### Thay đổi ngưỡng cảnh báo
Chỉnh sửa trong `dashboard_screen.py`:
```python
def _get_heart_rate_status(self, hr: float) -> str:
    if hr < 50:     # Thay đổi ngưỡng thấp
        return 'critical'
    elif hr > 120:  # Thay đổi ngưỡng cao
        return 'high'
```

### Thêm ngôn ngữ khác
1. Thay đổi text trong các Label
2. Cập nhật espeak-ng voice: `-v en` cho tiếng Anh

## Performance

### Tối ưu cho Raspberry Pi
- Sử dụng `NoTransition` cho ScreenManager
- Giảm tần suất cập nhật UI (1s thay vì realtime)
- Không vẽ animation phức tạp
- Sử dụng background thread cho sensor reading

### Memory usage
- Giới hạn buffer size cho lịch sử
- Clear widgets khi không sử dụng
- Tránh memory leak với Clock events

Giao diện này được thiết kế để đảm bảo trải nghiệm tốt nhất cho người cao tuổi trên màn hình cảm ứng nhỏ với hiệu năng tối ưu trên Raspberry Pi.