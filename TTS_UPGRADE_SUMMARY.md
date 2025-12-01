# TTS System Upgrade - Implementation Summary

**Ngày**: December 2, 2025  
**Status**: ✅ Core Implementation Complete (5/8 tasks done)

---

## ✅ ĐÃ HOÀN THÀNH

### 1. **ScenarioID Enum - 26 scenarios mới** ✅
**File**: `src/utils/tts_manager.py`

**Scenarios mới**:
- **Emergency & Safety** (5): `EMERGENCY_BUTTON_PRESSED`, `EMERGENCY_CALL_INITIATED`, `EMERGENCY_CONTACT_NOTIFIED`, `CRITICAL_VITALS_ALERT`, `EMERGENCY_CANCELLED`
- **Vital Signs Alerts** (8): `HR_TOO_LOW`, `HR_TOO_HIGH`, `SPO2_LOW`, `SPO2_CRITICAL`, `BP_HYPERTENSION`, `BP_HYPOTENSION`, `BP_HYPERTENSIVE_CRISIS`, `IRREGULAR_HEARTBEAT`
- **User Guidance** (6): `FIRST_TIME_SETUP`, `SENSOR_PLACEMENT_GUIDE`, `MEASUREMENT_TIPS`, `DEVICE_READY`, `CALIBRATION_NEEDED`, `MAINTENANCE_REMINDER`
- **Results & Reports** (3): `MEASUREMENT_COMPLETE`, `DAILY_SUMMARY`, `TREND_IMPROVING`
- **Device Connection** (1): `QR_PAIRING_SUCCESS`

**Tổng**: 30 cũ + 23 mới = **53 scenarios**

---

### 2. **SCENARIO_LIBRARY Templates** ✅
**File**: `src/utils/tts_manager.py`

Thêm 23 templates mới với:
- Vietnamese `template_vi` (primary)
- English `template_en` (optional)
- `required_fields` (e.g., `bpm`, `spo2`, `sys`, `dia`)
- `formatters` (`_format_int`, `_format_decimal`)
- `cooldown_seconds` (3s-60s tùy mức độ quan trọng)

---

### 3. **EmergencyButton Component** ✅
**File**: `src/gui/emergency_button.py` (MỚI)

**Features**:
- Nút đỏ lớn (80dp × 80dp) với glow effect
- Icon: `alert-octagon` (48sp)
- Countdown 5 giây để hủy
- Actions khi nhấn:
  - ✅ TTS: `EMERGENCY_BUTTON_PRESSED` → `EMERGENCY_CALL_INITIATED`
  - ✅ MQTT alert (QoS 2 - exactly once)
  - ✅ Popup xác nhận với buttons "HỦY" / "XÁC NHẬN NGAY"
  - ✅ Database logging
  - ✅ Callback to app

**Flow**:
```
User nhấn → TTS cảnh báo → Popup countdown (5s) 
          → [Cancel] hoặc [Confirm] 
          → TTS "Đang kết nối..." → MQTT alert → "Đã gửi" dialog
```

---

### 4. **Dashboard Integration** ✅
**File**: `src/gui/dashboard_screen.py`

**Changes**:
- Thay thế `MDRectangleFlatIconButton` emergency cũ → `EmergencyButton` component
- Thêm `_on_emergency_confirmed()` callback để log to database
- Emergency button nằm trong `button_row` (bên phải nút "Lịch sử")

---

### 5. **AlertSystem Full Implementation** ✅
**File**: `src/ai/alert_system.py`

**Thay thế toàn bộ stub code** bằng implementation thực:

#### **Core Methods**:
- `check_vital_signs()`: Main entry point, calls specialized checkers
- `_check_heart_rate()`: HR < 50 (Bradycardia) hoặc > 100 (Tachycardia) → TTS alert
- `_check_spo2()`: SpO2 < 85% (Critical) hoặc < 90% (Low) → TTS alert
- `_check_blood_pressure()`: 
  - SYS ≥ 180 or DIA ≥ 120 → **Crisis** → `BP_HYPERTENSIVE_CRISIS`
  - SYS ≥ 140 or DIA ≥ 90 → **Stage 2** → `BP_HYPERTENSION`
  - SYS < 90 or DIA < 60 → **Hypotension** → `BP_HYPOTENSION`
