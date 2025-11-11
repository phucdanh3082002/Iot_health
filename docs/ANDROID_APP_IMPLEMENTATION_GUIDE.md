# 📱 ANDROID APP - IMPLEMENTATION GUIDE

**Project:** IoT Health Monitor - Android Client  
**Date:** November 6, 2025  
**Status:** ✅ MQTT Verified - Ready for Development  

---

## ✅ **PHẦN 1: HỆ THỐNG HIỆN TẠI - VERIFIED**

### **1.1 MQTT Broker Status**

```
✅ Broker: test.mosquitto.org:1883
✅ Connection: SUCCESSFUL
✅ Publish: WORKING
✅ Subscribe: WORKING
✅ Topics:
   - iot_health/device/{device_id}/vitals (QoS 1)
   - iot_health/device/{device_id}/alerts (QoS 2)
   - iot_health/device/{device_id}/status (QoS 0)
   - iot_health/patient/{patient_id}/commands (QoS 2)
```

### **1.2 Cloud Database Status**

```
✅ MySQL: 192.168.2.15:3306
✅ Database: iot_health_cloud
✅ Sync: Auto 5 phút
✅ Tables:
   - patients
   - health_records
   - alerts
   - devices (cần tạo)
   - device_ownership (cần tạo)
```

### **1.3 Current Device Configuration**

```yaml
Device ID: rasp_pi_001  # Raspberry Pi hiện tại
Patient ID: patient_001
Location: Home - Living Room
```

---

## 🏗️ **PHẦN 2: ANDROID PROJECT STRUCTURE**

### **2.1 Project Setup**

