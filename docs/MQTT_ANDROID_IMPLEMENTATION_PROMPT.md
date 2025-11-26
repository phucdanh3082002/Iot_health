# 📡 PROMPT: Implement Real-time MQTT Monitoring for Android App

## 🎯 Objective
Implement real-time vital signs monitoring trong Android app sử dụng **MQTT protocol** để nhận dữ liệu từ Raspberry Pi devices và hiển thị live trên UI đã có sẵn.

---

## 📋 Prerequisites & Context

### **Current Status**
- ✅ Android UI đã hoàn thành (screens sẵn sàng nhận data)
- ✅ Device pairing flow đã hoàn thành (QR scan, API integration)
- ✅ REST API backend đã deploy tại `http://47.130.193.237`
- ✅ MySQL Cloud database schema v2.0.0 (AWS RDS)
- ⏳ **MQTT client integration chưa có** - cần implement

### **Technology Stack**
- **Language**: Kotlin
- **UI Framework**: Jetpack Compose (Material 3)
- **Architecture**: MVVM + Clean Architecture
- **DI**: Hilt/Dagger
- **Database**: Room (local cache)
- **MQTT Library**: **Eclipse Paho Android Service** (org.eclipse.paho:org.eclipse.paho.android.service)

---

## 🔧 MQTT Configuration (CRITICAL - KHÔNG ĐỔI)

### **Broker Details**
```kotlin
const val MQTT_BROKER_URL = "ssl://c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud:8883"
const val MQTT_CLIENT_ID_PREFIX = "android_app_" // + unique ID
const val MQTT_USERNAME = "android_app" // Credentials từ HiveMQ Cloud
const val MQTT_PASSWORD = "Danhsidoi123" 
const val MQTT_KEEP_ALIVE = 60 // seconds
const val MQTT_CLEAN_SESSION = true
const val MQTT_AUTO_RECONNECT = true
```

### **QoS Levels (BẮT BUỘC)**
```kotlin
enum class MqttQos(val value: Int) {
    STATUS(0),      // Fire and forget
    VITALS(1),      // At least once
    ALERTS(2),      // Exactly once
    COMMANDS(2)     // Exactly once
}
```

### **Topic Structure (KHÔNG ĐỔI)**
```kotlin
object MqttTopics {
    // Subscribe topics (receive from Pi)
    fun vitals(deviceId: String) = "iot_health/device/$deviceId/vitals"
    fun alerts(deviceId: String) = "iot_health/device/$deviceId/alerts"
    fun status(deviceId: String) = "iot_health/device/$deviceId/status"
    
    // Publish topics (send commands to Pi)
    fun commands(patientId: String) = "iot_health/patient/$patientId/commands"
}
```

---

## 📦 Required Dependencies (build.gradle.kts)

```kotlin
dependencies {
    // MQTT Client
    implementation("org.eclipse.paho:org.eclipse.paho.client.mqttv3:1.2.5")
    implementation("org.eclipse.paho:org.eclipse.paho.android.service:1.1.1")
    
    // JSON Parsing
    implementation("com.google.code.gson:gson:2.10.1")
    
    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
    
    // StateFlow/LiveData
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.6.2")
    
    // Room Database (cache)
    implementation("androidx.room:room-runtime:2.6.0")
    implementation("androidx.room:room-ktx:2.6.0")
    kapt("androidx.room:room-compiler:2.6.0")
    
    // Hilt DI
    implementation("com.google.dagger:hilt-android:2.48")
    kapt("com.google.dagger:hilt-compiler:2.48")
}
```

**AndroidManifest.xml permissions**:
```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
<uses-permission android:name="android.permission.WAKE_LOCK" />

<application>
    <service android:name="org.eclipse.paho.android.service.MqttService" />
</application>
```

---

## 📊 Message Payloads (JSON Schema - CHÍNH XÁC)

### **1. Vitals Payload** (Topic: `iot_health/device/{device_id}/vitals`, QoS 1)
```json
{
  "timestamp": 1700518000.123,
  "device_id": "rpi_bp_001",
  "patient_id": "patient_001",
  "measurements": {
    "heart_rate": {
      "value": 78,
      "unit": "bpm",
      "valid": true,
      "metadata": {
        "signal_quality_index": 89.5,
        "peak_count": 18,
        "measurement_duration": 24.5
      }
    },
    "spo2": {
      "value": 97,
      "unit": "%",
      "valid": true,
      "metadata": {
        "cv": 1.8,
        "signal_quality": "good"
      }
    },
    "temperature": {
      "object_temp": 36.7,
      "ambient_temp": 24.2,
      "unit": "celsius"
    },
    "blood_pressure": {
      "systolic": 120,
      "diastolic": 80,
      "map": 93,
      "unit": "mmHg"
    }
  }
}
```