- `_trigger_alert_with_tts()`: Unified alert với TTS + MQTT + Database + Callbacks
- `_check_cooldown()`: 10 phút cooldown để tránh spam alerts

#### **Automatic TTS Flow**:
```python
# Ví dụ: HR = 120 bpm
check_vital_signs({'heart_rate': 120})
  → _check_heart_rate(120)
    → HR > 100 detected
    → Check cooldown (ok)
    → _trigger_alert_with_tts(
        tts_scenario=ScenarioID.HR_TOO_HIGH,
        tts_params={'bpm': 120}
      )
      → TTS speaks: "Cảnh báo: Nhịp tim quá cao, 120 nhịp mỗi phút..."
      → MQTT alert sent
      → Database logged
      → UI callbacks triggered
    → Set cooldown (10 min)
```

---

## 🔄 ĐANG LÀM (In Progress)

### 6. **GPIO Physical Emergency Button Handler** 🔄
**File**: `main_app.py` (cần update)

**TODO**:
```python
import RPi.GPIO as GPIO

# Config
EMERGENCY_BUTTON_GPIO = 23  # Bạn chọn GPIO nào?

def setup_emergency_gpio(self):
    """Setup GPIO interrupt for physical emergency button"""
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(EMERGENCY_BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.add_event_detect(
        EMERGENCY_BUTTON_GPIO,
        GPIO.FALLING,  # Nhấn nút = LOW
        callback=self._on_physical_emergency_pressed,
        bouncetime=300  # Debounce 300ms
    )

def _on_physical_emergency_pressed(self, channel):
    """GPIO callback - trigger emergency button"""
    self.logger.critical("🚨 Physical emergency button pressed!")
    # Trigger same logic as GUI button
    if hasattr(self, 'emergency_button'):
        self.emergency_button._on_emergency_pressed(None)
```

**Câu hỏi cho bạn**:
1. Bạn muốn dùng **GPIO nào** cho nút khẩn cấp vật lý? (e.g., GPIO 23, 24, 25...)
2. Nút nhấn **pull-up** hay **pull-down**?
3. Có cần **LED indicator** khi nhấn không? (GPIO khác)

---

## ⏳ CHƯA LÀM (Pending)

### 7. **MEASUREMENT_COMPLETE TTS** ⏳
**Files cần update**:
- `src/gui/heart_rate_screen.py`
- `src/gui/temperature_screen.py`
- `src/gui/bp_measurement_screen.py`

**Change cần làm**:
```python
# Trong _save_measurement() của mỗi screen
def _save_measurement(self):
    # ... existing save logic ...
    
    # NEW: TTS notification
    self._speak_scenario(ScenarioID.MEASUREMENT_COMPLETE)
    
    # Update UI
    self.info_label.text = "✅ Đo xong. Kết quả đã lưu."
```

**Quick implementation** (3 files):
1. Tìm `_save_measurement()` method
2. Thêm `self._speak_scenario(ScenarioID.MEASUREMENT_COMPLETE)` SAU khi save thành công
3. Test

---

### 8. **Testing & Verification** ⏳
**Checklist**:
- [ ] Test emergency button (GUI) → Countdown → TTS → MQTT
- [ ] Test emergency button (GPIO vật lý) → Same flow
- [ ] Test HR alerts: HR < 50 → TTS "Nhịp tim quá thấp..."
- [ ] Test SpO2 alerts: SpO2 < 90 → TTS "Oxy máu thấp..."
- [ ] Test BP alerts: SYS ≥ 140 → TTS "Huyết áp cao..."
- [ ] Test cooldown: Alert 2 lần liên tiếp → Only 1 TTS (10 min cooldown)
- [ ] Test MEASUREMENT_COMPLETE TTS sau save
- [ ] Pre-generate all TTS audio (export_tts_assets.py)

---

## 🚀 HƯỚNG DẪN CHẠY PRE-GENERATE TTS AUDIO

