# 📱 MQTT Integration Summary for Mobile App

## 🎯 Overview

Hệ thống IoT Health đã được tích hợp đầy đủ MQTT real-time communication. Raspberry Pi device sẽ publish messages lên HiveMQ Cloud broker, Android app subscribe để nhận data real-time.

---

## 🔗 **MQTT Broker Configuration**

```yaml
Broker: c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud
Port: 8883 (TLS/SSL) | 8884 (WebSocket for web dashboard)
Protocol: MQTT v3.1.1
Region: Singapore (low latency for Vietnam)

Authentication:
  - Pi Device Username: rpi_bp_001
  - Android App Username: android_app
  - Password: Danhsidoi123 (same for all clients)
  
TLS: Required (Let's Encrypt CA managed by HiveMQ Cloud)
Connection String: ssl://c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud:8883
```

---

## 🔑 **Device Pairing & Discovery**

### **QR Code Pairing Flow**

1. **Pi Device generates QR code** containing:
```json
{
  "device_id": "rpi_bp_001",
  "pairing_code": "ABC123XY",
  "device_type": "blood_pressure_monitor",
  "mqtt_broker": "c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud"
}
```

2. **Android App scans QR** → Extract pairing_code

3. **Verify pairing** with MySQL REST API:
```http
POST https://your-api-endpoint.com/api/devices/pair
Content-Type: application/json

{
  "pairing_code": "ABC123XY",
  "user_id": "user123",
  "device_nickname": "Phòng khách nhà bà"
}
```

4. **Response**:
```json
{
  "success": true,
  "device": {
    "device_id": "rpi_bp_001",
    "device_name": "Living Room Health Monitor",
    "pairing_code": "ABC123XY",
    "mqtt_topics": {
      "vitals": "iot_health/device/rpi_bp_001/vitals",
      "alerts": "iot_health/device/rpi_bp_001/alerts",
      "status": "iot_health/device/rpi_bp_001/status"
    }
  }
}
```

5. **Android App** subscribes to MQTT topics for this device

### **Device Discovery (Alternative)**

For multiple devices, Android app can:
- Query MySQL API for all paired devices: `GET /api/users/{user_id}/devices`
- Subscribe to all device topics using wildcard: `iot_health/device/+/vitals`

---

## 📡 **MQTT Topics Structure**

### **1. Device Topics** (Pi → Mobile)

```
iot_health/device/{device_id}/
├── vitals          # Measurement data (HR, SpO2, Temp, BP)
├── alerts          # Health alerts (threshold violations)
└── status          # Device online/offline, sensor status
```

### **2. Patient Topics** (Mobile → Pi)

```
iot_health/patient/{patient_id}/
└── commands        # Remote commands từ mobile app
```

---

## 📊 **Message Payloads**

### **A. Vitals Message** (QoS 1)

**Topic**: `iot_health/device/rpi_bp_001/vitals`

**Payload Example**:
```json
{
  "timestamp": 1732185600.123,
  "device_id": "rpi_bp_001",
  "patient_id": "patient_001",
  "measurements": {
    "heart_rate": {
      "value": 78,
      "unit": "bpm",
      "valid": true,
      "confidence": 0.95,
      "source": "MAX30102",
      "raw_metrics": {
        "ir_quality": 89.5,
        "peak_count": 18,
        "sampling_rate": 100.0,
        "measurement_duration": 24.5,
        "cv_coefficient": 1.8
      }
    },
    "spo2": {
      "value": 97,
      "unit": "%",
      "valid": true,
      "confidence": 0.92,
      "source": "MAX30102",
      "raw_metrics": {
        "r_value": 0.45,
        "ac_red": 5000,
        "dc_red": 120000,
        "ac_ir": 8000,
        "dc_ir": 150000
      }
    },
    "temperature": {
      "object_temp": 36.7,
      "ambient_temp": 25.2,
      "unit": "celsius",
      "valid": true,
      "source": "MLX90614",
      "raw_metrics": {
        "read_count": 25,
        "std_deviation": 0.15
      }
    },
    "blood_pressure": {
      "systolic": 120,
      "diastolic": 80,
      "map": 93,
      "unit": "mmHg",
      "valid": true,
      "quality": "good",
      "confidence": 0.85,
      "source": "HX710B",
      "raw_metrics": {
        "pulse_pressure": 40,
        "heart_rate_bp": 75.0,
        "max_pressure_reached": 165,
        "deflate_rate_actual": 3.0,
        "oscillation_amplitude": 12.5,
        "envelope_quality": 0.88
      }
    }
  },
  "session": {
    "session_id": "session_1732185600",
    "measurement_sequence": 1,
    "total_duration": 30.5,
    "user_triggered": true
  },
  "device_context": {
    "gui_version": "2.0.0",
    "measurement_mode": "manual",
    "screen_resolution": "480x320",
    "timestamp": 1732185600.123
  }
}
```

**Frequency**: Mỗi khi đo xong (~ 30-60 giây cho mỗi measurement)

---

### **B. Alert Message** (QoS 2)

**Topic**: `iot_health/device/rpi_bp_001/alerts`

**Payload Example**:
```json
{
  "timestamp": 1732185700.456,
  "device_id": "rpi_bp_001",
  "patient_id": "patient_001",
  "alert_type": "high_heart_rate",
  "severity": "high",
  "priority": 2,
  "current_measurement": {
    "heart_rate": 125,
    "timestamp": 1732185700.456
  },
  "thresholds": {
    "min": 60,
    "max": 100,
    "vital_sign": "heart_rate"
  },
  "trend": {
    "direction": "up",
    "rate": 5.0
  },
  "actions": {
    "notification_sent": true,
    "tts_played": true
  },
  "recommendations": [
    "Giám sát heart_rate",
    "Liên hệ bác sĩ nếu triệu chứng tiếp diễn"
  ],
  "metadata": {
    "source": "gui_measurement",
    "session_id": "session_1732185600"
  }
}
```

**Alert Types**:
- `high_heart_rate`, `low_heart_rate`
- `low_spo2`
- `high_temperature`, `low_temperature`
- `high_blood_pressure`, `low_blood_pressure`

**Severity Levels**:
- `info` (priority 3): Thông tin
- `warning` (priority 2): Cảnh báo
- `critical` (priority 1): Nguy hiểm, cần xử lý ngay

