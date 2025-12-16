# Cách sử dụng `ai_threshold_generator.py`

## 📍 Vị trí file

**File:** `scripts/ai_threshold_generator.py` (637 lines)  
**Server deployment:** `/var/www/iot-health-api/scripts/ai_threshold_generator.py`

---

## 🔗 Nơi sử dụng

### **1. Backend API (`scripts/api.py`)**

**Import:**
```python
# Line 20
from ai_threshold_generator import ThresholdGenerator
```

**Khởi tạo (Line 41-48):**
```python
# Initialize AI Threshold Generator
try:
    threshold_generator = ThresholdGenerator(
        db_config=DB_CONFIG,
        gemini_api_key=os.getenv('GOOGLE_GEMINI_API_KEY')
    )
    logger.info("✅ ThresholdGenerator initialized")
except Exception as e:
    logger.warning(f"⚠️ ThresholdGenerator initialization failed: {e}")
    threshold_generator = None
```

**Sử dụng #1: Tạo patient mới với AI thresholds (Line 406-440)**
```python
# Endpoint: POST /api/patients
# Khi generate_ai_thresholds = true

if generate_ai_thresholds and threshold_generator:
    # Use AI to generate personalized thresholds
    logger.info(f"🤖 Generating AI thresholds for new patient {patient_id}")
    
    patient_data = {
        'age': age, 'gender': gender, 'height': height, 'weight': weight,
        'blood_type': blood_type, 'chronic_diseases': chronic_diseases or [],
        'medications': medications or [], 'allergies': allergies or [],
        'family_history': family_history or [],
        'smoking_status': smoking_status,
        'alcohol_consumption': alcohol_consumption,
        'exercise_frequency': exercise_frequency
    }
    
    # Gọi ThresholdGenerator
    result = threshold_generator.generate_thresholds(patient_data, method=threshold_method)
    
    # Lưu vào database
    for vital_sign, thresholds in result['thresholds'].items():
        cursor.execute("""
            INSERT INTO patient_thresholds (
                patient_id, vital_sign,
                min_normal, max_normal, min_warning, max_warning,
                min_critical, max_critical,
                generation_method, ai_confidence, ai_model,
                generation_timestamp, metadata, is_active
            )
            VALUES (%s, %s, ...)
        """, (...))
```

**Sử dụng #2: API endpoint `/api/ai/generate-thresholds` (Line 2097-2220)**
```python
@app.route('/api/ai/generate-thresholds', methods=['POST'])
def generate_ai_thresholds():
    """
    POST /api/ai/generate-thresholds
    
    Request:
    {
        "patient_id": "patient_001",
        "method": "hybrid"  // rule_based, ai_generated, or hybrid
    }
    
    Response:
    {
        "status": "success",
        "data": {
            "patient_id": "patient_001",
            "thresholds": {...},
            "metadata": {...}
        }
    }
    """
    
    # Validate input
    data = request.get_json()
    patient_id = data.get('patient_id')
    method = data.get('method', 'hybrid')
    
    # Get patient from database
    cursor.execute("""
        SELECT patient_id, name, age, gender, height, weight, blood_type,
               medical_conditions, chronic_diseases, medications, allergies,
               family_history, smoking_status, alcohol_consumption,
               exercise_frequency, risk_factors
        FROM patients
        WHERE patient_id = %s AND is_active = 1
    """)
    
    # Generate thresholds
    result = threshold_generator.generate_thresholds(patient, method=method)
    
    # Save to database
    for vital_sign, thresholds in result['thresholds'].items():
        cursor.execute("""
            INSERT INTO patient_thresholds (...)
            VALUES (...)
            ON DUPLICATE KEY UPDATE ...
        """)
```

---

## 📊 Data Flow