### **2. Alert Payload** (Topic: `iot_health/device/{device_id}/alerts`, QoS 2)
```json
{
  "timestamp": 1700518000.123,
  "device_id": "rpi_bp_001",
  "patient_id": "patient_001",
  "alert_type": "high_heart_rate",
  "severity": "high",
  "message": "Nhịp tim cao: 125 BPM (ngưỡng: 60-100)",
  "vital_sign": "heart_rate",
  "current_value": 125,
  "threshold_value": 100
}
```

### **3. Status Payload** (Topic: `iot_health/device/{device_id}/status`, QoS 0)
```json
{
  "timestamp": 1700518000.123,
  "device_id": "rpi_bp_001",
  "status": "online",
  "uptime_seconds": 86400,
  "battery_level": 85,
  "wifi_signal": -45
}
```

### **4. Command Payload** (Publish to: `iot_health/patient/{patient_id}/commands`, QoS 2)
```json
{
  "command_id": "cmd_1700518000",
  "timestamp": 1700518000.123,
  "issuer": "android_app",
  "command": "start_measurement",
  "parameters": {
    "measurement_type": "blood_pressure",
    "patient_id": "patient_001"
  }
}
```

---

## 🏗️ Required Architecture Components

### **1. Data Classes (models/MqttPayloads.kt)**
```kotlin
data class VitalsPayload(
    val timestamp: Double,
    val device_id: String,
    val patient_id: String,
    val measurements: Measurements
)

data class Measurements(
    val heart_rate: VitalSign?,
    val spo2: VitalSign?,
    val temperature: Temperature?,
    val blood_pressure: BloodPressure?
)

data class VitalSign(
    val value: Int,
    val unit: String,
    val valid: Boolean,
    val metadata: Map<String, Any>?
)

data class Temperature(
    val object_temp: Double,
    val ambient_temp: Double,
    val unit: String
)

data class BloodPressure(
    val systolic: Int,
    val diastolic: Int,
    val map: Int,
    val unit: String
)

data class AlertPayload(
    val timestamp: Double,
    val device_id: String,
    val patient_id: String,
    val alert_type: String,
    val severity: String, // low, medium, high, critical
    val message: String,
    val vital_sign: String,
    val current_value: Float,
    val threshold_value: Float
)

data class StatusPayload(
    val timestamp: Double,
    val device_id: String,
    val status: String, // online, offline
    val uptime_seconds: Long,
    val battery_level: Int,
    val wifi_signal: Int
)

data class CommandPayload(
    val command_id: String,
    val timestamp: Double,
    val issuer: String = "android_app",
    val command: String,
    val parameters: Map<String, Any>
)
```

### **2. MqttManager (Singleton via Hilt)**
```kotlin
@Singleton
class MqttManager @Inject constructor(
    @ApplicationContext private val context: Context,
    private val gson: Gson
) {
    private var mqttClient: MqttAndroidClient? = null
    
    // StateFlows for real-time updates
    private val _vitalsFlow = MutableStateFlow<VitalsPayload?>(null)
    val vitalsFlow: StateFlow<VitalsPayload?> = _vitalsFlow.asStateFlow()
    
    private val _alertsFlow = MutableStateFlow<AlertPayload?>(null)
    val alertsFlow: StateFlow<AlertPayload?> = _alertsFlow.asStateFlow()
    
    private val _statusFlow = MutableStateFlow<Map<String, StatusPayload>>(emptyMap())
    val statusFlow: StateFlow<Map<String, StatusPayload>> = _statusFlow.asStateFlow()
    
    private val _connectionState = MutableStateFlow(ConnectionState.DISCONNECTED)
    val connectionState: StateFlow<ConnectionState> = _connectionState.asStateFlow()
    
    fun connect(clientId: String): Result<Unit>
    fun disconnect()
    fun subscribeToDevice(deviceId: String): Result<Unit>
    fun unsubscribeFromDevice(deviceId: String): Result<Unit>
    fun publishCommand(patientId: String, command: CommandPayload): Result<Unit>
    
    private fun handleVitalsMessage(deviceId: String, message: String)
    private fun handleAlertMessage(deviceId: String, message: String)
    private fun handleStatusMessage(deviceId: String, message: String)
}

enum class ConnectionState {
    CONNECTED, CONNECTING, DISCONNECTED, ERROR
}
```

