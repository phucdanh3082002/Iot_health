# Phân Tích: Hệ Thống Tạo Ngưỡng Huyết Áp Thông Minh (AI-Driven Threshold Generation)

## 📋 Tóm tắt Ý tưởng

**Mục tiêu:**
1. **Android App** nhận input từ user: tuổi, giới tính, bệnh nền, thuốc đang sử dụng
2. **AI API** xử lý dữ liệu → sinh ngưỡng cá nhân hóa (SBP/DBP/MAP)
3. **Backend** lưu trữ ngưỡng → **MQTT publish** tới IoT Device
4. **IoT Device** cập nhật ngưỡng, sử dụng để cảnh báo

```
┌─────────────────────────────────────────────────────────┐
│ ANDROID APP                                             │
│ ┌──────────────────────────────────────────────────┐   │
│ │ Input Screen:                                    │   │
│ │ - Tuổi (age)                                     │   │
│ │ - Giới tính (gender)                             │   │
│ │ - Bệnh nền (medical_history: diabetes, ...)      │   │
│ │ - Thuốc (medications: antihypertensive, ...)      │   │
│ │ - [Generate Thresholds] button                    │   │
│ └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                          ↓ HTTP POST
┌─────────────────────────────────────────────────────────┐
│ BACKEND API (IoT_health)                                │
│ POST /api/thresholds/generate                          │
│ Request: {age, gender, medical_history, medications}   │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ AI MODEL (OpenAI / Local LLM / Rule-Based)              │
│ → Phân tích → Sinh ngưỡng cá nhân hóa                   │
│ Response: {sbp_min, sbp_max, dbp_min, dbp_max, ...}    │
└─────────────────────────────────────────────────────────┘
                          ↓ HTTP Response
┌─────────────────────────────────────────────────────────┐
│ ANDROID APP                                             │
│ Display generated thresholds → [Confirm & Apply]        │
└─────────────────────────────────────────────────────────┘
                          ↓ HTTP PUT
┌─────────────────────────────────────────────────────────┐
│ BACKEND API (IoT_health)                                │
│ PUT /api/thresholds/{patient_id}                        │
│ Request: {sbp_min, sbp_max, dbp_min, dbp_max, ...}     │
└─────────────────────────────────────────────────────────┘
                          ↓ MySQL Update
┌─────────────────────────────────────────────────────────┐
│ MySQL Database                                          │
│ UPDATE patient_thresholds SET ...                       │
└─────────────────────────────────────────────────────────┘
                          ↓ MQTT Publish
┌─────────────────────────────────────────────────────────┐
│ MQTT Broker (HiveMQ Cloud)                              │
│ Topic: patient/{patient_id}/commands                    │
│ Payload: {command: "set_thresholds", thresholds: {...}} │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ IOT DEVICE (Raspberry Pi)                               │
│ Subscribe & Update local thresholds                      │
│ Use for real-time alert checking                         │
└─────────────────────────────────────────────────────────┘
```

---

## ✅ Tính Khả Thi - Đánh Giá Chi Tiết

### **1. Android App Layer** ✅ CÓ KHẢ NĂNG

**Status**: CẦN THÊM NỚI DUNG

**Công việc cần làm:**
- [ ] Tạo `ThresholdGenerationScreen` hoặc thêm vào `SettingsScreen`
- [ ] Form input: age, gender, medical_history, medications
- [ ] HTTP client gọi Backend API
- [ ] Display kết quả + preview ngưỡng
- [ ] Button "Apply Thresholds" → lưu local + MQTT publish

**Tech Stack Khả dụng:**
```kotlin
// Retrofit2 (HTTP client) - thường được dùng trong Android
// Room Database (local cache)
// Coroutines (async operations)
// MQTT Client (Paho Android) - đã có
```

**Ước tính Effort**: 5-8 giờ (1-2 ngày)

---

### **2. Backend API Layer** ⚠️ CẦN PHÁT TRIỂN

**Status**: CẦN TẠỚI MỚI

**API Endpoints cần triển khai:**

