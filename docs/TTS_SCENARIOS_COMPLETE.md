# Kịch Bản TTS Đầy Đủ - IoT Health Monitor

## 📋 Tổng Quan

**Đối tượng**: Người cao tuổi tự sử dụng tại nhà/viện dưỡng lão  
**Ngôn ngữ**: Tiếng Việt  
**Phong cách**: Ngắn gọn, rõ ràng, dễ hiểu  
**Tổng số kịch bản hiện tại**: 30 scenarios

---

## ✅ CÁC KỊCH BẢN HIỆN CÓ (30 scenarios)

### 1. HỆ THỐNG (4 scenarios)

| ID | Tình huống | Nội dung TTS | Cooldown | Trạng thái |
|---|---|---|---|---|
| `SYSTEM_START` | Khởi động hệ thống | "Hệ thống IoT Health đã khởi động. Vui lòng đợi cảm biến ổn định." | 5s | ✅ Đã có |
| `SYSTEM_SHUTDOWN` | Tắt hệ thống | "Đang tắt hệ thống IoT Health, hẹn gặp lại." | 5s | ✅ Đã có |
| `NAVIGATE_DASHBOARD` | Chuyển màn hình chính | "Đang chuyển sang màn hình chính." | 2s | ✅ Đã có |
| `SETTINGS_UPDATED` | Cập nhật cài đặt | "Cập nhật cấu hình thành công." | 10s | ✅ Đã có |

### 2. MẠNG & ĐỒNG BỘ (5 scenarios)

| ID | Tình huống | Nội dung TTS | Cooldown | Trạng thái |
|---|---|---|---|---|
| `NETWORK_CONNECTED` | Kết nối mạng thành công | "Đã kết nối mạng thành công." | 10s | ✅ Đã có |
| `NETWORK_DISCONNECTED` | Mất kết nối mạng | "Mất kết nối mạng, hệ thống sẽ thử lại trong giây lát." | 10s | ✅ Đã có |
| `MQTT_PUBLISH_OK` | Gửi dữ liệu thành công | "Đã gửi dữ liệu lên máy chủ." | 15s | ✅ Đã có |
| `MQTT_PUBLISH_FAIL` | Gửi dữ liệu thất bại | "Không gửi được dữ liệu, hệ thống sẽ thử lại." | 15s | ✅ Đã có |
| `STORE_FORWARD_ACTIVE` | Chế độ offline | "Chế độ offline đang hoạt động, dữ liệu sẽ được gửi khi có mạng." | 30s | ✅ Đã có |

### 3. NHỊP TIM & SPO₂ (5 scenarios)

| ID | Tình huống | Nội dung TTS | Cooldown | Trạng thái |
|---|---|---|---|---|
| `HR_PROMPT_FINGER` | Yêu cầu đặt ngón tay | "Vui lòng đặt ngón tay lên cảm biến nhịp tim." | 5s | ✅ Đã có |
| `HR_NO_FINGER` | Không phát hiện ngón tay | "Không phát hiện ngón tay, xin thử lại." | 5s | ✅ Đã có |
| `HR_MEASURING` | Đang đo | "Đang đo nhịp tim và SpO₂, giữ nguyên tay trong mười lăm giây." | 6s | ✅ Đã có |
| `HR_SIGNAL_WEAK` | Tín hiệu yếu | "Tín hiệu yếu, vui lòng giữ ngón tay áp sát cảm biến." | 8s | ✅ Đã có |
| `HR_RESULT` | Kết quả đo | "Nhịp tim {bpm} nhịp mỗi phút, SpO₂ {spo2} phần trăm." | 3s | ✅ Đã có |

### 4. NHIỆT ĐỘ (9 scenarios)