### **3. Room Database Cache (database/)**
```kotlin
@Entity(tableName = "vitals_cache")
data class VitalsEntity(
    @PrimaryKey val id: String, // "$deviceId-$timestamp"
    val deviceId: String,
    val patientId: String,
    val timestamp: Long,
    val heartRate: Int?,
    val spo2: Int?,
    val objectTemp: Double?,
    val systolic: Int?,
    val diastolic: Int?,
    val map: Int?,
    val rawJson: String, // Full JSON for later parsing
    val syncedToCloud: Boolean = false,
    val createdAt: Long = System.currentTimeMillis()
)

@Dao
interface VitalsDao {
    @Query("SELECT * FROM vitals_cache WHERE deviceId = :deviceId ORDER BY timestamp DESC LIMIT 50")
    fun getRecentVitals(deviceId: String): Flow<List<VitalsEntity>>
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertVitals(vitals: VitalsEntity)
    
    @Query("DELETE FROM vitals_cache WHERE timestamp < :cutoffTime")
    suspend fun deleteOldRecords(cutoffTime: Long)
}
```

### **4. ViewModel (ui/monitoring/MonitoringViewModel.kt)**
```kotlin
@HiltViewModel
class MonitoringViewModel @Inject constructor(
    private val mqttManager: MqttManager,
    private val vitalsRepository: VitalsRepository,
    savedStateHandle: SavedStateHandle
) : ViewModel() {
    
    private val deviceId: String = savedStateHandle.get<String>("deviceId") ?: ""
    
    // UI State
    private val _uiState = MutableStateFlow(MonitoringUiState())
    val uiState: StateFlow<MonitoringUiState> = _uiState.asStateFlow()
    
    init {
        observeMqttData()
        loadCachedData()
    }
    
    private fun observeMqttData() {
        viewModelScope.launch {
            // Observe vitals with debounce (max 1 update/second)
            mqttManager.vitalsFlow
                .debounce(1000)
                .filterNotNull()
                .filter { it.device_id == deviceId }
                .collect { vitals ->
                    updateUiWithVitals(vitals)
                    cacheVitals(vitals)
                }
        }
        
        viewModelScope.launch {
            mqttManager.alertsFlow
                .filterNotNull()
                .filter { it.device_id == deviceId }
                .collect { alert ->
                    handleAlert(alert)
                }
        }
    }
    
    fun startMeasurement(type: String) {
        // Publish command to MQTT
    }
    
    fun stopMeasurement() {
        // Publish command to MQTT
    }
}

data class MonitoringUiState(
    val heartRate: Int? = null,
    val spo2: Int? = null,
    val temperature: Double? = null,
    val systolic: Int? = null,
    val diastolic: Int? = null,
    val isOnline: Boolean = false,
    val lastUpdate: Long? = null,
    val alerts: List<AlertPayload> = emptyList(),
    val isLoading: Boolean = false
)
```

---

## 🎯 Implementation Requirements

### **CRITICAL Requirements**
1. ✅ **TLS/SSL Connection**: Sử dụng `ssl://` protocol với port 8883
2. ✅ **Auto-reconnect**: Exponential backoff (5s, 10s, 30s, 60s max)
3. ✅ **QoS Compliance**: Đúng QoS level cho từng message type
4. ✅ **Debounce UI Updates**: Max 1 update/second để tránh lag UI
5. ✅ **Offline Support**: Cache vitals vào Room DB khi offline
6. ✅ **Memory Management**: Cleanup old cache (giữ 7 ngày gần nhất)
7. ✅ **Error Handling**: Graceful degradation khi mất kết nối

### **Security Requirements**
- ✅ Credentials lưu trong **encrypted SharedPreferences** hoặc **Keystore**
- ✅ Validate message format trước khi parse (prevent malformed JSON crashes)
- ✅ Certificate pinning (optional nhưng recommended cho production)

### **Performance Requirements**
- ✅ Background service cho MQTT (không block UI thread)
- ✅ Coroutines cho async operations
- ✅ LiveData/StateFlow cho reactive UI updates
- ✅ Pagination cho history list (load 50 records at a time)

### **Testing Requirements**
- ✅ Unit tests cho MqttManager (mock broker)
- ✅ Integration tests với HiveMQ Cloud test broker
- ✅ UI tests cho real-time updates (Compose Test)

---