#### **A. Generate Thresholds (AI)**
```
POST /api/thresholds/generate
Content-Type: application/json

Request Body:
{
  "age": 65,
  "gender": "male",  // male, female
  "medical_history": ["hypertension", "diabetes", "obesity"],
  "medications": ["lisinopril", "metoprolol"],
  "activity_level": "moderate",  // sedentary, moderate, active
  "smoking_status": "former"     // never, current, former
}

Response (200 OK):
{
  "status": "success",
  "thresholds": {
    "systolic": {
      "normal_min": 90,
      "normal_max": 130,
      "warning_min": 130,
      "warning_max": 140,
      "critical_min": 140
    },
    "diastolic": {
      "normal_min": 60,
      "normal_max": 85,
      "warning_min": 85,
      "warning_max": 90,
      "critical_min": 90
    },
    "map": {
      "normal_min": 70,
      "normal_max": 100,
      "warning_min": 100,
      "critical_min": 120
    },
    "pulse_pressure": {
      "normal_max": 70,
      "warning_max": 100,
      "critical_min": 100
    }
  },
  "reasoning": "Age 65 + hypertension → stricter control targets per ESC/ESH guidelines",
  "generated_at": "2025-12-05T10:30:00Z"
}
```

#### **B. Update Patient Thresholds**
```
PUT /api/thresholds/{patient_id}
Content-Type: application/json

Request Body:
{
  "systolic": { "normal_min": 90, "normal_max": 130, ... },
  "diastolic": { "normal_min": 60, "normal_max": 85, ... },
  ...
}

Response (200 OK):
{
  "status": "success",
  "message": "Thresholds updated",
  "patient_id": "patient_001",
  "updated_at": "2025-12-05T10:30:00Z"
}

Side effect: MQTT publish command to device
```

#### **C. Get Current Thresholds**
```
GET /api/thresholds/{patient_id}

Response (200 OK):
{
  "thresholds": {...},
  "updated_at": "2025-12-05T10:30:00Z",
  "last_synced_to_device": "2025-12-05T10:35:00Z"
}
```

**Implementation Options:**

**File cần tạo**: `scripts/api.py` (nếu chưa có) hoặc `src/communication/rest_client.py`

```python
# Endpoint handler (pseudocode)
@app.post("/api/thresholds/generate")
async def generate_thresholds(request: ThresholdGenerationRequest):
    """
    AI-powered threshold generation based on patient profile
    
    Flow:
    1. Validate input
    2. Call AI model / rule engine
    3. Generate personalized thresholds
    4. Return response
    """
    # 1. Validate
    if not request.age or not request.gender:
        return {"error": "Missing required fields"}
    
    # 2. Call AI model
    thresholds = ai_model.generate_thresholds(
        age=request.age,
        gender=request.gender,
        medical_history=request.medical_history,
        medications=request.medications
    )
    
    # 3. Return
    return {
        "status": "success",
        "thresholds": thresholds
    }

@app.put("/api/thresholds/{patient_id}")
async def update_thresholds(patient_id: str, thresholds: ThresholdData):
    """
    Update patient thresholds & publish to device via MQTT
    """
    # 1. Update DB
    db.update_patient_thresholds(patient_id, thresholds)
    
    # 2. Publish MQTT
    mqtt_client.publish(
        topic=f"patient/{patient_id}/commands",
        payload={"command": "set_thresholds", "thresholds": thresholds},
        qos=2
    )
    
    return {"status": "success"}
```

**Ước tính Effort**: 8-12 giờ (2-3 ngày)

---

### **3. AI Model Layer** 🔑 QUYẾT ĐỊNH CHÍNH

**Status**: CẦN LỰA CHỌN

#### **Option A: OpenAI API (Cloud)** ☁️

**Ưu điểm:**
- ✅ Chính xác cao (GPT-4 medical knowledge)
- ✅ Flexible - có thể xử lý context phức tạp
- ✅ Không cần training
- ✅ Dễ integrate

**Nhược điểm:**
- ❌ Chi phí ($0.03-0.06 per request)
- ❌ Phụ thuộc internet
- ❌ Latency cao (1-2 giây)
- ❌ Rate limiting

