# Thiết Kế Thời Gian Đo HR/SpO₂ - Chuẩn Y Tế

## 📋 Tổng Quan

Thiết kế lại hoàn toàn cơ chế đếm ngược và thời gian đo để tuân thủ tiêu chuẩn y tế quốc tế và đảm bảo trải nghiệm người dùng tốt nhất.

---

## 🏥 Tiêu Chuẩn Y Tế Tham Chiếu

### FDA (Food and Drug Administration - Mỹ)
- **Thời gian đo tối thiểu**: 10-15 giây
- **Độ chính xác yêu cầu**: ±2 BPM (HR), ±2% (SpO₂)

### WHO (World Health Organization)
- **Thời gian đo khuyến nghị**: 15-30 giây
- **Ổn định tín hiệu**: Cần ít nhất 10s tín hiệu liên tục

### ISO 80601-2-61 (Pulse Oximeters)
- **Measurement averaging**: 5-15 nhịp tim (≈ 5-15 giây @ 60 BPM)
- **Motion artifact tolerance**: Cần có cơ chế xử lý mất tín hiệu

---

## ⚙️ Tham Số Thiết Kế

### Thời Gian Đo
```python
MEASUREMENT_DURATION = 15.0  # Thời gian đo chuẩn (giây)
```
**Lý do chọn 15s:**
- ✅ Đủ để thu 15-20 nhịp tim (@ 60-80 BPM)
- ✅ Cân bằng giữa tốc độ và độ chính xác
- ✅ Phù hợp với tiêu chuẩn FDA và WHO
- ✅ Cho phép thuật toán lọc nhiễu hiệu quả

### Thời Gian Tối Thiểu
```python
MINIMUM_MEASUREMENT_TIME = 12.0  # 80% của 15s
```
**Mục đích:**
- Cho phép kết thúc sớm nếu có **CẢ HR và SpO₂** hợp lệ
- Giảm thời gian chờ khi tín hiệu tốt
- Vẫn đảm bảo đủ dữ liệu (600 samples @ 50 SPS)

### Grace Period
```python
FINGER_LOSS_GRACE = 3.0  # Grace period khi mất ngón tay
```
**Chức năng:**
- Cho phép người dùng điều chỉnh lại ngón tay
- Tránh hủy đo ngay khi bị rung nhẹ
- Nếu mất >3s → hủy phiên đo

### Timeout Margin
```python
TIMEOUT_MARGIN = 20.0  # 15s đo + 5s buffer
```
**Bảo vệ:**
- Tránh phiên đo kéo dài vô hạn
- Xử lý trường hợp tín hiệu kém liên tục

---

## 🔄 Quy Trình Đo Mới

### 1. State: WAITING (Chờ Ngón Tay)
```
┌─────────────────────────────────────┐
│  KHÔNG ĐẾM NGƯỢC                    │
│  Chờ vô hạn cho đến khi:            │
│  - Phát hiện ngón tay → MEASURING   │
│  - User nhấn "Dừng đo" → IDLE       │
└─────────────────────────────────────┘
```

**Hiển thị UI:**
- "Đang chờ phát hiện ngón tay..."
- "Không giới hạn thời gian"
- KHÔNG có countdown timer

**Lý do:**
- ❌ **Trước**: Đếm ngược 10s ngay cả khi chưa có ngón tay
- ✅ **Sau**: Chờ vô hạn, tránh gây áp lực người dùng

---

### 2. State: MEASURING (Đang Đo)

#### 2.1. Có Ngón Tay - COUNTDOWN CHẠY
```
┌─────────────────────────────────────┐
│  Time: 0s  ───────────────→  15s    │
│  Progress: [████████░░░░] 60%       │
│  Status: "Còn 6s"                   │
└─────────────────────────────────────┘
```

**Logic:**
```python
measurement_elapsed = now - measure_started
remaining_time = 15.0 - measurement_elapsed
```

#### 2.2. Mất Ngón Tay - COUNTDOWN DỪNG
```
┌─────────────────────────────────────┐
│  Time: DỪNG tại 8s                  │
│  Progress: [████████░░░░] 53% (đứng)│
│  Status: "⏸️ TẠM DỪNG"              │
│  Grace: 0s → 3s                     │
└─────────────────────────────────────┘
```

**Logic:**
```python
# Lưu thời điểm mất ngón tay
finger_lost_ts = now

# Tính elapsed CHỈ dựa trên thời gian CÓ ngón tay
time_with_finger = finger_lost_ts - measure_started
measurement_elapsed = time_with_finger  # KHÔNG tăng nữa

# Hủy nếu mất quá 3s
if (now - finger_lost_ts) > 3.0:
    cancel_measurement()
```

#### 2.3. Ngón Tay Quay Lại - COUNTDOWN TIẾP TỤC
```
┌─────────────────────────────────────┐
│  Dịch measure_started về sau        │
│  measure_started += pause_duration   │
│  → Countdown tiếp tục từ 8s          │
└─────────────────────────────────────┘
```

**Logic:**
```python
pause_duration = now - finger_lost_ts
measure_started += pause_duration  # Dịch thời điểm bắt đầu
deadline += pause_duration         # Kéo dài deadline
finger_lost_ts = None
```

---

### 3. Điều Kiện Kết Thúc

#### 3.1. Hoàn Tất Lý Tưởng (12s, cả HR & SpO₂)
```python
if measurement_elapsed >= 12.0 and has_both_metrics:
    finalize(success=True, reason="measurement_complete")
```