## 🔄 Data Flow (Từ Pi → Android UI)

```
Raspberry Pi → Publish vitals (QoS 1, every 5s when measuring)
                ↓
HiveMQ Cloud Broker (c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud)
                ↓
Android MqttManager → Subscribe iot_health/device/rpi_bp_001/vitals
                ↓
Parse JSON → VitalsPayload data class
                ↓
Emit to vitalsFlow (StateFlow)
                ↓
ViewModel observe → Debounce 1s → Update uiState
                ↓
Compose UI auto-recompose → Display on screen
                ↓
(Background) Save to Room DB for offline cache
```

---

## 📱 UI Integration Points (EXISTING SCREENS)

### **Screens cần integrate MQTT data**:
1. **Dashboard Screen** (`DashboardScreen.kt`):
   - Display latest vitals (HR, SpO2, Temp, BP)
   - Device online/offline status indicator
   - Last update timestamp

2. **Heart Rate Screen** (`HeartRateScreen.kt`):
   - Real-time HR chart (live update)
   - Signal quality indicator
   - Peak detection visualization

3. **BP Measurement Screen** (`BPMeasurementScreen.kt`):
   - Start/stop measurement commands (publish MQTT)
   - Live pressure readings during inflation/deflation
   - Final BP results display

4. **History Screen** (`HistoryScreen.kt`):
   - Query Room DB cache (offline data)
   - Show chart/list từ cached vitals

---

## ⚠️ Common Pitfalls to Avoid

1. **KHÔNG dùng MainScope** cho MQTT callbacks → Dùng `viewModelScope` hoặc background dispatcher
2. **KHÔNG subscribe tất cả devices cùng lúc** → Subscribe từng device khi cần
3. **KHÔNG parse JSON trên UI thread** → Dùng `withContext(Dispatchers.IO)`
4. **KHÔNG giữ connection khi app background** → Implement lifecycle-aware connection
5. **KHÔNG hardcode credentials** → Dùng BuildConfig hoặc secure storage

---

## 🧪 Testing Commands (Verify Implementation)

### **Test MQTT Connection**
```kotlin
// Unit test
@Test
fun `connect to broker successfully`() = runTest {
    val result = mqttManager.connect("test_client_001")
    assertTrue(result.isSuccess)
    assertEquals(ConnectionState.CONNECTED, mqttManager.connectionState.value)
}
```

### **Test với MQTT Explorer** (Desktop tool)
- Connect to `c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud:8883`
- Subscribe to `iot_health/device/+/vitals`
- Verify messages từ Pi đang publish

### **Manual Test on Android**
```bash
# Trigger measurement từ Android
# → Verify Pi nhận command và bắt đầu đo
# → Verify Android nhận vitals updates real-time
```

---

## 📚 Reference Documentation

- **MQTT Spec**: Xem file `/docs/MQTT_IMPLEMENTATION_SUMMARY.md` trong repo
- **Database Schema**: `/DATABASE_SCHEMA.md`
- **Copilot Instructions**: `/.github/copilot-instructions.md` (section MQTT Communication Architecture)
- **Eclipse Paho Docs**: https://www.eclipse.org/paho/index.php?page=clients/android/index.php

---

## ✅ Definition of Done

- [ ] MqttManager class implemented với all required methods
- [ ] StateFlows cho vitals, alerts, status
- [ ] Room DB cache cho offline data
- [ ] ViewModel integration với existing UI screens
- [ ] Auto-reconnect với exponential backoff
- [ ] Debounce UI updates (1 update/second max)
- [ ] Error handling và logging
- [ ] Unit tests pass (coverage > 80%)
- [ ] Manual testing với real Pi device successful
- [ ] No memory leaks (LeakCanary verified)
- [ ] Battery consumption acceptable (< 5% per hour khi active monitoring)

---

## 🚀 Deliverables

1. Source code files:
   - `data/mqtt/MqttManager.kt`
   - `data/models/MqttPayloads.kt`
   - `data/database/VitalsEntity.kt` + DAO
   - `data/repository/VitalsRepository.kt`
   - `ui/monitoring/MonitoringViewModel.kt`

2. Updated `build.gradle.kts` với dependencies

3. Updated `AndroidManifest.xml` với permissions

4. Unit test files trong `test/` directory

5. Brief documentation (comment trong code là đủ, KHÔNG tạo README riêng)

---

**Bắt đầu implementation ngay, tuân thủ CHÍNH XÁC cấu hình trên. Hỏi lại nếu có điểm nào không rõ!** 🚀