**Chi phí ước tính:**
- 100 requests/ngày × $0.05 = $5/ngày = $150/tháng
- Nếu có 100 bệnh nhân × 1 lần/tháng = $50/tháng

**Khuyến nghị**: Tốt nếu budget có sẵn + không quan tâm chi phí

---

#### **Option B: Local LLM (Self-hosted)** 🏠

**Models có thể dùng:**
- `ollama` + `mistral` / `llama2` (8-40GB)
- `llamafile` (single executable)

**Ưu điểm:**
- ✅ MIỄN PHÍ (chi phí điện + GPU)
- ✅ Latency thấp (local)
- ✅ Privacy (data không upload)
- ✅ Offline-capable

**Nhược điểm:**
- ❌ Cần máy mạnh (GPU/NPU)
- ❌ Setup phức tạp
- ❌ Accuracy không bằng GPT-4
- ❌ Maintenance overhead

**Hardware yêu cầu:**
- GPU: NVIDIA RTX 3060+ hoặc tương đương
- RAM: 8-16GB
- Storage: 10-20GB

**Setup ước tính**: 2-4 giờ

**Khuyến nghị**: Tốt nếu đã có server + không muốn chi phí recurring

---

#### **Option C: Rule-Based System (Logic)** 🎯

**Khái niệm:**
```python
def generate_thresholds(age, gender, medical_history, medications):
    """
    Rule-based threshold generation without AI
    """
    # Base threshold (healthy young adult)
    thresholds = {
        "systolic_max": 120,
        "diastolic_max": 80,
        "map_max": 100
    }
    
    # Adjustment 1: Age
    if age > 60:
        thresholds["systolic_max"] = 130  # ESC/ESH 2018 for >60
    elif age > 70:
        thresholds["systolic_max"] = 140  # More lenient for >70
    
    # Adjustment 2: Medical History
    if "diabetes" in medical_history:
        thresholds["diastolic_max"] = 75  # Stricter for diabetics
    
    if "ckd" in medical_history:  # Chronic Kidney Disease
        thresholds["systolic_max"] = 120  # Very strict
    
    # Adjustment 3: Medications
    if "lisinopril" in medications:  # ACE inhibitor already on board
        thresholds["systolic_max"] = 130
    
    return thresholds
```

**Ưu điểm:**
- ✅ MIỄN PHÍ (chỉ code)
- ✅ Instant response
- ✅ Deterministic + interpretable
- ✅ Không cần GPU

**Nhược điểm:**
- ❌ Rigid - không linh hoạt với edge cases
- ❌ Cần domain expert để thiết kế rules
- ❌ Khó maintain khi có nhiều biến

**Setup ước tính**: 4-6 giờ (thiết kế rules)

**Khuyến nghị**: **TỐT NHẤT CHO BĐ ĐẦU** - dễ dàng + không có chi phí

---

### **4. Database Layer** ✅ ĐÃ CÓ

**Tables cần thêm/cập nhật:**

```sql
-- MySQL Cloud (AWS RDS)
CREATE TABLE patient_thresholds (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id VARCHAR(255) NOT NULL,
    
    -- Systolic thresholds
    systolic_normal_min INT,
    systolic_normal_max INT,
    systolic_warning_min INT,
    systolic_warning_max INT,
    systolic_critical_min INT,
    
    -- Diastolic thresholds
    diastolic_normal_min INT,
    diastolic_normal_max INT,
    diastolic_warning_min INT,
    diastolic_warning_max INT,
    diastolic_critical_min INT,
    
    -- MAP thresholds
    map_normal_min INT,
    map_normal_max INT,
    map_warning_min INT,
    map_warning_max INT,
    map_critical_min INT,
    
    -- Pulse Pressure thresholds
    pulse_pressure_normal_max INT,
    pulse_pressure_warning_max INT,
    pulse_pressure_critical_min INT,
    
    -- Metadata
    generation_method ENUM('ai', 'rule_based', 'manual'),
    generated_at TIMESTAMP,
    updated_at TIMESTAMP,
    
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id),
    UNIQUE KEY (patient_id)
);

-- SQLite Local (Offline cache)
CREATE TABLE patient_thresholds (
    patient_id TEXT PRIMARY KEY,
    systolic_normal_min INTEGER,
    systolic_normal_max INTEGER,
    ...
    generation_method TEXT,
    generated_at REAL,
    updated_at REAL
);
```