**Frequency**: Khi phát hiện vượt ngưỡng (1 alert/hour cho mỗi loại để tránh spam)

---

### **C. Status Message** (QoS 0, Retained)

**Topic**: `iot_health/device/rpi_bp_001/status`

**Payload Example**:
```json
{
  "timestamp": 1732185600.789,
  "device_id": "rpi_bp_001",
  "online": true,
  "battery": {
    "level": 85,
    "charging": false
  },
  "sensors": {
    "max30102": "ready",
    "mlx90614": "ready",
    "hx710b": "ready"
  },
  "actuators": {
    "pump": "idle",
    "valve": "closed"
  },
  "system": {
    "uptime": 3600,
    "memory_usage": 45.2,
    "cpu_usage": 30.5
  },
  "network": {
    "wifi_signal": -55,
    "mqtt_connected": true
  }
}
```

**Frequency**: 
- Khi app start/stop
- Mỗi 5 phút (heartbeat)
- Khi có thay đổi sensor status

**Retained**: Yes (để mobile app biết device status ngay khi connect)

---

### **D. Command Message** (QoS 2) - **Mobile → Pi**

**Topic**: `iot_health/patient/patient_001/commands`

**Payload Example**:
```json
{
  "command_id": "cmd_1732185900",
  "timestamp": 1732185900.123,
  "issuer": "android_app",
  "command": "start_measurement",
  "parameters": {
    "measurement_type": "blood_pressure",
    "patient_id": "patient_001"
  },
  "expires_at": 1732186200
}
```

**Available Commands**:
- `start_measurement`: Bắt đầu đo (params: `measurement_type`)
- `stop_measurement`: Dừng đo đang chạy
- `calibrate_sensor`: Calibrate sensor (params: `sensor_type`)
- `emergency_deflate`: Xả khẩn cấp BP cuff
- `update_thresholds`: Cập nhật ngưỡng cảnh báo

---

## 🔐 **Security & Authentication**

### **Credentials for Mobile App**

```yaml
# For Android App
Username: android_app
Password: Danhsidoi123
Client ID: android_app_{unique_device_id}

# ACL Permissions
Subscribe:
  - iot_health/device/+/vitals
  - iot_health/device/+/alerts
  - iot_health/device/+/status
  
Publish:
  - iot_health/patient/+/commands
```

### **TLS Configuration**

```java
// Android - MqttConnectOptions
val options = MqttConnectOptions().apply {
    isCleanSession = false
    userName = "android_app"
    password = "Danhsidoi123".toCharArray()
    
    // TLS Setup
    val socketFactory = SSLContext.getInstance("TLSv1.2").apply {
        init(null, null, null)
    }.socketFactory
    this.socketFactory = socketFactory
    
    // Keepalive & Reconnect
    keepAliveInterval = 60
    isAutomaticReconnect = true
    connectionTimeout = 30
}
```

---

## 🗄️ **MySQL Cloud Integration**

### **Database Schema**

```sql
-- Devices table (cloud)
CREATE TABLE devices (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    device_id VARCHAR(50) UNIQUE NOT NULL,
    device_name VARCHAR(100) NOT NULL,
    device_type VARCHAR(50) DEFAULT 'blood_pressure_monitor',
    location VARCHAR(200),
    pairing_code VARCHAR(32) UNIQUE,
    firmware_version VARCHAR(20),
    os_version VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    last_seen DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Device ownership (multi-user access)
CREATE TABLE device_ownership (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id VARCHAR(100) NOT NULL,
    device_id VARCHAR(50) NOT NULL,
    role VARCHAR(20) DEFAULT 'owner',
    nickname VARCHAR(100),
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices(device_id)
);

-- Health records
CREATE TABLE health_records (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    patient_id VARCHAR(50) NOT NULL,
    device_id VARCHAR(50) NOT NULL,
    timestamp DATETIME NOT NULL,
    heart_rate INT,
    spo2 INT,
    temperature FLOAT,
    systolic_bp INT,
    diastolic_bp INT,
    mean_arterial_pressure FLOAT,
    sensor_data JSON,
    synced_at DATETIME,
    FOREIGN KEY (device_id) REFERENCES devices(device_id)
);

-- Alerts
CREATE TABLE alerts (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    patient_id VARCHAR(50) NOT NULL,
    device_id VARCHAR(50) NOT NULL,
    health_record_id BIGINT,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    acknowledged BOOLEAN DEFAULT FALSE,
    synced_at DATETIME,
    FOREIGN KEY (device_id) REFERENCES devices(device_id)
);
```

### **REST API Endpoints**

#### **1. Device Pairing**
```http
POST /api/devices/pair
Body: { "pairing_code": "ABC123XY", "user_id": "user123", "device_nickname": "..." }
Response: { "success": true, "device": {...} }
```

#### **2. Get User Devices**
```http
GET /api/users/{user_id}/devices
Response: [
  {
    "device_id": "rpi_bp_001",
    "device_name": "Phòng khách nhà bà",
    "device_type": "blood_pressure_monitor",
    "is_active": true,
    "last_seen": "2025-11-22T10:30:00Z"
  }
]
```

#### **3. Get Health Records**
```http
GET /api/devices/{device_id}/health_records?limit=100&offset=0
Response: {
  "total": 250,
  "records": [...]
}
```

#### **4. Update Device Settings**
```http
PATCH /api/devices/{device_id}
Body: { "device_name": "New Name", "location": "New Location" }
Response: { "success": true }
```

### **Sync Strategy (Pi ↔ Cloud)**

**Pi Device Behavior:**
- **INSERT** lần đầu: Push tất cả fields (device_id, device_name, pairing_code, firmware_version, os_version, location)
- **UPDATE** sau đó: Chỉ update technical fields (firmware_version, os_version, last_seen, ip_address)
- **NEVER overwrite**: device_name, location (do Android app quản lý)

**Android App Behavior:**
- **After pairing**: Update device_name và location qua REST API
- **Pi respects**: Không ghi đè device_name/location đã set từ Android

---

## 📱 **Android Implementation Guide**