| ID | Tình huống | Nội dung TTS | Cooldown | Trạng thái |
|---|---|---|---|---|
| `TEMP_PREP` | Chuẩn bị đo | "Đưa cảm biến hồng ngoại lại gần trán, cách khoảng ba đến năm centimet." | 6s | ✅ Đã có |
| `TEMP_MEASURING` | Đang đo | "Đang đo nhiệt độ cơ thể, vui lòng đứng yên." | 6s | ✅ Đã có |
| `TEMP_NORMAL` | Nhiệt độ bình thường (realtime) | "Nhiệt độ {temp} độ C, trong giới hạn bình thường." | 4s | ✅ Đã có |
| `TEMP_HIGH_ALERT` | Cảnh báo cao (realtime) | "Nhiệt độ cao bất thường, hãy kiểm tra lại hoặc liên hệ nhân viên y tế." | 15s | ✅ Đã có |
| `TEMP_RESULT_CRITICAL_LOW` | Kết quả: Rất thấp (<35°C) | "Nhiệt độ rất thấp, khoảng {temp} độ C. Cần làm ấm cơ thể ngay." | 4s | ✅ Đã có |
| `TEMP_RESULT_LOW` | Kết quả: Hơi thấp (35-36°C) | "Nhiệt độ hơi thấp, khoảng {temp} độ C." | 4s | ✅ Đã có |
| `TEMP_RESULT_NORMAL` | Kết quả: Bình thường (36-37.5°C) | "Nhiệt độ {temp} độ C, trong giới hạn bình thường." | 4s | ✅ Đã có |
| `TEMP_RESULT_FEVER` | Kết quả: Sốt nhẹ (37.5-38.5°C) | "Nhiệt độ hơi cao, khoảng {temp} độ C. Theo dõi thêm các triệu chứng." | 6s | ✅ Đã có |
| `TEMP_RESULT_HIGH_FEVER` | Kết quả: Sốt cao (38.5-40°C) | "Nhiệt độ cao {temp} độ C. Cần hạ sốt và liên hệ nhân viên y tế nếu kéo dài." | 6s | ✅ Đã có |
| `TEMP_RESULT_CRITICAL_HIGH` | Kết quả: Nguy hiểm (>40°C) | "Nhiệt độ rất cao, khoảng {temp} độ C. Đây là tình trạng nguy hiểm, cần hỗ trợ y tế khẩn." | 6s | ✅ Đã có |

### 5. HUYẾT ÁP (5 scenarios)

| ID | Tình huống | Nội dung TTS | Cooldown | Trạng thái |
|---|---|---|---|---|
| `BP_INFLATE` | Bắt đầu bơm | "Bắt đầu bơm cuff, bạn sẽ cảm thấy hơi căng." | 10s | ✅ Đã có |
| `BP_DEFLATE` | Xả khí | "Đang xả cuff, vui lòng giữ tay không cử động." | 8s | ✅ Đã có |
| `BP_OVERPRESSURE` | Áp suất nguy hiểm | "Cảnh báo áp suất nguy hiểm, cuff sẽ xả ngay lập tức." | 5s | ✅ Đã có |
| `SAFETY_EMERGENCY_RELEASE` | Xả khẩn cấp | "Áp suất vượt giới hạn, hệ thống đang xả để đảm bảo an toàn." | 5s | ✅ Đã có |
| `BP_RESULT` | Kết quả đo | "Huyết áp {sys} trên {dia} mi li mét thủy ngân, MAP {map}." | 5s | ✅ Đã có |

### 6. LỖI & BẢO TRÌ (2 scenarios)

| ID | Tình huống | Nội dung TTS | Cooldown | Trạng thái |
|---|---|---|---|---|
| `SENSOR_FAILURE` | Lỗi cảm biến | "Không thể đọc dữ liệu từ cảm biến {sensor}, vui lòng kiểm tra kết nối." | 15s | ✅ Đã có |
| `PUMP_VALVE_FAILURE` | Lỗi bơm/van | "Lỗi điều khiển bơm hoặc van, yêu cầu bảo trì." | 20s | ✅ Đã có |

### 7. ĐIỀU HƯỚNG & TƯƠNG TÁC (5 scenarios)

| ID | Tình huống | Nội dung TTS | Cooldown | Trạng thái |
|---|---|---|---|---|
| `NAVIGATION_TAP_HEART` | Hướng dẫn chạm | "Chạm vào khối nhịp tim để xem chi tiết." | 10s | ✅ Đã có |
| `HISTORY_OPEN` | Mở lịch sử | "Mở lịch sử đo, chạm vào bản ghi để xem chi tiết." | 10s | ✅ Đã có |
| `ANOMALY_DETECTED` | Phát hiện bất thường | "Phát hiện dấu hiệu bất thường trong chuỗi số đo, hãy xem lại trang cảnh báo." | 15s | ✅ Đã có |
| `CHATBOT_PROMPT` | Chatbot | "Bạn muốn biết thông tin nào? Nói 'Xin tư vấn' để kết nối chatbot." | 20s | ✅ Đã có |
| `REMINDER_DAILY` | Nhắc nhở định kỳ | "Đến giờ đo sức khỏe định kỳ, hãy chuẩn bị các cảm biến." | 60s | ✅ Đã có |

