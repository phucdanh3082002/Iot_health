# REST API Specification - IoT Health Monitor

## Base URL
```
http://47.130.193.237:8000
```

---

## 1. Health Check

### Endpoint
```http
GET /api/health
```

### Response (200 OK)
```json
{
  "status": "ok",
  "database": "connected",
  "version": "1.0.0",
  "timestamp": "2025-11-17T21:00:00.000000"
}
```

---

## 2. Device Pairing (QR Code)

### Endpoint
```http
POST /api/pair-device
```

### Request Headers
```
Content-Type: application/json
```

### Request Body
```json
{
  "pairing_code": "ABC123XYZ",
  "user_id": "user_001",
  "nickname": "Máy đo của bố"
}
```

**Fields:**
- `pairing_code` (required): Mã pairing từ QR code
- `user_id` (required): ID của user Android
- `nickname` (required): Tên thiết bị do user đặt (e.g., "Phòng khách", "Máy đo huyết áp gia đình")

### Success Response (200 OK)
```json
{
  "success": true,
  "device_id": "rpi_bp_001",
  "device_type": "blood_pressure",
  "location": "Living Room",
  "patient_id": "patient_001",
  "patient_name": "Nguyen Van A",
  "patient_age": 65,
  "patient_gender": "male",
  "nickname": "Máy đo của bố",
  "mqtt_topics": {
    "vitals": "iot_health/device/rpi_bp_001/vitals",
    "alerts": "iot_health/device/rpi_bp_001/alerts",
    "status": "iot_health/device/rpi_bp_001/status",
    "commands": "iot_health/patient/patient_001/commands"
  },
  "thresholds": {
    "heart_rate": {"min": 60, "max": 100, "critical_min": 40, "critical_max": 120},
    "spo2": {"min": 95, "max": 100, "critical_min": 90, "critical_max": 100},
    "temperature": {"min": 36.0, "max": 37.5, "critical_min": 35.0, "critical_max": 39.0},
    "systolic_bp": {"min": 90, "max": 140, "critical_min": 70, "critical_max": 180},
    "diastolic_bp": {"min": 60, "max": 90, "critical_min": 40, "critical_max": 120}
  }
}
```

### Error Responses

#### Invalid Pairing Code (404 Not Found)
```json
{
  "success": false,
  "error": "Invalid pairing code",
  "message": "Mã pairing không hợp lệ hoặc đã hết hạn"
}
```

#### Missing Required Fields (400 Bad Request)
```json
{
  "success": false,
  "error": "Missing required fields",
  "message": "Vui lòng cung cấp đầy đủ: pairing_code, user_id, nickname"
}
```

#### Device Already Paired (409 Conflict)
```json
{
  "success": false,
  "error": "Device already paired",
  "message": "Thiết bị đã được kết nối với user khác"
}
```

### Backend Implementation Notes

#### SQL Queries
```sql
-- 1. Verify pairing code và lấy device info
SELECT d.device_id, d.device_type, d.location,
       p.patient_id, p.name as patient_name, p.age, p.gender
FROM devices d
JOIN patients p ON d.device_id = p.device_id
WHERE d.pairing_code = %s
  AND d.is_active = 1
  AND (d.pairing_code_expires_at IS NULL OR d.pairing_code_expires_at > NOW())
LIMIT 1;

-- 2. Insert vào device_ownership (save nickname)
INSERT INTO device_ownership (user_id, device_id, role, nickname, access_granted_at)
VALUES (%s, %s, 'owner', %s, NOW())
ON DUPLICATE KEY UPDATE 
  nickname = VALUES(nickname),
  last_access = NOW();

-- 3. Lấy thresholds cho patient
SELECT vital_sign, min_normal, max_normal, min_critical, max_critical
FROM patient_thresholds
WHERE patient_id = %s;
```

---

## 3. Get User's Devices

### Endpoint
```http
GET /api/devices/<user_id>
```

### Response (200 OK)
```json
[
  {
    "device_id": "rpi_bp_001",
    "device_type": "blood_pressure",
    "location": "Living Room",
    "nickname": "Máy đo của bố",
    "status": "online",
    "last_seen": "2025-11-17T20:55:00",
    "patient_id": "patient_001",
    "patient_name": "Nguyen Van A",
    "patient_age": 65,
    "mqtt_topics": {
      "vitals": "iot_health/device/rpi_bp_001/vitals",
      "alerts": "iot_health/device/rpi_bp_001/alerts",
      "status": "iot_health/device/rpi_bp_001/status"
    }
  }
]
```