```
IoTHealthMonitor/
├── app/
│   ├── build.gradle.kts         # App-level build config
│   ├── proguard-rules.pro
│   └── src/
│       ├── main/
│       │   ├── AndroidManifest.xml
│       │   ├── java/com/iot/healthmonitor/
│       │   │   ├── MainActivity.kt
│       │   │   │
│       │   │   ├── data/               # Data Layer
│       │   │   │   ├── local/          # Room Database
│       │   │   │   │   ├── AppDatabase.kt
│       │   │   │   │   ├── dao/
│       │   │   │   │   │   ├── DeviceDao.kt
│       │   │   │   │   │   ├── PatientDao.kt
│       │   │   │   │   │   ├── HealthRecordDao.kt
│       │   │   │   │   │   └── AlertDao.kt
│       │   │   │   │   └── entities/
│       │   │   │   │       ├── DeviceEntity.kt
│       │   │   │   │       ├── PatientEntity.kt
│       │   │   │   │       ├── HealthRecordEntity.kt
│       │   │   │   │       └── AlertEntity.kt
│       │   │   │   │
│       │   │   │   ├── remote/         # Network Layer
│       │   │   │   │   ├── mqtt/
│       │   │   │   │   │   ├── MqttManager.kt
│       │   │   │   │   │   ├── MqttConfig.kt
│       │   │   │   │   │   └── MqttMessageHandler.kt
│       │   │   │   │   ├── api/
│       │   │   │   │   │   ├── HealthApiService.kt
│       │   │   │   │   │   ├── ApiClient.kt
│       │   │   │   │   │   └── ApiModels.kt
│       │   │   │   │   └── mysql/
│       │   │   │   │       └── CloudSyncService.kt
│       │   │   │   │
│       │   │   │   ├── repository/     # Repository Pattern
│       │   │   │   │   ├── DeviceRepository.kt
│       │   │   │   │   ├── PatientRepository.kt
│       │   │   │   │   ├── HealthDataRepository.kt
│       │   │   │   │   └── AlertRepository.kt
│       │   │   │   │
│       │   │   │   └── models/         # Domain Models
│       │   │   │       ├── Device.kt
│       │   │   │       ├── Patient.kt
│       │   │   │       ├── VitalSigns.kt
│       │   │   │       └── Alert.kt
│       │   │   │
│       │   │   ├── domain/             # Business Logic
│       │   │   │   ├── usecases/
│       │   │   │   │   ├── GetDevicesUseCase.kt
│       │   │   │   │   ├── PairDeviceUseCase.kt
│       │   │   │   │   ├── GetVitalsUseCase.kt
│       │   │   │   │   └── HandleAlertUseCase.kt
│       │   │   │   └── validators/
│       │   │   │       └── HealthDataValidator.kt
│       │   │   │
│       │   │   ├── presentation/       # UI Layer
│       │   │   │   ├── screens/
│       │   │   │   │   ├── devices/
│       │   │   │   │   │   ├── DevicesScreen.kt
│       │   │   │   │   │   ├── DevicesViewModel.kt
│       │   │   │   │   │   └── DeviceDetailScreen.kt
│       │   │   │   │   ├── pairing/
│       │   │   │   │   │   ├── QRScannerScreen.kt
│       │   │   │   │   │   ├── ManualPairingScreen.kt
│       │   │   │   │   │   └── PairingViewModel.kt
│       │   │   │   │   ├── overview/
│       │   │   │   │   │   ├── OverviewScreen.kt
│       │   │   │   │   │   └── OverviewViewModel.kt
│       │   │   │   │   ├── alerts/
│       │   │   │   │   │   ├── AlertsScreen.kt
│       │   │   │   │   │   └── AlertsViewModel.kt
│       │   │   │   │   ├── patients/
│       │   │   │   │   │   ├── PatientsScreen.kt
│       │   │   │   │   │   ├── PatientDetailScreen.kt
│       │   │   │   │   │   └── PatientsViewModel.kt
│       │   │   │   │   └── settings/
│       │   │   │   │       ├── SettingsScreen.kt
│       │   │   │   │       └── SettingsViewModel.kt
│       │   │   │   │
│       │   │   │   ├── components/     # Reusable Components
│       │   │   │   │   ├── VitalCard.kt
│       │   │   │   │   ├── DeviceCard.kt
│       │   │   │   │   ├── AlertCard.kt
│       │   │   │   │   ├── SparklineChart.kt
│       │   │   │   │   └── StatusIndicator.kt
│       │   │   │   │
│       │   │   │   ├── navigation/
│       │   │   │   │   └── NavGraph.kt
│       │   │   │   │
│       │   │   │   └── theme/
│       │   │   │       ├── Color.kt
│       │   │   │       ├── Theme.kt
│       │   │   │       └── Type.kt
│       │   │   │
│       │   │   ├── di/                 # Dependency Injection (Hilt)
│       │   │   │   ├── AppModule.kt
│       │   │   │   ├── DatabaseModule.kt
│       │   │   │   ├── NetworkModule.kt
│       │   │   │   └── RepositoryModule.kt
│       │   │   │
│       │   │   └── utils/              # Utilities
│       │   │       ├── DateFormatter.kt
│       │   │       ├── Logger.kt
│       │   │       ├── Constants.kt
│       │   │       └── Extensions.kt
│       │   │
│       │   └── res/
│       │       ├── drawable/
│       │       ├── layout/
│       │       ├── values/
│       │       │   ├── strings.xml
│       │       │   ├── colors.xml
│       │       │   └── themes.xml
│       │       └── xml/
│       │           └── network_security_config.xml
│       │
│       ├── androidTest/
│       └── test/
│
├── build.gradle.kts                # Project-level build config
├── settings.gradle.kts
├── gradle.properties
└── local.properties
```

---

## 📦 **PHẦN 3: DEPENDENCIES**

### **3.1 build.gradle.kts (Project Level)**

```kotlin
// Top-level build file
plugins {
    id("com.android.application") version "8.2.0" apply false
    id("org.jetbrains.kotlin.android") version "1.9.20" apply false
    id("com.google.dagger.hilt.android") version "2.48" apply false
    id("com.google.devtools.ksp") version "1.9.20-1.0.14" apply false
}
```

### **3.2 build.gradle.kts (App Level)**

