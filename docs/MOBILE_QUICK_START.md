# 📱 QUICK START - Mobile App MQTT Integration

## 🚀 TÓM TẮT NHANH

### **MQTT Broker**
```
Host: c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud
Port: 8883 (TLS)
Username: android_app
Password: Danhsidoi123
```

### **Subscribe Topics** (Android nhận từ Pi)
```
iot_health/device/rpi_bp_001/vitals   # Kết quả đo (HR, SpO2, Temp, BP)
iot_health/device/rpi_bp_001/alerts   # Cảnh báo vượt ngưỡng
iot_health/device/rpi_bp_001/status   # Device online/offline
```

### **Publish Topic** (Android gửi lệnh tới Pi)
```
iot_health/patient/patient_001/commands  # Remote control
```

---

## 📊 MESSAGE EXAMPLES

### 1. VITALS (Kết quả đo)
```json
{
  "measurements": {
    "heart_rate": {"value": 78, "unit": "bpm"},
    "spo2": {"value": 97, "unit": "%"},
    "temperature": {"object_temp": 36.7, "unit": "celsius"},
    "blood_pressure": {"systolic": 120, "diastolic": 80, "unit": "mmHg"}
  }
}
```

### 2. ALERTS (Cảnh báo)
```json
{
  "alert_type": "high_heart_rate",
  "severity": "high",
  "current_measurement": {"heart_rate": 125},
  "thresholds": {"min": 60, "max": 100}
}
```

### 3. STATUS (Trạng thái device)
```json
{
  "online": true,
  "sensors": {
    "max30102": "ready",
    "mlx90614": "ready",
    "hx710b": "ready"
  }
}
```

### 4. COMMANDS (Điều khiển từ xa)
```json
{
  "command": "start_measurement",
  "parameters": {"measurement_type": "blood_pressure"}
}
```

---

## 🔧 ANDROID CODE TEMPLATES

### **Dependencies** (build.gradle.kts)
```kotlin
implementation("org.eclipse.paho:org.eclipse.paho.client.mqttv3:1.2.5")
implementation("org.eclipse.paho:org.eclipse.paho.android.service:1.1.1")
implementation("com.google.code.gson:gson:2.10.1")
```

### **Connect to Broker**
```kotlin
val client = MqttAndroidClient(context, 
    "ssl://c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud:8883",
    "android_${UUID.randomUUID()}")

val options = MqttConnectOptions().apply {
    userName = "android_app"
    password = "Danhsidoi123".toCharArray()
    isAutomaticReconnect = true
}

client.connect(options, null, object : IMqttActionListener {
    override fun onSuccess(token: IMqttToken?) {
        client.subscribe("iot_health/device/rpi_bp_001/#", 1)
    }
})
```

### **Receive Messages**
```kotlin
client.setCallback(object : MqttCallback {
    override fun messageArrived(topic: String, message: MqttMessage) {
        val json = String(message.payload)
        
        when {
            topic.contains("vitals") -> handleVitals(json)
            topic.contains("alerts") -> handleAlert(json)
            topic.contains("status") -> handleStatus(json)
        }
    }
})
```

### **Send Command**
```kotlin
val command = JSONObject().apply {
    put("command", "start_measurement")
    put("parameters", JSONObject().put("measurement_type", "heart_rate"))
}

client.publish(
    "iot_health/patient/patient_001/commands",
    command.toString().toByteArray(),
    2, // QoS
    false
)
```

---

## ✅ TESTING

### **1. Monitor Messages (Terminal)**
```bash
cd /home/pi/Desktop/IoT_health
source .venv/bin/activate
python scripts/mqtt_monitor.py
```

### **2. Test Publishing**
```bash
python scripts/test_mqtt_simple.py
```

### **3. MQTT Explorer (GUI)**
- Download: https://mqtt-explorer.com/
- Connect với credentials trên
- Subscribe: `iot_health/#`

---

## 📝 MESSAGE FREQUENCY

- **Vitals**: Khi đo xong (~30-60s per measurement)
- **Alerts**: Khi vượt ngưỡng (max 1/hour per type)
- **Status**: Mỗi 5 phút (heartbeat)
- **Commands**: Instant response

---

## 🎨 UI DESIGN SUGGESTIONS

### **Dashboard Cards**
```
┌─────────────────────────────────┐
│ 🫀 Heart Rate                   │
│ 78 BPM                          │
│ Quality: ●●●●○ (89%)            │
│ 2 minutes ago                   │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ 🩸 SpO₂                         │
│ 97%                             │
│ Normal                          │
│ 2 minutes ago                   │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ 🌡️ Temperature                  │
│ 36.7°C                          │
│ Normal                          │
│ 5 minutes ago                   │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ 💉 Blood Pressure               │
│ 120/80 mmHg                     │
│ MAP: 93                         │
│ 10 minutes ago                  │
└─────────────────────────────────┘
```

### **Alert Notifications**
```
⚠️ HIGH ALERT
Nhịp tim cao: 125 BPM
Ngưỡng: 60-100 BPM
5 phút trước

[Xem chi tiết] [Đã xem]
```

### **Device Status Indicator**
```
🟢 Device Online
📡 All sensors ready
🔋 85%
📶 WiFi: -55 dBm
```

---

## 🐛 COMMON ISSUES

### **Không nhận messages**
✅ Check: `client.isConnected()` → phải là `true`
✅ Check: Subscriptions successful
✅ Enable logs: `MqttAndroidClient.setTraceEnabled(true)`

### **Connection drops**
✅ Set `isAutomaticReconnect = true`
✅ Check WiFi stability
✅ Monitor keepalive (60s default)

### **Battery drain**
✅ Use foreground service
✅ Debounce UI updates (max 1/second)
✅ Cache to Room DB

---

## 📚 FULL DOCUMENTATION

Chi tiết đầy đủ: `/home/pi/Desktop/IoT_health/docs/MOBILE_APP_MQTT_GUIDE.md`

---

**✅ Ready to integrate!**