### SQL Query
```sql
SELECT d.device_id, d.device_type, d.location,
       d.status, d.last_seen, 
       do.nickname, do.access_granted_at,
       p.patient_id, p.name as patient_name, p.age, p.gender
FROM device_ownership do
JOIN devices d ON do.device_id = d.device_id
LEFT JOIN patients p ON d.device_id = p.device_id
WHERE do.user_id = %s
  AND d.is_active = 1
ORDER BY do.last_access DESC;
```

---

## 4. Get Historical Vitals

### Endpoint
```http
GET /api/vitals/<device_id>?start_date=2025-11-17&end_date=2025-11-18&limit=100
```

### Query Parameters
- `start_date` (optional): Ngày bắt đầu (YYYY-MM-DD)
- `end_date` (optional): Ngày kết thúc (YYYY-MM-DD)
- `limit` (optional): Số record tối đa (default: 100, max: 1000)

### Response (200 OK)
```json
{
  "device_id": "rpi_bp_001",
  "count": 50,
  "vitals": [
    {
      "id": 12345,
      "timestamp": "2025-11-17T20:30:00",
      "heart_rate": 78,
      "spo2": 97,
      "temperature": 36.7,
      "systolic_bp": 120,
      "diastolic_bp": 80,
      "mean_arterial_pressure": 93,
      "data_quality": {
        "hr_sqi": 89.5,
        "spo2_cv": 1.8,
        "peak_count": 18,
        "measurement_duration": 24.5
      }
    }
  ]
}
```

### SQL Query
```sql
SELECT id, timestamp, 
       heart_rate, spo2, temperature,
       systolic_bp, diastolic_bp, mean_arterial_pressure,
       sensor_data
FROM health_records
WHERE device_id = %s
  AND timestamp BETWEEN %s AND %s
ORDER BY timestamp DESC
LIMIT %s;
```

---

## 5. Update Device Nickname

### Endpoint
```http
PUT /api/devices/<device_id>/nickname
```

### Request Body
```json
{
  "user_id": "user_001",
  "nickname": "Máy đo phòng ngủ"
}
```

### Success Response (200 OK)
```json
{
  "success": true,
  "device_id": "rpi_bp_001",
  "nickname": "Máy đo phòng ngủ"
}
```

### SQL Query
```sql
UPDATE device_ownership 
SET nickname = %s, last_access = NOW()
WHERE user_id = %s AND device_id = %s;
```

---

## 6. Get Alerts History

### Endpoint
```http
GET /api/alerts/<device_id>?severity=high&limit=50
```

### Query Parameters
- `severity` (optional): Filter by severity (low, medium, high, critical)
- `limit` (optional): Max records (default: 50)

### Response (200 OK)
```json
{
  "device_id": "rpi_bp_001",
  "count": 12,
  "alerts": [
    {
      "id": 567,
      "timestamp": "2025-11-17T18:45:00",
      "alert_type": "high_heart_rate",
      "severity": "high",
      "message": "Nhịp tim cao: 125 BPM (ngưỡng: 60-100)",
      "vital_sign": "heart_rate",
      "current_value": 125,
      "threshold_value": 100,
      "acknowledged": false,
      "resolved": false
    }
  ]
}
```

---

## Error Handling

### Standard Error Response Format
```json
{
  "success": false,
  "error": "error_code",
  "message": "Human-readable error message",
  "timestamp": "2025-11-17T21:00:00"
}
```

### HTTP Status Codes
- `200` - Success
- `400` - Bad Request (invalid parameters)
- `401` - Unauthorized
- `404` - Not Found (invalid pairing code, device not found)
- `409` - Conflict (device already paired)
- `500` - Internal Server Error

---

## Security

### Rate Limiting
- `/api/pair-device`: 10 requests/minute per IP
- Other endpoints: 100 requests/minute per IP

### Input Validation
- Sanitize all input parameters
- Use parameterized queries to prevent SQL injection
- Validate user_id and device_id format

### CORS Policy
```python
# Allow only mobile app and web dashboard
CORS(app, origins=[
    "http://localhost:3000",  # Web dashboard (development)
    "https://yourdomain.com",  # Web dashboard (production)
    "capacitor://localhost",  # Android app (Capacitor)
    "ionic://localhost"       # Android app (Ionic)
])
```

---

## Testing

### cURL Examples

#### Health Check
```bash
curl http://47.130.193.237:8000/api/health
```

#### Pair Device
```bash
curl -X POST http://47.130.193.237:8000/api/pair-device \
  -H "Content-Type: application/json" \
  -d '{
    "pairing_code": "ABC123XYZ",
    "user_id": "user_001",
    "nickname": "Máy đo của bố"
  }'
```

#### Get Devices
```bash
curl http://47.130.193.237:8000/api/devices/user_001
```

#### Get Vitals
```bash
curl "http://47.130.193.237:8000/api/vitals/rpi_bp_001?start_date=2025-11-17&end_date=2025-11-18&limit=100"
```