### **Project Structure**
```
app/src/main/java/com/yourcompany/iothealth/
├── data/
│   ├── local/
│   │   ├── dao/
│   │   │   ├── VitalsDao.kt
│   │   │   ├── AlertsDao.kt
│   │   │   └── DevicesDao.kt
│   │   ├── entities/
│   │   │   ├── VitalsEntity.kt
│   │   │   ├── AlertEntity.kt
│   │   │   └── DeviceEntity.kt
│   │   └── HealthDatabase.kt
│   ├── remote/
│   │   ├── api/
│   │   │   ├── DeviceApi.kt
│   │   │   └── HealthRecordsApi.kt
│   │   ├── models/
│   │   │   ├── VitalsPayload.kt
│   │   │   ├── AlertPayload.kt
│   │   │   └── DeviceStatusPayload.kt
│   │   └── mqtt/
│   │       ├── MqttManager.kt
│   │       └── MqttMessageHandler.kt
│   └── repository/
│       ├── DeviceRepository.kt
│       └── HealthDataRepository.kt
├── di/
│   └── AppModule.kt (Hilt modules)
├── ui/
│   ├── screens/
│   │   ├── dashboard/
│   │   │   ├── DashboardScreen.kt
│   │   │   └── DashboardViewModel.kt
│   │   ├── pairing/
│   │   │   ├── QRScannerScreen.kt
│   │   │   └── PairingViewModel.kt
│   │   ├── history/
│   │   │   ├── HistoryScreen.kt
│   │   │   └── HistoryViewModel.kt
│   │   └── alerts/
│   │       ├── AlertsScreen.kt
│   │       └── AlertsViewModel.kt
│   └── components/
│       ├── VitalsCard.kt
│       ├── AlertItem.kt
│       └── DeviceStatusIndicator.kt
└── utils/
    ├── NotificationHelper.kt
    └── DateTimeUtils.kt
```

### **1. Dependencies** (build.gradle.kts)

```kotlin
dependencies {
    // Paho MQTT Client
    implementation("org.eclipse.paho:org.eclipse.paho.client.mqttv3:1.2.5")
    implementation("org.eclipse.paho:org.eclipse.paho.android.service:1.1.1")
    
    // Jetpack Compose (Modern Android UI)
    implementation(platform("androidx.compose:compose-bom:2024.01.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.activity:activity-compose:1.8.2")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.7.0")
    debugImplementation("androidx.compose.ui:ui-tooling")
    
    // Navigation
    implementation("androidx.navigation:navigation-compose:2.7.6")
    
    // Hilt Dependency Injection
    implementation("com.google.dagger:hilt-android:2.48")
    kapt("com.google.dagger:hilt-compiler:2.48")
    implementation("androidx.hilt:hilt-navigation-compose:1.1.0")
    
    // Retrofit (REST API)
    implementation("com.squareup.retrofit2:retrofit:2.9.0")
    implementation("com.squareup.retrofit2:converter-gson:2.9.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
    
    // JSON Parsing
    implementation("com.google.code.gson:gson:2.10.1")
    
    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.7.3")
    
    // Room Database (offline cache)
    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.room:room-ktx:2.6.1")
    kapt("androidx.room:room-compiler:2.6.1")
    
    // DataStore (for settings)
    implementation("androidx.datastore:datastore-preferences:1.0.0")
    
    // WorkManager (background sync)
    implementation("androidx.work:work-runtime-ktx:2.9.0")
    
    // Charts (for vitals visualization)
    implementation("com.patrykandpatrick.vico:compose:1.13.1")
    implementation("com.patrykandpatrick.vico:compose-m3:1.13.1")
    
    // QR Code Scanner
    implementation("com.google.mlkit:barcode-scanning:17.2.0")
    implementation("androidx.camera:camera-camera2:1.3.1")
    implementation("androidx.camera:camera-lifecycle:1.3.1")
    implementation("androidx.camera:camera-view:1.3.1")
    
    // Coil (Image loading)
    implementation("io.coil-kt:coil-compose:2.5.0")
    
    // Testing
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.7.3")
    testImplementation("app.cash.turbine:turbine:1.0.0")
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
}
```

### **Gradle Plugins** (build.gradle.kts - app level)
```kotlin
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.dagger.hilt.android")
    id("kotlin-kapt")
    id("kotlin-parcelize")
}
```

### **2. Room Database** (Local Cache)

#### **HealthDatabase.kt**
```kotlin
@Database(
    entities = [
        VitalsEntity::class,
        AlertEntity::class,
        DeviceEntity::class
    ],
    version = 1,
    exportSchema = false
)
@TypeConverters(Converters::class)
abstract class HealthDatabase : RoomDatabase() {
    abstract fun vitalsDao(): VitalsDao
    abstract fun alertsDao(): AlertsDao
    abstract fun devicesDao(): DevicesDao
}
```

#### **VitalsEntity.kt**
```kotlin
@Entity(tableName = "vitals")
data class VitalsEntity(
    @PrimaryKey val id: String = UUID.randomUUID().toString(),
    val timestamp: Long,
    val deviceId: String,
    val patientId: String,
    val heartRate: Int?,
    val spo2: Int?,
    val temperature: Float?,
    val systolicBp: Int?,
    val diastolicBp: Int?,
    val map: Float?,
    val sensorData: String?, // JSON string
    val syncedToCloud: Boolean = false,
    val createdAt: Long = System.currentTimeMillis()
)

@Dao
interface VitalsDao {
    @Query("SELECT * FROM vitals WHERE deviceId = :deviceId ORDER BY timestamp DESC LIMIT :limit")
    fun getLatestVitals(deviceId: String, limit: Int = 100): Flow<List<VitalsEntity>>
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(vitals: VitalsEntity)
    
    @Query("DELETE FROM vitals WHERE timestamp < :cutoffTime")
    suspend fun deleteOldVitals(cutoffTime: Long)
}
```

#### **AlertEntity.kt**
```kotlin
@Entity(tableName = "alerts")
data class AlertEntity(
    @PrimaryKey val id: String = UUID.randomUUID().toString(),
    val timestamp: Long,
    val deviceId: String,
    val patientId: String,
    val alertType: String,
    val severity: String,
    val priority: Int,
    val message: String,
    val acknowledged: Boolean = false,
    val acknowledgedAt: Long? = null,
    val createdAt: Long = System.currentTimeMillis()
)

@Dao
interface AlertsDao {
    @Query("SELECT * FROM alerts WHERE deviceId = :deviceId ORDER BY timestamp DESC")
    fun getAlerts(deviceId: String): Flow<List<AlertEntity>>
    
    @Query("SELECT * FROM alerts WHERE acknowledged = 0 ORDER BY priority ASC, timestamp DESC")
    fun getUnacknowledgedAlerts(): Flow<List<AlertEntity>>
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(alert: AlertEntity)
    
    @Update
    suspend fun update(alert: AlertEntity)
}
```