---

## 🆕 CÁC KỊCH BẢN ĐỀ XUẤT BỔ SUNG (20+ scenarios mới)

### 8. KHẨN CẤP & AN TOÀN (6 scenarios mới) ⭐ ƯU TIÊN CAO

| ID | Tình huống | Nội dung TTS đề xuất | Cooldown | Lý do |
|---|---|---|---|---|
| `EMERGENCY_BUTTON_PRESSED` | **Nhấn nút khẩn cấp** | "Đã kích hoạt cảnh báo khẩn cấp. Đang gửi thông báo đến người thân và trung tâm y tế." | 3s | **YÊU CẦU CỦA USER** |
| `EMERGENCY_CALL_INITIATED` | Đang gọi khẩn cấp | "Đang kết nối với số khẩn cấp. Vui lòng giữ máy." | 5s | Tự động gọi khi có tình huống nguy hiểm |
| `EMERGENCY_CONTACT_NOTIFIED` | Đã thông báo người thân | "Đã gửi tin nhắn khẩn cấp đến {contact_name}." | 10s | Xác nhận đã thông báo |
| `FALL_DETECTED` | Phát hiện ngã | "Phát hiện ngã đổ. Bạn có ổn không? Hệ thống sẽ gọi khẩn cấp sau mười giây nếu không có phản hồi." | 3s | Nếu có cảm biến gia tốc |
| `CRITICAL_VITALS_ALERT` | Chỉ số nguy hiểm | "Cảnh báo: Chỉ số sức khỏe ở mức nguy hiểm. Vui lòng liên hệ y tế ngay." | 5s | Khi nhiều chỉ số vượt ngưỡng |
| `EMERGENCY_CANCELLED` | Hủy khẩn cấp | "Đã hủy cảnh báo khẩn cấp." | 5s | User xác nhận an toàn |

### 9. CẢNH BÁO CHỈ SỐ CỤ THỂ (8 scenarios mới)

| ID | Tình huống | Nội dung TTS đề xuất | Cooldown | Lý do |
|---|---|---|---|---|
| `HR_TOO_LOW` | Nhịp tim quá thấp | "Cảnh báo: Nhịp tim quá thấp, {bpm} nhịp mỗi phút. Hãy nghỉ ngơi và theo dõi." | 10s | Bradycardia (<50 bpm) |
| `HR_TOO_HIGH` | Nhịp tim quá cao | "Cảnh báo: Nhịp tim quá cao, {bpm} nhịp mỗi phút. Hãy ngồi xuống và thở sâu." | 10s | Tachycardia (>100 bpm) |
| `SPO2_LOW` | SpO₂ thấp | "Cảnh báo: Nồng độ oxy trong máu thấp, {spo2} phần trăm. Hãy thở sâu và kiểm tra lại." | 10s | Hypoxia (<90%) |
| `SPO2_CRITICAL` | SpO₂ nguy hiểm | "Nguy hiểm: Oxy máu rất thấp, {spo2} phần trăm. Cần hỗ trợ y tế khẩn cấp." | 5s | Severe hypoxia (<85%) |
| `BP_HYPERTENSION` | Huyết áp cao | "Cảnh báo: Huyết áp cao, {sys} trên {dia}. Hãy nghỉ ngơi và uống thuốc nếu có chỉ định." | 10s | Stage 2 HTN (≥140/90) |
| `BP_HYPOTENSION` | Huyết áp thấp | "Cảnh báo: Huyết áp thấp, {sys} trên {dia}. Hãy nằm xuống và nâng chân lên." | 10s | Hypotension (<90/60) |
| `BP_HYPERTENSIVE_CRISIS` | Cơn tăng huyết áp | "Nguy hiểm: Huyết áp rất cao, {sys} trên {dia}. Cần đến bệnh viện ngay." | 5s | Crisis (≥180/120) |
| `IRREGULAR_HEARTBEAT` | Nhịp tim không đều | "Phát hiện nhịp tim không đều. Hãy đo lại và liên hệ bác sĩ nếu tình trạng kéo dài." | 15s | Arrhythmia detected |

### 10. HƯỚNG DẪN SỬ DỤNG (6 scenarios mới)