```kotlin
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.dagger.hilt.android")
    id("com.google.devtools.ksp")
    kotlin("kapt")
}

android {
    namespace = "com.iot.healthmonitor"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.iot.healthmonitor"
        minSdk = 26  // Android 8.0+
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        
        // MQTT Configuration
        buildConfigField("String", "MQTT_BROKER", "\"test.mosquitto.org\"")
        buildConfigField("int", "MQTT_PORT", "1883")
        buildConfigField("String", "MYSQL_HOST", "\"192.168.2.15\"")
        buildConfigField("int", "MYSQL_PORT", "3306")
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
        debug {
            isDebuggable = true
        }
    }
    
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    
    kotlinOptions {
        jvmTarget = "17"
    }
    
    buildFeatures {
        compose = true
        buildConfig = true
    }
    
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.4"
    }
    
    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    // Core Android
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.6.2")
    implementation("androidx.activity:activity-compose:1.8.1")
    
    // Jetpack Compose
    val composeVersion = "1.5.4"
    implementation(platform("androidx.compose:compose-bom:2023.10.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    
    // Navigation Compose
    implementation("androidx.navigation:navigation-compose:2.7.5")
    
    // ViewModel Compose
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.6.2")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.6.2")
    
    // Hilt Dependency Injection
    implementation("com.google.dagger:hilt-android:2.48")
    kapt("com.google.dagger:hilt-android-compiler:2.48")
    implementation("androidx.hilt:hilt-navigation-compose:1.1.0")
    
    // Room Database
    val roomVersion = "2.6.0"
    implementation("androidx.room:room-runtime:$roomVersion")
    implementation("androidx.room:room-ktx:$roomVersion")
    ksp("androidx.room:room-compiler:$roomVersion")
    
    // MQTT (Paho Android)
    implementation("org.eclipse.paho:org.eclipse.paho.client.mqttv3:1.2.5")
    implementation("org.eclipse.paho:org.eclipse.paho.android.service:1.1.1")
    
    // Retrofit + OkHttp (REST API)
    implementation("com.squareup.retrofit2:retrofit:2.9.0")
    implementation("com.squareup.retrofit2:converter-gson:2.9.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
    
    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.7.3")
    
    // DataStore (Preferences)
    implementation("androidx.datastore:datastore-preferences:1.0.0")
    
    // Charts (MPAndroidChart)
    implementation("com.github.PhilJay:MPAndroidChart:v3.1.0")
    
    // QR Code Scanner (ZXing)
    implementation("com.google.zxing:core:3.5.2")
    implementation("com.journeyapps:zxing-android-embedded:4.3.0")
    
    // Image Loading (Coil for Compose)
    implementation("io.coil-kt:coil-compose:2.5.0")
    
    // JSON (Gson)
    implementation("com.google.code.gson:gson:2.10.1")
    
    // WorkManager (Background Sync)
    implementation("androidx.work:work-runtime-ktx:2.9.0")
    
    // Accompanist (Compose Extensions)
    implementation("com.google.accompanist:accompanist-permissions:0.32.0")
    implementation("com.google.accompanist:accompanist-systemuicontroller:0.32.0")
    
    // Security (EncryptedSharedPreferences)
    implementation("androidx.security:security-crypto:1.1.0-alpha06")
    
    // Testing
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.5.1")
    androidTestImplementation(platform("androidx.compose:compose-bom:2023.10.01"))
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
```

### **3.3 settings.gradle.kts**

```kotlin
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        maven { url = uri("https://jitpack.io") }  // For MPAndroidChart
    }
}

rootProject.name = "IoT Health Monitor"
include(":app")
```

---

## 🔧 **PHẦN 4: CORE IMPLEMENTATIONS**

### **4.1 MQTT Manager (MqttManager.kt)**