#### **DeviceEntity.kt**
```kotlin
@Entity(tableName = "devices")
data class DeviceEntity(
    @PrimaryKey val deviceId: String,
    val deviceName: String,
    val deviceType: String,
    val location: String?,
    val pairingCode: String?,
    val isActive: Boolean,
    val lastSeen: Long?,
    val isPaired: Boolean = false,
    val createdAt: Long = System.currentTimeMillis()
)

@Dao
interface DevicesDao {
    @Query("SELECT * FROM devices WHERE isPaired = 1")
    fun getPairedDevices(): Flow<List<DeviceEntity>>
    
    @Query("SELECT * FROM devices WHERE deviceId = :deviceId")
    suspend fun getDevice(deviceId: String): DeviceEntity?
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(device: DeviceEntity)
    
    @Update
    suspend fun update(device: DeviceEntity)
}
```

### **3. Retrofit API Interfaces**

#### **DeviceApi.kt**
```kotlin
interface DeviceApi {
    @POST("api/devices/pair")
    suspend fun pairDevice(@Body request: PairDeviceRequest): PairDeviceResponse
    
    @GET("api/users/{userId}/devices")
    suspend fun getUserDevices(@Path("userId") userId: String): List<DeviceResponse>
    
    @PATCH("api/devices/{deviceId}")
    suspend fun updateDevice(
        @Path("deviceId") deviceId: String,
        @Body request: UpdateDeviceRequest
    ): DeviceResponse
    
    @GET("api/devices/{deviceId}/health_records")
    suspend fun getHealthRecords(
        @Path("deviceId") deviceId: String,
        @Query("limit") limit: Int = 100,
        @Query("offset") offset: Int = 0
    ): HealthRecordsResponse
}

data class PairDeviceRequest(
    val pairingCode: String,
    val userId: String,
    val deviceNickname: String?
)

data class PairDeviceResponse(
    val success: Boolean,
    val device: DeviceResponse,
    val mqttTopics: MqttTopics
)

data class MqttTopics(
    val vitals: String,
    val alerts: String,
    val status: String
)
```

### **4. MqttManager.kt** (Singleton with Hilt)

```kotlin
@Singleton
class MqttManager @Inject constructor(
    @ApplicationContext private val context: Context,
    private val gson: Gson
) {
    
    private val mqttClient: MqttAndroidClient
    private val gson = Gson()
    
    // StateFlows for real-time updates
    private val _vitalsFlow = MutableStateFlow<VitalsPayload?>(null)
    val vitalsFlow: StateFlow<VitalsPayload?> = _vitalsFlow.asStateFlow()
    
    private val _alertsFlow = MutableStateFlow<AlertPayload?>(null)
    val alertsFlow: StateFlow<AlertPayload?> = _alertsFlow.asStateFlow()
    
    private val _statusFlow = MutableStateFlow<DeviceStatusPayload?>(null)
    val statusFlow: StateFlow<DeviceStatusPayload?> = _statusFlow.asStateFlow()
    
    init {
        mqttClient = MqttAndroidClient(
            context.applicationContext,
            "ssl://c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud:8883",
            "android_app_${UUID.randomUUID()}"
        )
        
        mqttClient.setCallback(object : MqttCallback {
            override fun messageArrived(topic: String, message: MqttMessage) {
                handleMessage(topic, String(message.payload))
            }
            
            override fun connectionLost(cause: Throwable?) {
                Log.w(TAG, "Connection lost", cause)
                // Auto-reconnect handled by MqttConnectOptions
            }
            
            override fun deliveryComplete(token: IMqttDeliveryToken?) {
                Log.d(TAG, "Delivery complete")
            }
        })
    }
    
    fun connect(deviceId: String, patientId: String) {
        val options = MqttConnectOptions().apply {
            isCleanSession = false
            userName = "android_app"
            password = "Danhsidoi123".toCharArray()
            keepAliveInterval = 60
            isAutomaticReconnect = true
            connectionTimeout = 30
            
            // TLS
            val socketFactory = SSLContext.getInstance("TLSv1.2").apply {
                init(null, null, null)
            }.socketFactory
            this.socketFactory = socketFactory
        }
        
        mqttClient.connect(options, null, object : IMqttActionListener {
            override fun onSuccess(asyncActionToken: IMqttToken?) {
                Log.i(TAG, "Connected to MQTT broker")
                subscribeToDevice(deviceId, patientId)
            }
            
            override fun onFailure(asyncActionToken: IMqttToken?, exception: Throwable?) {
                Log.e(TAG, "Failed to connect", exception)
            }
        })
    }
    
    private fun subscribeToDevice(deviceId: String, patientId: String) {
        val topics = arrayOf(
            "iot_health/device/$deviceId/vitals",
            "iot_health/device/$deviceId/alerts",
            "iot_health/device/$deviceId/status"
        )
        val qos = intArrayOf(1, 2, 0)
        
        mqttClient.subscribe(topics, qos)
    }
    
    private fun handleMessage(topic: String, payload: String) {
        try {
            when {
                topic.contains("/vitals") -> {
                    val vitals = gson.fromJson(payload, VitalsPayload::class.java)
                    _vitalsFlow.value = vitals
                }
                topic.contains("/alerts") -> {
                    val alert = gson.fromJson(payload, AlertPayload::class.java)
                    _alertsFlow.value = alert
                    showCriticalAlertNotification(alert)
                }
                topic.contains("/status") -> {
                    val status = gson.fromJson(payload, DeviceStatusPayload::class.java)
                    _statusFlow.value = status
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error parsing message", e)
        }
    }
    
    fun publishCommand(command: String, parameters: Map<String, Any>) {
        val payload = CommandPayload(
            commandId = "cmd_${System.currentTimeMillis()}",
            timestamp = System.currentTimeMillis() / 1000.0,
            issuer = "android_app",
            command = command,
            parameters = parameters
        )
        
        val topic = "iot_health/patient/patient_001/commands"
        val message = MqttMessage(gson.toJson(payload).toByteArray())
        message.qos = 2
        
        mqttClient.publish(topic, message)
    }
    
    private fun showCriticalAlertNotification(alert: AlertPayload) {
        if (alert.severity == "critical") {
            // Show push notification
            // Play alert sound
        }
    }
    
    fun disconnect() {
        try {
            mqttClient.disconnect()
            Log.i(TAG, "Disconnected from MQTT broker")
        } catch (e: Exception) {
            Log.e(TAG, "Error disconnecting", e)
        }
    }
    
    companion object {
        private const val TAG = "MqttManager"
        private const val BROKER_URL = "ssl://c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud:8883"
        private const val USERNAME = "android_app"
        private const val PASSWORD = "Danhsidoi123"
    }
}

// Hilt Module
@Module
@InstallIn(SingletonComponent::class)
object MqttModule {
    @Provides
    @Singleton
    fun provideGson(): Gson = GsonBuilder()
        .setDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'")
        .create()
    
    @Provides
    @Singleton
    fun provideMqttManager(
        @ApplicationContext context: Context,
        gson: Gson
    ): MqttManager = MqttManager(context, gson)
}
```