| ID | Tình huống | Nội dung TTS đề xuất | Cooldown | Lý do |
|---|---|---|---|---|
| `FIRST_TIME_SETUP` | Lần đầu sử dụng | "Chào mừng đến với IoT Health. Hãy làm theo hướng dẫn trên màn hình để thiết lập." | 0s | Onboarding |
| `SENSOR_PLACEMENT_GUIDE` | Hướng dẫn đặt cảm biến | "Để đo chính xác, hãy đặt cảm biến {sensor} đúng vị trí như hình minh họa." | 10s | Tutorial mode |
| `MEASUREMENT_TIPS` | Mẹo đo lường | "Để kết quả chính xác, hãy ngồi yên, thư giãn và không nói chuyện trong khi đo." | 20s | Before measurement |
| `DEVICE_READY` | Thiết bị sẵn sàng | "Thiết bị đã sẵn sàng. Chạm vào nút đo để bắt đầu." | 5s | After sensor init |
| `CALIBRATION_NEEDED` | Cần hiệu chuẩn | "Cảm biến cần hiệu chuẩn. Vui lòng liên hệ nhân viên kỹ thuật." | 30s | Sensor drift |
| `MAINTENANCE_REMINDER` | Nhắc bảo trì | "Đã đến lịch bảo trì định kỳ. Vui lòng vệ sinh cảm biến và kiểm tra kết nối." | 60s | Monthly reminder |

### 11. PIN & NGUỒN ĐIỆN (4 scenarios mới)

| ID | Tình huống | Nội dung TTS đề xuất | Cooldown | Lý do |
|---|---|---|---|---|
| `BATTERY_LOW` | Pin yếu | "Cảnh báo: Pin còn {percent} phần trăm. Vui lòng sạc thiết bị." | 30s | <20% battery |
| `BATTERY_CRITICAL` | Pin sắp hết | "Pin sắp hết, còn {percent} phần trăm. Hãy sạc ngay để tránh mất dữ liệu." | 10s | <10% battery |
| `CHARGING_STARTED` | Bắt đầu sạc | "Đã kết nối nguồn điện, đang sạc pin." | 15s | Charging detected |
| `POWER_OUTAGE` | Mất điện | "Mất nguồn điện chính, đang chuyển sang pin dự phòng." | 5s | Power failure |

### 12. KẾT QUẢ & BÁO CÁO (3 scenarios mới)

| ID | Tình huống | Nội dung TTS đề xuất | Cooldown | Lý do |
|---|---|---|---|---|
| `MEASUREMENT_COMPLETE` | Hoàn thành đo | "Đo xong. Kết quả đã được lưu vào lịch sử." | 3s | After any measurement |
| `DAILY_SUMMARY` | Tóm tắt ngày | "Hôm nay bạn đã đo {count} lần. Các chỉ số trung bình trong giới hạn bình thường." | 0s | End of day |
| `TREND_IMPROVING` | Xu hướng tốt | "Chúc mừng! Các chỉ số sức khỏe của bạn đang cải thiện trong tuần qua." | 0s | Weekly analysis |

### 13. KẾT NỐI THIẾT BỊ (3 scenarios mới)

| ID | Tình huống | Nội dung TTS đề xuất | Cooldown | Lý do |
|---|---|---|---|---|
| `BLUETOOTH_CONNECTED` | Kết nối Bluetooth | "Đã kết nối với thiết bị {device_name}." | 10s | Nếu có BT |
| `BLUETOOTH_DISCONNECTED` | Mất kết nối Bluetooth | "Mất kết nối với {device_name}." | 10s | BT lost |
| `QR_PAIRING_SUCCESS` | Ghép nối thành công | "Đã ghép nối với ứng dụng di động thành công." | 5s | QR code scan |

---

## 📊 THỐNG KÊ TỔNG HỢP

| Nhóm | Hiện có | Đề xuất | Tổng |
|---|---|---|---|
| Hệ thống | 4 | 0 | 4 |
| Mạng & Đồng bộ | 5 | 0 | 5 |
| Nhịp tim & SpO₂ | 5 | 2 | 7 |
| Nhiệt độ | 9 | 0 | 9 |
| Huyết áp | 5 | 3 | 8 |
| Lỗi & Bảo trì | 2 | 1 | 3 |
| Điều hướng | 5 | 0 | 5 |
| **Khẩn cấp & An toàn** | 0 | **6** | **6** ⭐ |
| **Cảnh báo chỉ số** | 0 | **8** | **8** |
| **Hướng dẫn sử dụng** | 0 | **6** | **6** |
| **Pin & Nguồn** | 0 | **4** | **4** |
| **Kết quả & Báo cáo** | 0 | **3** | **3** |
| **Kết nối thiết bị** | 0 | **3** | **3** |
| **TỔNG** | **30** | **33** | **63** |