```kotlin
package com.iot.healthmonitor.data.remote.mqtt

import android.content.Context
import android.util.Log
import com.google.gson.Gson
import info.mqtt.android.service.MqttAndroidClient
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.eclipse.paho.client.mqttv3.*
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class MqttManager @Inject constructor(
    private val context: Context,
    private val gson: Gson
) {
    companion object {
        private const val TAG = "MqttManager"
        private const val BROKER_URL = "tcp://test.mosquitto.org:1883"
        private const val CLIENT_ID_PREFIX = "android_health_monitor_"
    }

    private var mqttClient: MqttAndroidClient? = null
    private val _connectionState = MutableStateFlow<ConnectionState>(ConnectionState.Disconnected)
    val connectionState: StateFlow<ConnectionState> = _connectionState

    private val _vitalsFlow = MutableStateFlow<VitalsPayload?>(null)
    val vitalsFlow: StateFlow<VitalsPayload?> = _vitalsFlow

    private val _alertsFlow = MutableStateFlow<AlertPayload?>(null)
    val alertsFlow: StateFlow<AlertPayload?> = _alertsFlow

    fun connect(onConnected: () -> Unit = {}) {
        val clientId = CLIENT_ID_PREFIX + System.currentTimeMillis()
        
        mqttClient = MqttAndroidClient(context, BROKER_URL, clientId).apply {
            setCallback(object : MqttCallbackExtended {
                override fun connectComplete(reconnect: Boolean, serverURI: String?) {
                    Log.i(TAG, "✅ Connected to broker: $serverURI")
                    _connectionState.value = ConnectionState.Connected
                    onConnected()
                }

                override fun connectionLost(cause: Throwable?) {
                    Log.w(TAG, "⚠️ Connection lost: ${cause?.message}")
                    _connectionState.value = ConnectionState.Disconnected
                }

                override fun messageArrived(topic: String?, message: MqttMessage?) {
                    handleMessage(topic, message)
                }

                override fun deliveryComplete(token: IMqttDeliveryToken?) {
                    Log.d(TAG, "✅ Message delivered")
                }
            })

            try {
                val options = MqttConnectOptions().apply {
                    isAutomaticReconnect = true
                    isCleanSession = false
                    connectionTimeout = 30
                    keepAliveInterval = 60
                }

                _connectionState.value = ConnectionState.Connecting
                connect(options, null, object : IMqttActionListener {
                    override fun onSuccess(asyncActionToken: IMqttToken?) {
                        Log.i(TAG, "Connection success!")
                    }

                    override fun onFailure(asyncActionToken: IMqttToken?, exception: Throwable?) {
                        Log.e(TAG, "Connection failed: ${exception?.message}")
                        _connectionState.value = ConnectionState.Error(exception?.message ?: "Unknown error")
                    }
                })
            } catch (e: MqttException) {
                Log.e(TAG, "MQTT Exception: ${e.message}")
                _connectionState.value = ConnectionState.Error(e.message ?: "MQTT error")
            }
        }
    }

    fun subscribeToDevice(deviceId: String) {
        try {
            val topics = arrayOf(
                "iot_health/device/$deviceId/vitals",
                "iot_health/device/$deviceId/alerts",
                "iot_health/device/$deviceId/status"
            )
            val qos = intArrayOf(1, 2, 0)

            mqttClient?.subscribe(topics, qos, null, object : IMqttActionListener {
                override fun onSuccess(asyncActionToken: IMqttToken?) {
                    Log.i(TAG, "📡 Subscribed to device: $deviceId")
                }

                override fun onFailure(asyncActionToken: IMqttToken?, exception: Throwable?) {
                    Log.e(TAG, "Subscribe failed: ${exception?.message}")
                }
            })
        } catch (e: MqttException) {
            Log.e(TAG, "Subscribe error: ${e.message}")
        }
    }

    fun subscribeToAllDevices() {
        try {
            val topics = arrayOf(
                "iot_health/device/+/vitals",
                "iot_health/device/+/alerts",
                "iot_health/device/+/status"
            )
            val qos = intArrayOf(1, 2, 0)

            mqttClient?.subscribe(topics, qos)
            Log.i(TAG, "📡 Subscribed to all devices (wildcard)")
        } catch (e: MqttException) {
            Log.e(TAG, "Subscribe all error: ${e.message}")
        }
    }

    private fun handleMessage(topic: String?, message: MqttMessage?) {
        topic ?: return
        message ?: return

        try {
            val payload = message.toString()
            Log.d(TAG, "📥 Received on $topic: ${payload.take(100)}...")

            when {
                "/vitals" in topic -> {
                    val vitals = gson.fromJson(payload, VitalsPayload::class.java)
                    _vitalsFlow.value = vitals
                }
                "/alerts" in topic -> {
                    val alert = gson.fromJson(payload, AlertPayload::class.java)
                    _alertsFlow.value = alert
                }
                "/status" in topic -> {
                    // Handle device status
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error parsing message: ${e.message}")
        }
    }

    fun publishCommand(patientId: String, command: String, params: Map<String, Any> = emptyMap()) {
        try {
            val topic = "iot_health/patient/$patientId/commands"
            val commandPayload = mapOf(
                "command_id" to System.currentTimeMillis().toString(),
                "timestamp" to System.currentTimeMillis() / 1000.0,
                "issuer" to "android_app",
                "command" to command,
                "parameters" to params
            )
            
            val json = gson.toJson(commandPayload)
            val mqttMessage = MqttMessage(json.toByteArray()).apply {
                qos = 2  // Exactly once for commands
            }

            mqttClient?.publish(topic, mqttMessage)
            Log.i(TAG, "📤 Published command: $command to $patientId")
        } catch (e: MqttException) {
            Log.e(TAG, "Publish command error: ${e.message}")
        }
    }

    fun disconnect() {
        try {
            mqttClient?.disconnect()
            _connectionState.value = ConnectionState.Disconnected
            Log.i(TAG, "🔌 Disconnected from broker")
        } catch (e: MqttException) {
            Log.e(TAG, "Disconnect error: ${e.message}")
        }
    }
}

sealed class ConnectionState {
    object Disconnected : ConnectionState()
    object Connecting : ConnectionState()
    object Connected : ConnectionState()
    data class Error(val message: String) : ConnectionState()
}

// Data classes matching Python payloads
data class VitalsPayload(
    val timestamp: Double,
    val device_id: String,
    val patient_id: String,
    val measurements: Measurements
)

data class Measurements(
    val heart_rate: Measurement?,
    val spo2: Measurement?,
    val temperature: TemperatureMeasurement?,
    val blood_pressure: BloodPressureMeasurement?
)

data class Measurement(
    val value: Double,
    val unit: String,
    val valid: Boolean = true
)

data class TemperatureMeasurement(
    val object_temp: Double,
    val ambient_temp: Double?,
    val unit: String
)

data class BloodPressureMeasurement(
    val systolic: Int,
    val diastolic: Int,
    val map: Int?,
    val unit: String
)

data class AlertPayload(
    val timestamp: Double,
    val device_id: String,
    val patient_id: String,
    val alert_type: String,
    val severity: String,
    val message: String,
    val vital_sign: String?,
    val current_value: Double?
)
```

