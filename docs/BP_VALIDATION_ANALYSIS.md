# Phân tích và Điều chỉnh Ngưỡng Validation Huyết Áp

## 📊 Vấn đề hiện tại

```
[WARNING] Chênh lệch huyết áp quá cao: 152.51 mmHg (tâm thu - tâm trương > 100)
```

**Pulse Pressure (PP) = Systolic - Diastolic = 152.51 mmHg** là bất thường.

---

## 📋 Thông số Y tế - Các Ngưỡng Huyết Áp

### 1. **Pulse Pressure (Chênh lệch huyết áp)**

| Phân loại | PP (mmHg) | Diễn giải |
|-----------|----------|----------|
| **Bình thường** | 30-50 | Lành mạnh, độ đàn hồi động mạch tốt |
| **Tăng cao** | 50-60 | Có thể chỉ độ cứng động mạch tăng |
| **Cao** | > 60 | Nguy cơ tim mạch cao |
| **Bệnh lý** | > 100 | Rất bất thường, cần kiểm tra |

**Ghi chú:** Người cao tuổi PP có thể cao hơn (40-70 mmHg là bình thường cho tuổi >60)

### 2. **Systolic Blood Pressure (SBP - Huyết áp tâm thu)**

| Phân loại | SBP (mmHg) | Ghi chú |
|-----------|-----------|--------|
| Huyết áp thấp | < 90 | Hypotension |
| Bình thường | 90-119 | Healthy |
| Tăng cao | 120-129 | Elevated (+ DIA < 80) |
| Giai đoạn 1 | 130-139 | Hypertension stage 1 |
| Giai đoạn 2 | ≥ 140 | Hypertension stage 2 |

### 3. **Diastolic Blood Pressure (DBP - Huyết áp tâm trương)**

| Phân loại | DBP (mmHg) | Ghi chú |
|-----------|-----------|--------|
| Huyết áp thấp | < 60 | Hypotension |
| Bình thường | 60-79 | Healthy |
| Giai đoạn 1 | 80-89 | Hypertension stage 1 |
| Giai đoạn 2 | ≥ 90 | Hypertension stage 2 |

### 4. **Mean Arterial Pressure (MAP - Huyết áp trung bình)**

```
MAP = DBP + (SBP - DBP) / 3
   = (SBP + 2×DBP) / 3
```

| MAP (mmHg) | Tình trạng |
|-----------|-----------|
| < 60 | Hypotension (nguy hiểm) |
| 60-100 | Bình thường |
| > 100 | Hypertension |

---

## 🔍 Phân tích PP = 152.51 mmHg

### Khả năng nguyên nhân:

1. **Lỗi Calibration HX710B** (KHẢ NĂNG CAO)
   - Offset/slope sai lệch
   - Dữ liệu được chuyển đổi không chính xác từ counts → mmHg
   - **Giải pháp**: Kiểm tra file config `app_config.yaml`:
     ```yaml
     sensors:
       hx710b:
         calibration:
           offset_counts: 0
           slope_mmhg_per_count: 0.001
     ```

2. **Dữ liệu nhiễu từ sensor** (KHẢ NĂNG CAO)
   - Sensor HX710B chưa được scale đúng
   - Áp cuff không đặt đúng
   - Cuff quá lỏng/quá chặt

3. **Ngưỡng validation quá chặt** (KHẢ NĂNG TRUNG)
   - Ngưỡng PP > 100 mmHg không phù hợp với phần cứng
   - Cần điều chỉnh dựa trên dữ liệu thực tế

---

## ✅ Giải pháp điều chỉnh

### Bước 1: Kiểm tra Calibration (Ưu tiên 1)

**File**: `/home/pi/Desktop/IoT_health/config/app_config.yaml`

```yaml
sensors:
  hx710b:
    enabled: true
    gpio_dout: 6
    gpio_sck: 5
    sps_hint: 50
    calibration:
      offset_counts: 0          # ← Kiểm tra giá trị này
      slope_mmhg_per_count: 0.001  # ← Và giá trị này
    timeout_ms: 1000
```

**Kiểm tra:**
```bash
cd /home/pi/Desktop/IoT_health
python tests/calibrate_offset.py  # Nếu có sẵn
```

### Bước 2: Điều chỉnh Ngưỡng Validation

**File**: `/home/pi/Desktop/IoT_health/src/utils/health_validators.py`