```
┌─────────────────────────────────────────┐
│   Android App / API Request             │
│   POST /api/patients (with AI flags)    │
│   or POST /api/ai/generate-thresholds   │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│   api.py (scripts/api.py)               │
│   - Extract patient data                │
│   - Call ThresholdGenerator()           │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│   ThresholdGenerator                    │
│   (scripts/ai_threshold_generator.py)   │
│                                         │
│   Methods:                              │
│   - generate_thresholds()               │
│   - _generate_rule_based()              │
│   - _generate_ai_powered()              │
│   - _refine_with_ai()                   │
└────────────────┬────────────────────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
    ┌────────────┐  ┌──────────────────┐
    │ MySQL DB  │  │ Google Gemini API│
    │           │  │ (Optional)       │
    │ Rules:    │  │                  │
    │ - Load    │  │ AI Refinement    │
    │   rules   │  │                  │
    │ - Apply   │  └──────────────────┘
    │   to      │
    │   patient │
    └────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│   Generated Thresholds                  │
│   {                                     │
│     "thresholds": {...},                │
│     "metadata": {                       │
│       "generation_method": "hybrid",    │
│       "ai_confidence": 0.95,            │
│       "applied_rules": [...]            │
│     }                                   │
│   }                                     │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│   api.py saves to MySQL                 │
│   patient_thresholds table              │
│   - INSERT or UPDATE per vital_sign     │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│   CloudSyncManager (Pi)                 │
│   Syncs from MySQL → SQLite             │
│   Every 60 seconds                      │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│   AlertSystem (Pi)                      │
│   Loads patient-specific thresholds     │
│   Uses for vital signs checking         │
└─────────────────────────────────────────┘
```

---

## 🔧 Các methods trong ThresholdGenerator

### **1. `__init__(db_config, gemini_api_key=None)`**
```python
# Khởi tạo generator
generator = ThresholdGenerator(
    db_config={
        'host': 'database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com',
        'user': 'admin',
        'password': 'password',
        'database': 'iot_health_cloud'
    },
    gemini_api_key='your_gemini_key'  # Optional
)
```

### **2. `generate_thresholds(patient_data, method='hybrid')`**
Main method để generate thresholds.

**Parameters:**
- `patient_data`: Dict với fields:
  - `age`, `gender`, `height`, `weight`, `blood_type`
  - `chronic_diseases`, `medications`, `allergies`, `family_history`
  - `smoking_status`, `alcohol_consumption`, `exercise_frequency`

- `method`: 'rule_based', 'ai_generated', hoặc 'hybrid'

**Returns:**
```python
{
    'thresholds': {
        'heart_rate': {
            'min_critical': 40,
            'min_normal': 60,
            'max_normal': 100,
            'max_critical': 120,
            'min_warning': 55,
            'max_warning': 110
        },
        'spo2': {...},
        'temperature': {...},
        'systolic_bp': {...},
        'diastolic_bp': {...}
    },
    'metadata': {
        'generation_method': 'hybrid',
        'ai_model': 'rule_based + gemini-1.5-pro',
        'ai_confidence': 0.95,
        'generation_timestamp': '2025-12-15T18:30:00',
        'applied_rules': [
            {
                'vital_sign': 'heart_rate',
                'rule': 'Elderly HR Adjustment: +5/-5 BPM',
                'priority': 1
            },
            {...}
        ],
        'input_factors': {
            'age': 65,
            'gender': 'M',
            'bmi': 25.5,
            'chronic_disease_count': 1,
            'smoking_status': 'former'
        }
    }
}
```

### **3. `_generate_rule_based(patient_data)`**
Apply medical rules từ database.

**Process:**
1. Load baseline thresholds
2. Query `threshold_generation_rules` table
3. Match rules dựa vào patient conditions
4. Apply adjustments để từng vital sign
5. Calculate confidence score

### **4. `_generate_ai_powered(patient_data)`**
Dùng Google Gemini API để generate.

### **5. `_refine_with_ai(rule_thresholds, patient_data)`**
Hybrid mode: refinement rule-based thresholds với AI.

---

## 📋 API Endpoints sử dụng ThresholdGenerator

### **Endpoint 1: Create Patient with AI Thresholds**

```bash
POST /api/patients
```

**Request:**
```json
{
  "name": "Nguyen Van A",
  "age": 65,
  "gender": "male",
  "height": 170,
  "weight": 75,
  "blood_type": "A+",
  "device_id": "rpi_bp_001",
  "chronic_diseases": [
    {"name": "Hypertension", "severity": "moderate"},
    {"name": "Diabetes", "severity": "mild"}
  ],
  "medications": ["Metformin", "Amlodipine"],
  "smoking_status": "former",
  "exercise_frequency": "weekly",
  "generate_ai_thresholds": true,
  "threshold_generation_method": "hybrid"
}
```

**Response:**
```json
{
  "status": "success",
  "patient_id": "patient_001",
  "message": "Patient created with AI thresholds",
  "thresholds_generated": 5,
  "generation_method": "hybrid",
  "confidence_score": 0.95
}
```

### **Endpoint 2: Generate/Regenerate Thresholds for Existing Patient**

```bash
POST /api/ai/generate-thresholds
```