---

## 🚀 **PHẦN 5: ROADMAP IMPLEMENTATION**

### **Week 1: Project Setup & MQTT**
- ✅ Day 1-2: Create Android Studio project
- ✅ Day 3-4: Setup dependencies & Hilt DI
- ✅ Day 5-7: Implement MqttManager + test connection

### **Week 2: Database & Repository**
- ✅ Day 8-10: Room database (Device, Patient, HealthRecord entities)
- ✅ Day 11-12: Repository layer
- ✅ Day 13-14: Sync logic (MQTT → Room cache)

### **Week 3: UI Foundation**
- ✅ Day 15-17: Navigation setup + Bottom nav
- ✅ Day 18-19: Theme & design system
- ✅ Day 20-21: Reusable components (VitalCard, DeviceCard)

### **Week 4: Devices Screen**
- ✅ Day 22-24: DevicesScreen + ViewModel
- ✅ Day 25-26: Device detail screen
- ✅ Day 27-28: Real-time vitals display

### **Week 5: QR Pairing**
- ✅ Day 29-30: QR scanner integration (ZXing)
- ✅ Day 31-32: Manual pairing screen
- ✅ Day 33-35: Device pairing flow + MySQL sync

### **Week 6-7: Remaining Screens**
- Week 6: Overview, Alerts, Patients screens
- Week 7: Settings, polish, testing

### **Week 8: Testing & Deployment**
- Integration testing
- UI testing
- Performance optimization
- Play Store preparation

---

## 📋 **PHẦN 6: NEXT IMMEDIATE STEPS**

### **Bước tiếp theo (Bạn chọn):**

1. **Tạo Android Studio Project ngay** → tôi sẽ guide từng bước
2. **Xem code mẫu chi tiết** → Devices Screen implementation
3. **Setup MySQL tables** → devices, device_ownership cho pairing
4. **Test MQTT với Pi thực** → publish vitals từ GUI hiện tại

**Bạn muốn bắt đầu từ đâu?**