**Hiện tại (dòng 144-152):**
```python
# Pulse pressure check (normal range: 30-50 mmHg)
pulse_pressure = systolic - diastolic
if pulse_pressure < 20:
    errors.append(...)
elif pulse_pressure > 100:  # ← NGƯỠNG HIỆN TẠI: 100 mmHg
    errors.append(...)
```

**Đề xuất điều chỉnh:**

| Scenario | Ngưỡng PP | Lý do |
|----------|----------|------|
| **Bảo thủ (chặt)** | > 100 | Phát hiện lỗi calibration |
| **Trung bình** | > 120 | Cho phép sai số sensor 20% |
| **Chill (lỏng)** | > 150 | Cho phép sai số sensor 50% |

**Khuyến nghị**: Đặt ngưỡng tạm thời **> 120 mmHg** để thu thập dữ liệu, sau đó điều chỉnh dựa trên xu hướng thực tế.

### Bước 3: Thêm Cảnh báo thay vì Lỗi

Thay vì từ chối toàn bộ kết quả, có thể:
- ✅ **Lưu dữ liệu** nhưng đánh dấu `data_quality = "warning"`
- ⚠️ **Hiển thị cảnh báo** trên UI: "Kết quả có thể không chính xác"
- 📊 **Ghi log** để phân tích sau

---

## 📈 Dữ liệu Y tế Tham khảo

### Tuổi và PP (Người khỏe mạnh):

| Tuổi | PP bình thường (mmHg) | Ghi chú |
|-----|----------------------|---------|
| 20-30 | 30-45 | Động mạch rất đàn hồi |
| 30-40 | 35-50 | Độ đàn hồi tốt |
| 40-50 | 40-55 | Bắt đầu cứng động mạch |
| 50-60 | 45-65 | Độ cứng động mạch tăng |
| **>60** | **50-70** | Bình thường cho tuổi |
| **>70** | **55-80** | Động mạch cứng do tuổi |

### Ví dụ kết quả có PP cao hợp lệ:

```
Tuổi: 75 tuổi
SBP: 160 mmHg (cao)
DBP: 85 mmHg
PP: 75 mmHg ← HỢP LỆ (bình thường cho tuổi)
```

```
Tuổi: 80 tuổi (suy tim)
SBP: 175 mmHg
DBP: 60 mmHg
PP: 115 mmHg ← HỢP LỆ (bệnh lý suy tim)
Kết luận: Độ cứng động mạch cao do tuổi + suy tim
```

---

## 🛠️ Khuyến nghị Hành động

### **1. Kiểm tra ngay Calibration HX710B** ⚠️
```bash
# Chạy test calibration
python tests/test_hx710b_driver.py
# hoặc
python tests/calibrate_offset.py
```

### **2. Tạm thời điều chỉnh Ngưỡng (Nếu calibration khó)**
Sửa file `/home/pi/Desktop/IoT_health/src/utils/health_validators.py`:
- Đổi `elif pulse_pressure > 100:` thành `elif pulse_pressure > 120:`
- Thu thập dữ liệu thực tế (50-100 lần đo)
- Phân tích PP trung bình và phương sai
- Điều chỉnh ngưỡng dựa trên kết quả

### **3. Thêm Flag Warning thay vì Error**
```python
# Thay vì error, có thể:
if pulse_pressure > 100:
    logger.warning(f"High PP ({pulse_pressure} mmHg) - verify calibration")
    # Vẫn lưu dữ liệu nhưng đánh dấu cảnh báo
```

### **4. Ghi thêm Device Age + Thông tin Bệnh nhân**
Huyết áp bình thường phụ thuộc tuổi, cần lưu trữ:
- `age` (tuổi bệnh nhân)
- `medical_history` (bệnh lý)
- `medications` (thuốc uống)

---

## 📝 Tóm tắt

| Vấn đề | Nguyên nhân | Giải pháp |
|--------|-----------|----------|
| PP = 152.51 mmHg | Calibration sai | Kiểm tra `offset_counts` + `slope_mmhg_per_count` |
| Ngưỡng quá chặt | Validation > 100 | Điều chỉnh thành > 120 hoặc > 150 |
| Không linh hoạt | Từ chối toàn bộ | Thêm warning flag thay vì error |
| Không có context | Không lưu tuổi | Thêm `age`, `medical_history` |

**Action ngay:** Kiểm tra file calibration HX710B trong `config/app_config.yaml` 🎯