### **Tại sao cần pre-generate?**
- Lần đầu TTS speak → phải generate audio → **delay 1-2 giây** → trải nghiệm không tốt
- Pre-generate → audio files sẵn → speak ngay lập tức → smooth

### **Cách chạy**:

#### **Option 1: Default output (asset/tts/)**
```bash
cd /home/pi/Desktop/IoT_health
python src/utils/export_tts_assets.py
```

#### **Option 2: Custom output directory**
```bash
python src/utils/export_tts_assets.py --output /home/pi/custom_tts_assets
```

#### **Option 3: Override locale/volume**
```bash
# Vietnamese với volume 120%
python src/utils/export_tts_assets.py --locale vi --volume 120

# English với volume 100%
python src/utils/export_tts_assets.py --locale en --volume 100
```

### **Kết quả mong đợi**:
```
2025-12-02 10:30:15 - INFO - Exporting TTS assets to /home/pi/Desktop/IoT_health/asset/tts
2025-12-02 10:30:16 - INFO - Preloading 30 static scenarios
2025-12-02 10:30:45 - INFO - Generated 30 audio files
```

### **Verify**:
```bash
ls -lh asset/tts/*.wav | wc -l
# Should show ~30 files (static scenarios without parameters)
```

**Note**: Scenarios có parameters (e.g., `HR_RESULT` với `{bpm}`, `{spo2}`) sẽ generate runtime khi cần.

---

## 📊 STATISTICS

| Category | Count | Status |
|---|---|---|
| **Total Scenarios** | 53 | ✅ (30 old + 23 new) |
| **Static Scenarios** | ~30 | ✅ Can pre-generate |
| **Dynamic Scenarios** | ~23 | Runtime generation |
| **New TTS Templates** | 23 | ✅ Complete |
| **GUI Components** | 1 | ✅ EmergencyButton |
| **Alert System** | 1 | ✅ Full implementation |
| **GPIO Handler** | 0 | ⏳ Needs GPIO pin config |
| **Measurement TTS** | 0/3 | ⏳ Needs 3 file updates |

---

## 🎯 NEXT STEPS (Để bạn quyết định)

### **Option A: Test ngay những gì đã có** (Recommended)
1. ✅ Chạy `export_tts_assets.py` để generate audio
2. ✅ Test emergency button (GUI only)
3. ✅ Test alert system với data giả:
   ```python
   alert_system.check_vital_signs('patient_001', {
       'heart_rate': 120,  # Should trigger HR_TOO_HIGH
       'spo2': 88,         # Should trigger SPO2_LOW
   })
   ```
4. ✅ Verify TTS plays without delay

### **Option B: Hoàn thành tất cả trước khi test**
1. Cho tôi biết GPIO pin cho emergency button
2. Tôi implement GPIO handler
3. Tôi thêm MEASUREMENT_COMPLETE vào 3 screens
4. Chạy full testing

### **Option C: Bạn tự làm phần còn lại**
Tôi đã cung cấp đầy đủ:
- ✅ Core TTS system (53 scenarios)
- ✅ EmergencyButton component (reusable)
- ✅ AlertSystem với auto TTS
- 📝 Clear instructions cho GPIO handler
- 📝 Clear instructions cho MEASUREMENT_COMPLETE

Bạn có thể:
- Copy GPIO code mẫu vào `main_app.py`
- Add 1 dòng TTS vào 3 save methods

---

## ❓ CÂU HỎI DÀNH CHO BẠN

1. **GPIO Emergency Button**:
   - Bạn có nút vật lý chưa? Đấu vào GPIO nào?
   - Pull-up hay pull-down?
   - Cần LED indicator không?

2. **Testing Priority**:
   - Test option A (ngay) hay B (đầy đủ)?

3. **Audio Export**:
   - Chạy `export_tts_assets.py` ngay bây giờ?
   - Volume mặc định (100) hay tăng lên?

4. **Deployment**:
   - Triển khai ngay hay cần thêm features nào?

---

## 📞 CONTACT

Cho tôi biết:
- ✅ Chạy `export_tts_assets.py` → OK
- ✅ GPIO pin number (nếu có)
- ✅ Muốn test option nào (A/B/C)

Tôi sẽ hoàn thành phần còn lại! 🚀