**Request:**
```json
{
  "patient_id": "patient_001",
  "method": "hybrid"
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "patient_id": "patient_001",
    "thresholds": {
      "heart_rate": {
        "min_critical": 40,
        "min_normal": 65,
        "max_normal": 85,
        "max_critical": 120
      },
      ...
    },
    "metadata": {
      "generation_method": "hybrid",
      "ai_confidence": 0.95,
      "generation_timestamp": "2025-12-15T18:30:00",
      "applied_rules": [...]
    }
  }
}
```

---

## 🔐 Environment Variables cần thiết

Để ThresholdGenerator hoạt động đầy đủ:

```bash
# MySQL Cloud
MYSQL_HOST=database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com
MYSQL_USER=admin
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=iot_health_cloud

# Google Gemini API (Option, cho AI mode)
GOOGLE_GEMINI_API_KEY=your_gemini_key

# Database user (fallback)
DB_USER=admin
```

---

## 📦 Dependencies

```
mysql-connector-python>=8.0.0    # MySQL connection
google-generativeai>=0.3.0       # Google Gemini API
flask>=2.3.0                     # Flask API
```

---

## ✅ Database Tables sử dụng

### **1. `threshold_generation_rules`**
Chứa medical rules cho threshold generation.

**Columns:**
- `id`: Auto-increment
- `vital_sign`: heart_rate, spo2, temperature, systolic_bp, diastolic_bp
- `conditions`: JSON - age_range, chronic_diseases, smoking_status, etc.
- `min_normal_adjustment`, `max_normal_adjustment`: Điều chỉnh từ baseline
- `min_critical_adjustment`, `max_critical_adjustment`
- `justification`: Lý do rule này
- `priority`: Thứ tự apply
- `is_active`: Boolean

**Example:**
```sql
INSERT INTO threshold_generation_rules VALUES (
  NULL,
  'heart_rate',
  '{"age_range": [60, 80], "chronic_diseases": ["Hypertension"]}',
  -5,   -- Reduce min_normal by 5
  -5,   -- Reduce max_normal by 5
  0,
  0,
  'Elderly + Hypertension: Lower HR targets',
  1,
  TRUE
);
```

### **2. `patient_thresholds`**
Lưu generated thresholds cho mỗi patient.

**Columns:**
- `id`: Auto-increment
- `patient_id`: FK to patients
- `vital_sign`: heart_rate, spo2, etc.
- `min_normal`, `max_normal`, `min_warning`, `max_warning`
- `min_critical`, `max_critical`
- `generation_method`: 'rule_based', 'ai_generated', 'hybrid', 'manual'
- `ai_confidence`: 0.0 - 1.0
- `ai_model`: 'rule_based', 'gemini-1.5-pro', 'hybrid', 'baseline'
- `generation_timestamp`: When generated
- `metadata`: JSON with applied_rules, input_factors
- `is_active`: Boolean

---

## 🧪 Testing ThresholdGenerator

### **Standalone test:**

```python
# scripts/ai_threshold_generator.py có built-in CLI test

cd /home/pi/Desktop/IoT_health/
python3 scripts/ai_threshold_generator.py
```

**Output:**
```
============================================================
AI Threshold Generator - Test
============================================================

📊 Generated Thresholds:

HEART_RATE:
  Normal:   65.0 - 85.0
  Warning:  60.0 - 90.0
  Critical: 40.0 - 120.0

SOO2:
  Normal:   95.0 - 100.0
  Warning:  92.0 - 100.0
  Critical: 85.0 - 100.0

...

📋 Metadata:
  Method: hybrid
  Model: rule_based + gemini-1.5-pro
  Confidence: 0.95
  Rules Applied: 4
```

### **Via API test:**

```bash
curl -X POST http://localhost:8000/api/ai/generate-thresholds \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "patient_001",
    "method": "hybrid"
  }'
```

---

## 🎯 Summary

| Item | Value |
|------|-------|
| **File** | `scripts/ai_threshold_generator.py` |
| **Main Class** | `ThresholdGenerator` |
| **Used in** | `scripts/api.py` (Flask API) |
| **Key Methods** | `generate_thresholds()`, `_generate_rule_based()`, `_generate_ai_powered()` |
| **Endpoints** | `/api/patients` (POST), `/api/ai/generate-thresholds` (POST) |
| **Databases** | `threshold_generation_rules`, `patient_thresholds` tables |
| **Dependencies** | mysql-connector-python, google-generativeai |
| **Environment** | GOOGLE_GEMINI_API_KEY (optional) |