**Ước tính Effort**: 2-3 giờ (schema + migration)

---

### **5. MQTT Integration Layer** ✅ ĐÃ GẦN HẦN

**MQTT Command Flow:**

```
Topic: patient/{patient_id}/commands
QoS: 2 (exactly once)

Command Payload:
{
  "command_id": "cmd_1733379600",
  "timestamp": 1733379600.123,
  "issuer": "android_app",
  "command": "set_thresholds",
  "parameters": {
    "systolic_min": 90,
    "systolic_max": 130,
    "diastolic_min": 60,
    "diastolic_max": 85,
    "map_min": 70,
    "map_max": 100,
    "pulse_pressure_max": 70
  }
}

Response (IoT Device):
{
  "device_id": "rpi_bp_001",
  "command_id": "cmd_1733379600",
  "status": "success",
  "message": "Thresholds updated",
  "timestamp": 1733379600.456
}
```

**IoT Device Handler (Python):**

```python
def on_mqtt_command_received(message):
    """Handle set_thresholds command from Android"""
    payload = json.loads(message.payload)
    
    if payload["command"] == "set_thresholds":
        # Update local thresholds
        app_instance.update_thresholds(payload["parameters"])
        
        # Save to SQLite (persistent)
        db.update_thresholds(payload["parameters"])
        
        # Log
        logger.info(f"Thresholds updated: {payload['parameters']}")
        
        # Send acknowledgment
        mqtt_client.publish(
            topic=f"device/{device_id}/status",
            payload={
                "command_id": payload["command_id"],
                "status": "success"
            },
            qos=2
        )
```

**Ước tính Effort**: 3-4 giờ (handler + integration)

---

## 📊 So Sánh Các Phương Án AI

| Tiêu chí | OpenAI | Local LLM | Rule-Based |
|----------|--------|-----------|-----------|
| **Chi phí** | $150/tháng | $0 | $0 |
| **Latency** | 1-2s | 100-500ms | <10ms |
| **Accuracy** | 95%+ | 80-90% | 70-80% |
| **Setup time** | 1h | 4h | 6h |
| **Maintenance** | Thấp | Cao | Trung bình |
| **Flexibility** | Rất cao | Cao | Thấp |
| **Privacy** | Không | Có | Có |
| **Phù hợp MVP** | ❌ | ⚠️ | ✅ |

---

## 🎯 Khuyến Nghị Phương Án

### **Giai đoạn 1 (MVP): Rule-Based** ✅ KHUYẾN NGHỊ

**Tại sao:**
- Nhanh implement (1-2 ngày)
- Không chi phí
- Đủ chính xác cho MVP
- Có thể nâng cấp sau

**Implementation:**

```python
# src/ai/threshold_generator.py
class ThresholdGenerator:
    """Rule-based threshold generation"""
    
    BASE_THRESHOLDS = {
        "systolic_max": 120,
        "diastolic_max": 80,
        "map_max": 100,
        "pulse_pressure_max": 50
    }
    
    @staticmethod
    def generate(age: int, gender: str, medical_history: list, medications: list):
        thresholds = ThresholdGenerator.BASE_THRESHOLDS.copy()
        
        # Age adjustment
        if age >= 65:
            thresholds["systolic_max"] = 130  # ESC/ESH 2018
        elif age >= 75:
            thresholds["systolic_max"] = 140  # Lenient for >75
        
        # Medical history adjustment
        for condition in medical_history:
            if condition == "diabetes":
                thresholds["diastolic_max"] = 75
                thresholds["systolic_max"] = 130
            elif condition == "ckd":
                thresholds["systolic_max"] = 120
                thresholds["diastolic_max"] = 75
            elif condition == "cvd":
                thresholds["systolic_max"] = 130
        
        return thresholds
```

**Timeline:** 2-3 tuần (toàn bộ hệ thống)