### **5. Repository Pattern**

#### **DeviceRepository.kt**
```kotlin
@Singleton
class DeviceRepository @Inject constructor(
    private val deviceApi: DeviceApi,
    private val devicesDao: DevicesDao,
    private val mqttManager: MqttManager
) {
    fun getPairedDevices(): Flow<List<DeviceEntity>> = devicesDao.getPairedDevices()
    
    suspend fun pairDevice(
        pairingCode: String,
        userId: String,
        deviceNickname: String?
    ): Result<DeviceEntity> {
        return try {
            val response = deviceApi.pairDevice(
                PairDeviceRequest(pairingCode, userId, deviceNickname)
            )
            
            val device = DeviceEntity(
                deviceId = response.device.deviceId,
                deviceName = deviceNickname ?: response.device.deviceName,
                deviceType = response.device.deviceType,
                location = response.device.location,
                pairingCode = pairingCode,
                isActive = true,
                lastSeen = null,
                isPaired = true
            )
            
            devicesDao.insert(device)
            
            // Subscribe to MQTT topics
            mqttManager.subscribeToDevice(device.deviceId, "patient_001")
            
            Result.success(device)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    suspend fun updateDeviceSettings(
        deviceId: String,
        deviceName: String?,
        location: String?
    ): Result<Unit> {
        return try {
            deviceApi.updateDevice(
                deviceId,
                UpdateDeviceRequest(deviceName, location)
            )
            
            val device = devicesDao.getDevice(deviceId)
            device?.let {
                devicesDao.update(
                    it.copy(
                        deviceName = deviceName ?: it.deviceName,
                        location = location ?: it.location
                    )
                )
            }
            
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
```

#### **HealthDataRepository.kt**
```kotlin
@Singleton
class HealthDataRepository @Inject constructor(
    private val vitalsDao: VitalsDao,
    private val alertsDao: AlertsDao,
    private val mqttManager: MqttManager
) {
    fun getLatestVitals(deviceId: String): Flow<List<VitalsEntity>> {
        return vitalsDao.getLatestVitals(deviceId)
    }
    
    fun getUnacknowledgedAlerts(): Flow<List<AlertEntity>> {
        return alertsDao.getUnacknowledgedAlerts()
    }
    
    // Observe MQTT messages and cache to database
    fun observeMqttVitals(): Flow<VitalsPayload?> {
        return mqttManager.vitalsFlow
            .onEach { vitals ->
                vitals?.let { cacheVitalsToDatabase(it) }
            }
    }
    
    private suspend fun cacheVitalsToDatabase(vitals: VitalsPayload) {
        val entity = VitalsEntity(
            timestamp = (vitals.timestamp * 1000).toLong(),
            deviceId = vitals.device_id,
            patientId = vitals.patient_id,
            heartRate = vitals.measurements.heart_rate?.value,
            spo2 = vitals.measurements.spo2?.value,
            temperature = vitals.measurements.temperature?.object_temp,
            systolicBp = vitals.measurements.blood_pressure?.systolic,
            diastolicBp = vitals.measurements.blood_pressure?.diastolic,
            map = vitals.measurements.blood_pressure?.map,
            sensorData = Gson().toJson(vitals),
            syncedToCloud = false
        )
        vitalsDao.insert(entity)
    }
    
    suspend fun acknowledgeAlert(alertId: String) {
        val alert = alertsDao.getAlerts("").first().find { it.id == alertId }
        alert?.let {
            alertsDao.update(
                it.copy(
                    acknowledged = true,
                    acknowledgedAt = System.currentTimeMillis()
                )
            )
        }
    }
}
```

### **6. Data Models** (Kotlin Data Classes)

```kotlin
data class VitalsPayload(
    val timestamp: Double,
    val device_id: String,
    val patient_id: String,
    val measurements: Measurements,
    val session: Session,
    val device_context: Map<String, Any>
)

data class Measurements(
    val heart_rate: Measurement?,
    val spo2: Measurement?,
    val temperature: TemperatureMeasurement?,
    val blood_pressure: BloodPressureMeasurement?
)

data class Measurement(
    val value: Int,
    val unit: String,
    val valid: Boolean,
    val confidence: Double,
    val source: String,
    val raw_metrics: Map<String, Any>
)

data class AlertPayload(
    val timestamp: Double,
    val device_id: String,
    val patient_id: String,
    val alert_type: String,
    val severity: String,
    val priority: Int,
    val current_measurement: Map<String, Any>,
    val thresholds: Map<String, Any>,
    val message: String?
)

data class DeviceStatusPayload(
    val timestamp: Double,
    val device_id: String,
    val online: Boolean,
    val sensors: Map<String, String>,
    val battery: Map<String, Any>
)
```

### **7. ViewModels**