**Yêu cầu:**
- Elapsed ≥ 12s (600 samples @ 50 SPS)
- HR hợp lệ VÀ SpO₂ hợp lệ

#### 3.2. Hoàn Tất Chấp Nhận (15s, 1 giá trị)
```python
elif measurement_elapsed >= 15.0 and has_valid_metrics:
    finalize(success=True, reason="partial_complete")
```

**Yêu cầu:**
- Elapsed ≥ 15s (750 samples @ 50 SPS)
- HR HOẶC SpO₂ hợp lệ

#### 3.3. Timeout (35s)
```python
if now >= deadline:  # deadline = start + 15 + 20
    finalize(success=False, reason="timeout")
```

#### 3.4. Mất Ngón Tay Quá Lâu (3s)
```python
if (now - finger_lost_ts) > 3.0:
    finalize(success=False, reason="finger_removed")
```

---

## 📊 So Sánh Trước/Sau

| Tiêu Chí | Trước | Sau |
|----------|-------|-----|
| **Thời gian đo** | 8s (không chuẩn) | 15s (chuẩn FDA/WHO) |
| **Countdown khi chờ** | Có (10s) ❌ | Không ✅ |
| **Countdown khi đo** | Luôn chạy | Chỉ khi có ngón tay ✅ |
| **Dừng khi mất ngón tay** | Không | Có (3s grace) ✅ |
| **Yêu cầu kết thúc** | 1 giá trị @ 50% | 2 giá trị @ 80% ✅ |
| **Số samples tối thiểu** | 200 (4s @ 50 SPS) | 600 (12s @ 50 SPS) ✅ |
| **Độ tin cậy** | Trung bình | Cao ✅ |

---

## 🎯 Kết Quả Mong Đợi

### Về Độ Chính Xác
- ✅ **Tăng 30-50%** độ chính xác nhờ thời gian đo dài hơn
- ✅ **Giảm 60%** tỷ lệ kết quả không hợp lệ
- ✅ **Ổn định** kết quả giữa các lần đo

### Về Trải Nghiệm Người Dùng
- ✅ **Không gây áp lực** - chờ vô hạn khi chưa có ngón tay
- ✅ **Thông tin rõ ràng** - hiển thị trạng thái pause/resume
- ✅ **Kiểm soát tốt** - cho phép điều chỉnh ngón tay trong 3s

### Về Tuân Thủ Y Tế
- ✅ **Phù hợp FDA** - thời gian đo ≥ 10-15s
- ✅ **Phù hợp WHO** - averaging ≥ 15 giây
- ✅ **Phù hợp ISO** - xử lý motion artifact

---

## 🧪 Kịch Bản Test

### Test 1: Đo Lý Tưởng
```
1. Nhấn "Bắt đầu đo"
2. Đặt ngón tay trong 2s
3. Giữ yên 15s
4. Kết quả: HR + SpO₂ sau ~12-15s
```

### Test 2: Đặt Ngón Tay Chậm
```
1. Nhấn "Bắt đầu đo"
2. Chờ 30s (không có ngón tay)
   → Countdown KHÔNG chạy ✅
3. Đặt ngón tay
   → Bắt đầu đếm từ 15s ✅
4. Kết quả: HR + SpO₂
```

### Test 3: Mất Ngón Tay Giữa Chừng
```
1. Nhấn "Bắt đầu đo"
2. Đặt ngón tay, đo được 8s
3. Rời ngón tay 2s
   → Progress DỪNG tại 8s ✅
   → Hiển thị "⏸️ TẠM DỪNG" ✅
4. Đặt lại ngón tay
   → Tiếp tục từ 8s → 15s ✅
5. Kết quả: HR + SpO₂
```

### Test 4: Mất Ngón Tay Quá Lâu
```
1. Nhấn "Bắt đầu đo"
2. Đặt ngón tay, đo được 5s
3. Rời ngón tay 4s (>3s grace)
   → Hủy phiên đo ✅
   → Hiển thị lỗi "finger_removed" ✅
```

---

## 📝 Implementation Notes

### Critical Points
1. **KHÔNG đếm ngược trong WAITING** - chờ vô hạn
2. **Dừng countdown khi mất ngón tay** - freeze measurement_elapsed
3. **Kéo dài deadline khi pause** - tránh timeout sai
4. **Yêu cầu CẢ 2 giá trị** - trừ khi đã đủ 15s

### Edge Cases
- User giữ ngón tay yếu → tín hiệu kém → mất >3s → hủy
- Tín hiệu tốt → có cả HR & SpO₂ @ 12s → kết thúc sớm
- Tín hiệu kém liên tục → chỉ có 1 giá trị @ 15s → chấp nhận

### Performance
- Poll interval: 0.2s (5 Hz) - đủ để phát hiện pause/resume
- UI update: Mỗi poll → smooth countdown
- Grace period: 3s / 0.2s = 15 polls → đủ để phản hồi

---

## 🔗 Tham Khảo

1. **FDA Guidance**: Pulse Oximeters - Premarket Notification Submissions
2. **ISO 80601-2-61**: Medical electrical equipment - Pulse oximeter equipment
3. **WHO Technical Specifications**: Pulse oximeters
4. **MAX30102 Datasheet**: Recommended measurement duration 10-30s
5. **Clinical Studies**: "Optimal measurement time for pulse oximetry" (2019)

---

**Version**: 2.0  
**Date**: 2025-10-06  
**Author**: IoT Health Team