---

### **Giai đoạn 2 (v2.0): Nâng cấp OpenAI/LLM**

Sau MVP ổn định, có thể:
1. Integrate OpenAI API
2. Compare kết quả vs Rule-based
3. Hybrid approach (LLM + Rules)

---

## 📋 Implementation Roadmap

### **Week 1-2: Backend API + Rule Engine**

- [ ] Design database schema (patient_thresholds table)
- [ ] Create REST endpoints (POST /generate, PUT /update, GET /get)
- [ ] Implement ThresholdGenerator (rule-based)
- [ ] Add MQTT integration (publish set_thresholds command)
- [ ] Unit tests

**Deliverable**: Functional API endpoints

### **Week 2-3: Android App Integration**

- [ ] Create ThresholdGenerationScreen (Jetpack Compose)
- [ ] Implement Retrofit HTTP client
- [ ] Add form validation
- [ ] Display & preview thresholds
- [ ] MQTT publisher for confirmation

**Deliverable**: End-to-end flow (Android → API → DB → MQTT → Device)

### **Week 3-4: IoT Device Handler**

- [ ] MQTT command listener (set_thresholds)
- [ ] Local threshold update logic
- [ ] SQLite persistence
- [ ] Status response publisher

**Deliverable**: Device receives & applies thresholds

### **Week 4-5: Testing & Refinement**

- [ ] E2E testing
- [ ] Threshold accuracy validation
- [ ] Performance optimization
- [ ] Documentation

**Deliverable**: Production-ready system

---

## 🚨 Potential Issues & Mitigation

### **Issue 1: Medical Accuracy**

**Problem**: Rule-based system không đủ chính xác y tế

**Mitigation:**
- Collaborate với bác sĩ → validate rules
- Include disclaimers: "Consult doctor before using"
- Log all generated thresholds → audit trail

### **Issue 2: MQTT Connectivity**

**Problem**: Device offline khi nhận command

**Mitigation:**
- Use **Last Will & Testament** → detect offline
- Queue thresholds locally on app
- Retry on device reconnection

### **Issue 3: Data Privacy**

**Problem**: Gửi medical info lên cloud API

**Mitigation:**
- Use HTTPS/TLS encryption
- Don't log sensitive data
- Option: Local LLM (private)

### **Issue 4: Latency**

**Problem**: AI API quá chậm (1-2s) cho user experience

**Mitigation:**
- Cache results (same profile → same thresholds)
- Show loading spinner
- Option: Rule-based as fallback

---

## 📝 API Specification (Complete)

### **Authentication**

```http
Header: Authorization: Bearer {token}
Header: X-Device-ID: {device_id}
```

### **Error Handling**

```json
{
  "error": {
    "code": "INVALID_AGE",
    "message": "Age must be between 1 and 150",
    "details": {"age": 999}
  }
}
```

---

## 🎓 Medical Knowledge Base (Rules)

### **ESC/ESH 2018 Guidelines**

```
Adults:
- Optimal: SBP < 120 & DBP < 80
- Normal: SBP 120-129 & DBP < 80
- High-normal: SBP 130-139 & DBP 80-89

Hypertension Stage 1: SBP 140-159 or DBP 90-99
Hypertension Stage 2: SBP ≥ 160 or DBP ≥ 100

Older adults (≥65):
- Target: SBP 120-130 (vs 130-140 in younger)
- More lenient >75 or frail

Diabetes:
- Target: SBP < 130, DBP < 80 (stricter)

CKD:
- Target: SBP < 120, DBP < 75 (strictest)
```

---

## ✅ Kết Luận

**Tính khả thi: 9/10** ✅ CÓ KHẢ NĂNG THỰC HIỆN

**Khuyến nghị:**
1. **Bắt đầu với Rule-Based** (nhanh, hiệu quả)
2. **Tổng effort: 3-4 tuần** (toàn bộ hệ thống)
3. **Chi phí: $0** (nếu dùng rule-based)
4. **Nâng cấp sau với OpenAI** khi cần flexibility

**Next step:** Bạn muốn bắt đầu từ Backend API hay Android App trước?