#### **DashboardViewModel.kt**
```kotlin
@HiltViewModel
class DashboardViewModel @Inject constructor(
    private val deviceRepository: DeviceRepository,
    private val healthDataRepository: HealthDataRepository,
    private val mqttManager: MqttManager
) : ViewModel() {
    
    val pairedDevices = deviceRepository.getPairedDevices()
        .stateIn(viewModelScope, SharingStarted.Lazily, emptyList())
    
    private val _selectedDevice = MutableStateFlow<DeviceEntity?>(null)
    val selectedDevice: StateFlow<DeviceEntity?> = _selectedDevice.asStateFlow()
    
    val latestVitals = selectedDevice
        .flatMapLatest { device ->
            device?.let { 
                healthDataRepository.getLatestVitals(it.deviceId).take(1)
            } ?: flowOf(emptyList())
        }
        .stateIn(viewModelScope, SharingStarted.Lazily, emptyList())
    
    val liveVitals = healthDataRepository.observeMqttVitals()
        .debounce(1000) // Max 1 update/second
        .stateIn(viewModelScope, SharingStarted.Lazily, null)
    
    val deviceStatus = mqttManager.statusFlow
        .stateIn(viewModelScope, SharingStarted.Lazily, null)
    
    val unacknowledgedAlerts = healthDataRepository.getUnacknowledgedAlerts()
        .stateIn(viewModelScope, SharingStarted.Lazily, emptyList())
    
    fun selectDevice(device: DeviceEntity) {
        _selectedDevice.value = device
    }
    
    fun startMeasurement(type: String) {
        mqttManager.publishCommand(
            command = "start_measurement",
            parameters = mapOf(
                "measurement_type" to type,
                "patient_id" to "patient_001"
            )
        )
    }
    
    fun acknowledgeAlert(alertId: String) {
        viewModelScope.launch {
            healthDataRepository.acknowledgeAlert(alertId)
        }
    }
}
```

#### **PairingViewModel.kt**
```kotlin
@HiltViewModel
class PairingViewModel @Inject constructor(
    private val deviceRepository: DeviceRepository
) : ViewModel() {
    
    private val _pairingState = MutableStateFlow<PairingState>(PairingState.Idle)
    val pairingState: StateFlow<PairingState> = _pairingState.asStateFlow()
    
    fun pairDevice(pairingCode: String, userId: String, deviceNickname: String?) {
        viewModelScope.launch {
            _pairingState.value = PairingState.Pairing
            
            val result = deviceRepository.pairDevice(pairingCode, userId, deviceNickname)
            
            _pairingState.value = if (result.isSuccess) {
                PairingState.Success(result.getOrNull()!!)
            } else {
                PairingState.Error(result.exceptionOrNull()?.message ?: "Pairing failed")
            }
        }
    }
}

sealed class PairingState {
    object Idle : PairingState()
    object Pairing : PairingState()
    data class Success(val device: DeviceEntity) : PairingState()
    data class Error(val message: String) : PairingState()
}
```

### **8. UI Screens** (Jetpack Compose)

#### **QRScannerScreen.kt**
```kotlin
@Composable
fun QRScannerScreen(
    viewModel: PairingViewModel = hiltViewModel(),
    onPairingSuccess: (DeviceEntity) -> Unit
) {
    val pairingState by viewModel.pairingState.collectAsState()
    var scannedCode by remember { mutableStateOf<String?>(null) }
    var deviceNickname by remember { mutableStateOf("") }
    
    Column(modifier = Modifier.fillMaxSize()) {
        // Camera Preview for QR scanning
        CameraPreview(
            onQRCodeScanned = { code ->
                scannedCode = code
            }
        )
        
        // Pairing Form
        scannedCode?.let { code ->
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp)
            ) {
                Text("Pairing Code: $code", style = MaterialTheme.typography.bodyLarge)
                
                OutlinedTextField(
                    value = deviceNickname,
                    onValueChange = { deviceNickname = it },
                    label = { Text("Device Name (optional)") },
                    modifier = Modifier.fillMaxWidth()
                )
                
                Spacer(modifier = Modifier.height(16.dp))
                
                Button(
                    onClick = {
                        viewModel.pairDevice(
                            pairingCode = code,
                            userId = "user123", // From auth
                            deviceNickname = deviceNickname.ifBlank { null }
                        )
                    },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text("Pair Device")
                }
            }
        }
        
        // Loading/Success/Error states
        when (val state = pairingState) {
            is PairingState.Pairing -> CircularProgressIndicator()
            is PairingState.Success -> {
                LaunchedEffect(state.device) {
                    onPairingSuccess(state.device)
                }
            }
            is PairingState.Error -> {
                Text("Error: ${state.message}", color = MaterialTheme.colorScheme.error)
            }
            else -> {}
        }
    }
}
```

#### **DashboardScreen.kt**
```kotlin
@Composable
fun DashboardScreen(viewModel: DashboardViewModel = hiltViewModel()) {
    val vitals by viewModel.latestVitals.collectAsState()
    val alerts by viewModel.latestAlerts.collectAsState()
    val deviceStatus by viewModel.deviceStatus.collectAsState()
    
    Column {
        // Device Status Card
        DeviceStatusCard(
            online = deviceStatus?.online ?: false,
            sensors = deviceStatus?.sensors ?: emptyMap()
        )
        
        // Vitals Cards
        vitals?.measurements?.let { measurements ->
            HeartRateCard(
                value = measurements.heart_rate?.value,
                quality = measurements.heart_rate?.raw_metrics?.get("ir_quality") as? Double
            )
            
            SpO2Card(value = measurements.spo2?.value)
            
            TemperatureCard(value = measurements.temperature?.object_temp)
            
            BloodPressureCard(
                systolic = measurements.blood_pressure?.systolic,
                diastolic = measurements.blood_pressure?.diastolic
            )
        }
        
        // Recent Alerts
        AlertsList(alerts = alerts)
    }
}
```

### **9. Background Sync with WorkManager**

```kotlin
@HiltWorker
class SyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val healthDataRepository: HealthDataRepository,
    private val deviceApi: DeviceApi
) : CoroutineWorker(context, params) {
    
    override suspend fun doWork(): Result {
        return try {
            // Sync unsynced vitals to cloud
            val unsyncedVitals = healthDataRepository.getUnsyncedVitals()
            unsyncedVitals.forEach { vitals ->
                deviceApi.uploadVitals(vitals.toUploadRequest())
                healthDataRepository.markAsSynced(vitals.id)
            }
            
            Result.success()
        } catch (e: Exception) {
            Log.e("SyncWorker", "Sync failed", e)
            Result.retry()
        }
    }
}

// Schedule periodic sync
class SyncScheduler @Inject constructor(
    @ApplicationContext private val context: Context
) {
    fun scheduleSyncWork() {
        val syncRequest = PeriodicWorkRequestBuilder<SyncWorker>(
            repeatInterval = 15,
            repeatIntervalTimeUnit = TimeUnit.MINUTES
        )
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build()
            )
            .build()
        
        WorkManager.getInstance(context)
            .enqueueUniquePeriodicWork(
                "health_data_sync",
                ExistingPeriodicWorkPolicy.KEEP,
                syncRequest
            )
    }
}
```