---

## 🎯 ƯU TIÊN TRIỂN KHAI

### Phase 1: KHẨN CẤP (Cao nhất) ⭐⭐⭐
1. `EMERGENCY_BUTTON_PRESSED` - **YÊU CẦU CỦA USER**
2. `EMERGENCY_CALL_INITIATED`
3. `EMERGENCY_CONTACT_NOTIFIED`
4. `CRITICAL_VITALS_ALERT`
5. `EMERGENCY_CANCELLED`

### Phase 2: CẢNH BÁO CHỈ SỐ (Cao) ⭐⭐
6. `HR_TOO_LOW` / `HR_TOO_HIGH`
7. `SPO2_LOW` / `SPO2_CRITICAL`
8. `BP_HYPERTENSION` / `BP_HYPOTENSION` / `BP_HYPERTENSIVE_CRISIS`
9. `IRREGULAR_HEARTBEAT`

### Phase 3: HƯỚNG DẪN & PIN (Trung bình) ⭐
10. `BATTERY_LOW` / `BATTERY_CRITICAL`
11. `DEVICE_READY`
12. `MEASUREMENT_COMPLETE`
13. `SENSOR_PLACEMENT_GUIDE`

### Phase 4: BỔ SUNG (Thấp)
14. Các scenarios còn lại

---

## 💡 GỢI Ý TRIỂN KHAI

### 1. Thêm ScenarioID mới vào enum
```python
class ScenarioID(str, Enum):
    # ... existing scenarios ...
    
    # Emergency & Safety
    EMERGENCY_BUTTON_PRESSED = "emergency_button_pressed"
    EMERGENCY_CALL_INITIATED = "emergency_call_initiated"
    EMERGENCY_CONTACT_NOTIFIED = "emergency_contact_notified"
    FALL_DETECTED = "fall_detected"
    CRITICAL_VITALS_ALERT = "critical_vitals_alert"
    EMERGENCY_CANCELLED = "emergency_cancelled"
    
    # Vital Signs Alerts
    HR_TOO_LOW = "hr_too_low"
    HR_TOO_HIGH = "hr_too_high"
    SPO2_LOW = "spo2_low"
    SPO2_CRITICAL = "spo2_critical"
    # ... etc
```

### 2. Thêm templates vào SCENARIO_LIBRARY
```python
SCENARIO_LIBRARY: Dict[ScenarioID, ScenarioTemplate] = {
    # ... existing templates ...
    
    ScenarioID.EMERGENCY_BUTTON_PRESSED: ScenarioTemplate(
        template_vi="Đã kích hoạt cảnh báo khẩn cấp. Đang gửi thông báo đến người thân và trung tâm y tế.",
        cooldown_seconds=3.0,
    ),
    # ... etc
}
```

### 3. Tích hợp vào GUI
```python
# Trong emergency button handler
def on_emergency_button_press(self):
    self._speak_scenario(ScenarioID.EMERGENCY_BUTTON_PRESSED)
    # Send notifications...
```

### 4. Tích hợp vào Alert System
```python
# Trong alert_system.py
def check_critical_vitals(self, vitals):
    if vitals.hr < 50:
        self.tts_manager.speak_scenario(
            ScenarioID.HR_TOO_LOW,
            bpm=vitals.hr
        )
```

---

## 📝 GHI CHÚ

1. **Cooldown**: Thời gian chờ giữa các lần phát cùng một scenario để tránh spam
2. **Required fields**: Các tham số bắt buộc (ví dụ: `{bpm}`, `{temp}`)
3. **Formatters**: Hàm format số (int, decimal) để đọc tự nhiên
4. **Priority**: Scenarios khẩn cấp có priority cao hơn trong queue

---

## ❓ CÂU HỎI BỔ SUNG

Bạn có muốn:
1. ✅ Triển khai Phase 1 (Khẩn cấp) ngay?
2. Thêm scenarios nào khác không có trong danh sách?
3. Điều chỉnh nội dung TTS của scenarios nào?
4. Thay đổi cooldown time?
5. Thêm tiếng Anh cho các scenarios mới?