### **10. Notification Helper**

```kotlin
@Singleton
class NotificationHelper @Inject constructor(
    @ApplicationContext private val context: Context
) {
    private val notificationManager = context.getSystemService<NotificationManager>()!!
    
    init {
        createNotificationChannels()
    }
    
    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val criticalChannel = NotificationChannel(
                CRITICAL_CHANNEL_ID,
                "Critical Alerts",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Critical health alerts that require immediate attention"
                enableVibration(true)
                setSound(
                    RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM),
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ALARM)
                        .build()
                )
            }
            
            notificationManager.createNotificationChannel(criticalChannel)
        }
    }
    
    fun showCriticalAlert(alert: AlertPayload) {
        val notification = NotificationCompat.Builder(context, CRITICAL_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_alert)
            .setContentTitle("⚠️ Critical Health Alert")
            .setContentText(alert.message ?: "Critical alert detected")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setAutoCancel(true)
            .build()
        
        notificationManager.notify(alert.timestamp.toInt(), notification)
    }
    
    companion object {
        private const val CRITICAL_CHANNEL_ID = "critical_alerts"
    }
}
```

---

## 🔄 **Complete Implementation Checklist**

### **Phase 1: Project Setup** ✅
- [ ] Create Android project với Kotlin + Jetpack Compose
- [ ] Add all dependencies (Hilt, Retrofit, Room, Paho MQTT, etc.)
- [ ] Setup Hilt Application class
- [ ] Configure ProGuard rules cho Paho MQTT
- [ ] Add permissions trong AndroidManifest.xml:
  - `INTERNET`
  - `ACCESS_NETWORK_STATE`
  - `WAKE_LOCK`
  - `CAMERA` (for QR scanning)
  - `POST_NOTIFICATIONS` (Android 13+)

### **Phase 2: Data Layer** 📊
- [ ] Create Room database với 3 entities (Vitals, Alerts, Devices)
- [ ] Implement DAOs với Flow support
- [ ] Create Retrofit API interfaces
- [ ] Implement MqttManager với StateFlows
- [ ] Create Repository pattern cho data operations
- [ ] Add TypeConverters cho JSON serialization

### **Phase 3: MQTT Integration** 📡
- [ ] Implement MqttManager connection logic với TLS
- [ ] Handle message parsing cho vitals/alerts/status
- [ ] Implement auto-reconnect với exponential backoff
- [ ] Add message debouncing (1 UI update/second max)
- [ ] Implement command publishing
- [ ] Test MQTT connectivity với HiveMQ broker

### **Phase 4: UI Screens** 🎨
- [ ] QR Scanner Screen với CameraX
- [ ] Pairing Flow với ViewModel
- [ ] Dashboard Screen với device selection
- [ ] Vitals Display Cards (HR, SpO2, Temp, BP)
- [ ] Alerts Screen với priority sorting
- [ ] History Screen với pagination
- [ ] Settings Screen cho device management
- [ ] Navigation Graph với Jetpack Navigation

### **Phase 5: Background Services** ⚙️
- [ ] Implement WorkManager sync worker
- [ ] Create foreground service cho MQTT connection
- [ ] Add notification helper cho critical alerts
- [ ] Implement battery optimization exclusion request
- [ ] Handle doze mode với AlarmManager

### **Phase 6: Testing & Polish** ✨
- [ ] Unit tests cho ViewModels
- [ ] Integration tests cho MQTT flow
- [ ] UI tests cho Compose screens
- [ ] Test offline mode với Room cache
- [ ] Test reconnection scenarios
- [ ] Performance testing (memory, battery)
- [ ] Add error handling và user feedback

### **Phase 7: Production Ready** 🚀
- [ ] Configure signing keys
- [ ] Setup ProGuard rules
- [ ] Add crash reporting (Firebase Crashlytics)
- [ ] Add analytics (Firebase Analytics)
- [ ] Implement app update mechanism
- [ ] Create app icons và splash screen
- [ ] Write user documentation
- [ ] Prepare for Play Store submission

---

## 🧪 **Testing**

### **Monitor MQTT Messages (Python)**

```bash
cd /home/pi/Desktop/IoT_health
source .venv/bin/activate

# Subscribe to all messages
python scripts/mqtt_monitor.py

# Publish test messages
python scripts/test_mqtt_simple.py
```

### **Monitor with MQTT Explorer (GUI)**

1. Download: https://mqtt-explorer.com/
2. Connect:
   - Host: `c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud`
   - Port: `8883`
   - Protocol: `mqtts://`
   - Username: `android_app`
   - Password: `Danhsidoi123`
3. Subscribe: `iot_health/#`

---

## 📊 **Message Flow Diagram**

```
┌─────────────┐                     ┌──────────────┐                   ┌─────────────┐
│ Raspberry Pi│                     │ HiveMQ Cloud │                   │ Android App │
│   Device    │                     │   Broker     │                   │             │
└──────┬──────┘                     └──────┬───────┘                   └──────┬──────┘
       │                                   │                                  │
       │ 1. Connect (TLS)                  │                                  │
       │──────────────────────────────────>│                                  │
       │                                   │                                  │
       │                                   │  2. Connect (TLS)                │
       │                                   │<─────────────────────────────────│
       │                                   │                                  │
       │                                   │  3. Subscribe                    │
       │                                   │    vitals/alerts/status          │
       │                                   │<─────────────────────────────────│
       │                                   │                                  │
       │ 4. Publish Status (online)        │                                  │
       │──────────────────────────────────>│                                  │
       │                                   │                                  │
       │                                   │  5. Receive Status               │
       │                                   │─────────────────────────────────>│
       │                                   │                                  │
       │ [User đo heart rate trên Pi]      │                                  │
       │                                   │                                  │
       │ 6. Publish Vitals (HR/SpO2)       │                                  │
       │──────────────────────────────────>│                                  │
       │                                   │                                  │
       │                                   │  7. Receive Vitals               │
       │                                   │─────────────────────────────────>│
       │                                   │                                  │
       │                                   │     [App hiển thị real-time]     │
       │                                   │                                  │
       │ 8. Publish Alert (HR > 100)       │                                  │
       │──────────────────────────────────>│                                  │
       │                                   │                                  │
       │                                   │  9. Receive Alert                │
       │                                   │─────────────────────────────────>│
       │                                   │                                  │
       │                                   │     [App show notification]      │
       │                                   │                                  │
       │                                   │  10. Publish Command             │
       │                                   │    (start_measurement)           │
       │                                   │<─────────────────────────────────│
       │                                   │                                  │
       │ 11. Receive Command               │                                  │
       │<──────────────────────────────────│                                  │
       │                                   │                                  │
       │ [Pi bắt đầu đo BP]                │                                  │
       │                                   │                                  │
```

---

## ⚡ **Performance & Best Practices**

### **Message Rate Limits**
- Vitals: Max 1 message/5 seconds
- Alerts: Max 1 alert/hour per type (deduplication)
- Status: Max 1 message/5 minutes (heartbeat)
- Commands: No limit (instant response needed)

### **Debouncing (Android)**
```kotlin
// Debounce vitals updates to max 1 UI update/second
val debouncedVitals = mqttManager.vitalsFlow
    .debounce(1000)
    .stateIn(viewModelScope, SharingStarted.Lazily, null)
```

### **Offline Handling**
- **Pi**: Store-and-forward queue → publish khi online lại
- **Android**: Room DB cache → show cached data khi offline

### **Battery Optimization**
- Use `isCleanSession = false` để không mất subscriptions khi reconnect
- Keepalive = 60s (balance between battery và responsiveness)
- Background service với foreground notification

---

## 🐛 **Troubleshooting**

### **Android không nhận messages**
1. Check MQTT connection status
2. Verify subscriptions: `mqttClient.isConnected()`
3. Check topic patterns (wildcard `+`)
4. Enable debug logs: `MqttAndroidClient.setTraceEnabled(true)`

### **Messages bị delay**
1. Check network latency (ping broker)
2. Verify QoS levels
3. Check device không bị doze mode

### **Connection drops**
1. Enable `isAutomaticReconnect = true`
2. Check Wi-Fi stability
3. Monitor keepalive intervals

---

## 📞 **Support**

- **MQTT Broker Dashboard**: https://console.hivemq.cloud/
- **Python Test Scripts**: `/home/pi/Desktop/IoT_health/scripts/`
- **Logs**: `/home/pi/Desktop/IoT_health/logs/`

---

## 📝 **Critical Implementation Notes for AI**

### **1. MQTT Message Handling Priority**
```kotlin
// IMPORTANT: Always debounce vitals updates to prevent UI lag
val debouncedVitals = mqttManager.vitalsFlow
    .debounce(1000) // Max 1 UI update per second
    .stateIn(viewModelScope, SharingStarted.Lazily, null)
```

### **2. Device Pairing Sequence**
```
1. Android scans QR code → Extract pairing_code
2. Call REST API POST /api/devices/pair với pairing_code
3. API returns device_id và MQTT topics
4. MqttManager subscribes to topics
5. Cache device info vào Room database
6. Navigate to Dashboard
```

### **3. Sync Strategy Rules**
- **Pi to Cloud**: Pi updates technical fields only (firmware, OS, last_seen)
- **Android to Cloud**: Android updates user-facing fields (device_name, location)
- **Conflict Resolution**: Cloud wins (latest timestamp)
- **Offline Mode**: Cache everything in Room, sync when online

### **4. Critical Alert Flow**
```
MQTT Alert → MqttManager → Repository → ViewModel → UI
                ↓
        NotificationHelper → System Notification + Sound
                ↓
        Room Database (persist)
```

### **5. Battery Optimization**
- Use `isCleanSession = false` để giữ subscriptions
- Keepalive = 60 seconds (balance)
- Foreground service với notification khi MQTT connected
- Request battery optimization exclusion
- Use WorkManager với network constraints

### **6. Error Handling Patterns**
```kotlin
// Always wrap MQTT operations in try-catch
try {
    mqttClient.publish(topic, message)
} catch (e: MqttException) {
    Log.e(TAG, "MQTT publish failed", e)
    // Queue message for retry
    messageQueue.add(message)
}
```

### **7. State Management Best Practices**
- Use `StateFlow` cho UI state (not LiveData)
- Use `SharedFlow` cho one-time events (navigation, toasts)
- Collect flows với `collectAsState()` trong Compose
- Use `stateIn()` với `SharingStarted.Lazily` để cache latest value

### **8. Dependency Injection with Hilt**
```kotlin
// Application class MUST be annotated
@HiltAndroidApp
class HealthMonitorApp : Application()

// ViewModels MUST use @HiltViewModel
@HiltViewModel
class DashboardViewModel @Inject constructor(...) : ViewModel()

// Fragments/Activities MUST use @AndroidEntryPoint
@AndroidEntryPoint
class MainActivity : ComponentActivity()
```

### **9. ProGuard Rules** (Add to proguard-rules.pro)
```proguard
# Paho MQTT
-keep class org.eclipse.paho.** { *; }
-dontwarn org.eclipse.paho.**

# Gson
-keepattributes Signature
-keepattributes *Annotation*
-dontwarn sun.misc.**
-keep class com.google.gson.** { *; }

# Retrofit
-keepattributes Signature, InnerClasses, EnclosingMethod
-keepattributes RuntimeVisibleAnnotations, RuntimeVisibleParameterAnnotations
-keepclassmembers,allowshrinking,allowobfuscation interface * {
    @retrofit2.http.* <methods>;
}

# Room
-keep class * extends androidx.room.RoomDatabase
-dontwarn androidx.room.paging.**
```

### **10. Required Permissions** (AndroidManifest.xml)
```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
<uses-permission android:name="android.permission.WAKE_LOCK" />
<uses-permission android:name="android.permission.CAMERA" />
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC" />
```

---

## 🎯 **Key Success Metrics**

- **Connection Success Rate**: > 95% (MQTT connect attempts)
- **Message Delivery Rate**: > 99% (QoS 1/2)
- **UI Responsiveness**: < 100ms (vitals display update)
- **Battery Usage**: < 5% per hour (background MQTT)
- **Offline Cache**: 7 days of vitals data
- **Sync Success Rate**: > 98% (background sync to cloud)

---

**✅ System Status**: Fully integrated and tested (Pi side)
**📅 Last Updated**: November 22, 2025
**🔧 Version**: 2.0.0
**📱 Android App Status**: Ready for implementation
**🤖 AI Model**: Use this guide for complete Android app development
