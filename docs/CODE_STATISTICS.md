# 📊 **CODE STATISTICS & ARCHITECTURE DEEP DIVE**

**Generated:** 28/11/2025  
**System:** IoT Health Monitoring v2.0.0

---

## 📁 **Complete File Breakdown**

### **GUI Layer - 5,410+ lines**

#### `main_app.py` (1,825 lines)
```
Purpose: Main Kivy/KivyMD application controller
Key Components:
  - HealthMonitorApp (MDApp)
    ├── Screen initialization & management
    ├── Sensor callbacks registration
    ├── MQTT integration setup
    ├── Data update scheduling
    └── Settings persistence

Responsibilities:
  ✅ Create sensors from config
  ✅ Initialize TTS manager
  ✅ Setup screen navigation
  ✅ Bind sensor callbacks
  ✅ Manage data updates (non-blocking)
  ✅ Handle app lifecycle (on_start, on_stop)
  ✅ Provide patient_id resolution
  ✅ Integrate MQTT publishing

Key Methods:
  - __init__() - Initialize app
  - _create_sensors_from_config() - Sensor setup
  - _init_tts_manager() - TTS initialization
  - on_max30102_data() - HR/SpO2 callback
  - on_temperature_data() - Temperature callback
  - on_blood_pressure_data() - BP callback
  - _update_sensor_status() - Status updates
  - navigate_to_screen() - Screen switching
```

#### `dashboard_screen.py` (374 lines)
```
Purpose: Home screen with overview of all measurements
Layout:
  ┌─────────────────────────────────┐
  │  Info Banner (title + time)     │ dp(100)
  ├─────────────────────────────────┤
  │  ┌──────────────┬──────────────┐ │
  │  │   HR/SpO2    │  Temperature │ │ dp(96)
  │  ├──────────────┼──────────────┤ │
  │  │   Blood      │   Settings   │ │
  │  │  Pressure    │   + Info     │ │
  │  └──────────────┴──────────────┘ │
  │                                   │
  │  [History] [Sync Status]          │ dp(40)
  └─────────────────────────────────┘

Key Features:
  ✅ Feature cards with icons
  ✅ Real-time clock update (1s interval)
  ✅ Navigation to measurement screens
  ✅ Sync status indicator
  ✅ Responsive grid layout
  
Callbacks:
  - on_card_press() → Navigate to measurement
  - on_settings_press() → Open settings
  - on_history_press() → Open history
  - update_time() → Clock scheduler
```

#### `heart_rate_screen.py` (1,031 lines)
```
Purpose: HR/SpO2 measurement with signal quality visualization
State Machine:
  IDLE → WAITING (finger detect) → MEASURING (15s) → FINISHED → IDLE
  
Key Components:
  - PulseAnimation (animated heart icon)
  - HeartRateMeasurementController (state machine)
  - Signal quality graph (matplotlib)
  - Real-time data display
  
Layout (480×320):
  ┌──────────────────────────────────┐
  │ Title: HỀ RIT TIM & SpO2          │ dp(30)
  ├──────────────────────────────────┤
  │  ┌──────────────────────────────┐ │
  │  │  Pulse Animation (🫀)         │ │ dp(60)
  │  │  HR: 78 bpm | SpO2: 97%      │ │
  │  │  Signal Quality: ████████░░  │ │
  │  └──────────────────────────────┘ │
  ├──────────────────────────────────┤
  │  ┌──────────────────────────────┐ │
  │  │ [Graph showing HR trend]      │ │ dp(80)
  │  │ (matplotlib embedded)         │ │
  │  └──────────────────────────────┘ │
  ├──────────────────────────────────┤
  │ Status: Ready | Timer: 15s       │ dp(30)
  ├──────────────────────────────────┤
  │  [Start] [Stop]   [Back]         │ dp(40)
  └──────────────────────────────────┘

Key Features:
  ✅ 15-second standardized measurement
  ✅ Finger detection with grace period (3s)
  ✅ Real-time signal quality feedback
  ✅ Pulse animation synchronized to HR
  ✅ Non-blocking measurement loop
  ✅ Automatic result collection
  ✅ TTS "Remove finger" alert
  ✅ MQTT vitals publish
  
State Transitions:
  IDLE → WAITING:
    - Sensor starts reading
    - Wait for finger detection (5-10s)
    
  WAITING → MEASURING:
    - Finger detected
    - 15s measurement window starts
    
  MEASURING → FINISHED:
    - 15s elapsed or early exit if finger lost
    - Calculate HR/SpO2/SQI averages
    - Publish to MQTT
    - Save to SQLite
    
  FINISHED → IDLE:
    - User presses Next/Back
    - Screen transitions
```

#### `temperature_screen.py` (740 lines)
```
Purpose: Temperature measurement (MLX90614)
Features:
  ✅ Object temperature (forehead/ear)
  ✅ Ambient temperature reference
  ✅ 5-second measurement stabilization
  ✅ Outlier rejection (±0.7°C)
  ✅ Medical-range color coding
  ✅ Averaging for accuracy
  
Layout:
  ┌──────────────────────────────────┐
  │ Title: NHIỆT ĐỘ CƠ THỂ           │
  ├──────────────────────────────────┤
  │  ┌──────────────────────────────┐ │
  │  │ Object Temp: 36.7°C          │ │
  │  │ Ambient: 24.2°C              │ │
  │  │ Status: Normal               │ │
  │  └──────────────────────────────┘ │
  ├──────────────────────────────────┤
  │ Measurement progress: ████████░░ │
  │ Time remaining: 3 seconds        │
  ├──────────────────────────────────┤
  │ Samples: 15/15  Stability: OK    │
  ├──────────────────────────────────┤
  │  [Start] [Stop]   [Back]         │
  └──────────────────────────────────┘

Key Methods:
  - _validate_temperature() - Outlier check
  - _calculate_average() - Exponential moving average
  - _map_to_color() - Status color coding
  - _on_measurement_complete() - Result handling
```

#### `bp_measurement_screen.py` (636 lines)
```
Purpose: Blood Pressure measurement (Oscillometric)
State Machine:
  IDLE → INFLATE → ACQUIRE → DEFLATE → ANALYZE → RESULT
  
Layout (3 rows × varying height):
  Row 1: Header toolbar (ĐÓHUYẾT ÁP, back button) - dp(30)
  
  Row 2: Status display (2 columns)
    ┌──────────────┬──────────────┐
    │ Pressure     │ State        │ dp(70)
    │ 0 mmHg       │ Idle         │
    ├──────────────┼──────────────┤
    
  Row 3: Results grid (2×2)
    ┌──────────┬──────────┐
    │ SYS      │ DIA      │ dp(50)
    │ -- mmHg  │ -- mmHg  │
    ├──────────┼──────────┤
    │ MAP      │ HR       │ dp(50)
    │ -- mmHg  │ -- bpm   │
    └──────────┴──────────┘
    
  Row 4: Progress bar (measurement duration) - dp(8)
  
  Row 5: Control buttons - dp(40)
    [Start Measurement] [Stop] [Back]

Key Features:
  ✅ Real-time pressure display
  ✅ State visualization
  ✅ Oscillation detection & analysis
  ✅ SYS/DIA/MAP calculation (ratio-based)
  ✅ AHA color coding:
     - Normal: Green (<120/<80)
     - Elevated: Yellow (120-129/<80)
     - High: Red (≥130/≥80)
  ✅ Motor control (pump/valve)
  ✅ Safety limits (max 200 mmHg)
  ✅ Timeout protection
  ✅ TTS guidance ("Inflate now", "Deflating", etc.)
  
Measurement Flow:
  1. User presses [Start]
  2. Pump activates (GPIO 26)
  3. Pressure rises while reading ADC
  4. Max pressure reached (user-configured, ~165 mmHg)
  5. Valve opens (GPIO 16), slow deflation
  6. Peak detection on oscillations
  7. SYS = 50% of max amplitude
  8. DIA = 80% of max amplitude
  9. MAP = pressure at max amplitude
  10. Display results
  11. MQTT publish + SQLite save
```

#### `history_screen.py` (595 lines)
```
Purpose: Browse and filter measurement history
Layout:
  ┌──────────────────────────────────┐
  │ [Date Filter] [Type Filter]      │ dp(40)
  ├──────────────────────────────────┤
  │ Scrollable List:                 │
  │ ┌──────────────────────────────┐ │
  │ │ 14:30 | 78 | 97% | 36.7°C   │ │ dp(78)
  │ │ HR | SpO2 | Temp | BP OK    │ │
  │ │ 120/80 | Alert: None        │ │
  │ ├──────────────────────────────┤ │
  │ │ 13:15 | 85 | 95% | 35.9°C   │ │
  │ │ HR ▲ | SpO2 ▼ | Temp OK | ⚠️ │
  │ │ 140/92 | Alert: High BP     │ │
  │ └──────────────────────────────┘ │
  │ ... (scrollable)                 │
  └──────────────────────────────────┘

Key Features:
  ✅ Query SQLite history
  ✅ Color-coded status (normal/warning/critical)
  ✅ Alert indicators
  ✅ Tap to expand (detail view)
  ✅ Filter by date range
  ✅ Sort by time/value
  ✅ Search by alert type
  
Callbacks:
  - on_record_tap() → Expand details
  - apply_date_filter() → Query update
  - apply_alert_filter() → Query update
  - export_selected() → CSV export
```

#### `settings_screen.py` (822 lines)
```
Purpose: Configuration and system settings
Layout (scrollable):
  ┌──────────────────────────────────┐
  │ SENSOR CALIBRATION               │
  │ ├─ HX710B Offset      [Slider]   │
  │ ├─ HX710B Slope       [Slider]   │
  │ └─ Temperature Offset [Slider]   │
  ├──────────────────────────────────┤
  │ THRESHOLDS                       │
  │ ├─ HR Normal       [50 - 100]    │
  │ ├─ HR Critical     [< 40 >120]   │
  │ ├─ SpO2 Normal     [95 - 100%]   │
  │ ├─ SpO2 Critical   [< 92%]       │
  │ ├─ Temp Normal     [36 - 37.5°C] │
  │ ├─ Temp Critical   [< 35 >38.5°C]│
  │ ├─ BP Normal       [< 120/80]    │
  │ └─ BP Critical     [≥ 140/90]    │
  ├──────────────────────────────────┤
  │ MQTT CONNECTION                  │
  │ ├─ Status          🟢 Online     │
  │ ├─ Broker          hivemq.cloud  │
  │ ├─ Device ID       rpi_bp_001    │
  │ ├─ Reconnect Delay [5s]          │
  │ └─ [Test Connection]             │
  ├──────────────────────────────────┤
  │ CLOUD SYNC                       │
  │ ├─ Status          🟢 Synced     │
  │ ├─ Last Sync       2 mins ago    │
  │ ├─ Records Queued  0             │
  │ ├─ Sync Interval   [300s]        │
  │ └─ [Sync Now]                    │
  ├──────────────────────────────────┤
  │ AUDIO SETTINGS                   │
  │ ├─ Voice Enabled   [Toggle]      │
  │ ├─ Volume          [████████░░] │
  │ ├─ Language        [Vietnamese]  │
  │ └─ [Test Voice]                  │
  ├──────────────────────────────────┤
  │ SYSTEM INFO                      │
  │ ├─ Version         2.0.0         │
  │ ├─ OS              Pi OS Bookworm│
  │ ├─ Uptime          12 hours      │
  │ ├─ Memory Usage    45%           │
  │ ├─ Database Size   15 MB         │
  │ └─ [View Logs]                   │
  └──────────────────────────────────┘

Key Features:
  ✅ Live MQTT status
  ✅ Cloud sync controls
  ✅ Threshold customization
  ✅ Sensor calibration
  ✅ Voice settings
  ✅ Connection testing
  ✅ Manual sync trigger
  ✅ Log viewer
  ✅ System information
  ✅ Settings persistence
```

#### `mqtt_integration.py` (370 lines)
```
Purpose: GUI ↔ MQTT integration helper
Key Class: GUIMQTTIntegration
  
Responsibilities:
  ✅ Convert measurement → VitalsPayload
  ✅ Publish vitals to MQTT broker
  ✅ Publish alerts on threshold breach
  ✅ Handle device-centric patient resolution
  ✅ Track measurement sessions
  ✅ Error logging & retry
  
Key Methods:
  - publish_vitals_from_measurement()
    Input: Measurement data dict
    Output: MQTT publish to iot_health/device/{device_id}/vitals
    Format: VitalsPayload JSON
    QoS: 1 (at least once)
    
  - publish_alert_from_threshold_check()
    Input: Alert type, severity, values, message
    Output: MQTT publish to iot_health/device/{device_id}/alerts
    Format: AlertPayload JSON
    QoS: 2 (exactly once)
    
  - publish_status()
    Input: Device status (online/offline, battery, sensors)
    Output: MQTT publish to iot_health/device/{device_id}/status
    Format: DeviceStatusPayload JSON
    QoS: 0 (fire and forget)
    Retained: true (LWT)
```

---

### **Sensor Layer - 2,200+ lines**

#### `base_sensor.py` (~150 lines)
```python
Purpose: Abstract base class for all sensors
Key Interface:
  
class BaseSensor:
    def __init__(self, name, config)
    def initialize() → bool
    def start() → bool
    def stop() → bool
    def set_data_callback(callback) → None
    def get_status() → Dict[str, Any]
    def on_data_ready(sensor_data)  # Called by subclass
    
Callback Signature:
    def callback(sensor_data: Dict[str, Any]) → None
        sensor_data = {
            'timestamp': float (Unix epoch),
            'sensor_name': str,
            'measurements': {...},
            'metadata': {...}
        }

Thread Safety:
  ✅ Callback execution in sensor thread
  ✅ GUI must handle thread-safe updates (Clock.schedule_once)
```

#### `max30102_sensor.py` (~400 lines)
```python
Purpose: Heart Rate & SpO2 sensor driver
Hardware:
  - Sensor: MAX30102 (I2C 0x57)
  - Sampling: 100 Hz
  - Output: PPG signal, HR, SpO2, Signal Quality Index
  
Measurement Flow:
  1. Initialize I2C communication
  2. Enable LED (red + IR)
  3. Set sampling rate (100 Hz)
  4. Read FIFO buffer continuously
  5. Apply signal processing:
     - Butterworth filter (DC removal)
     - Peak detection
     - HR calculation (beats per minute)
     - SpO2 calculation (ratio-metric method)
  6. Calculate Signal Quality Index (SQI):
     - Peak height
     - Noise floor
     - Ratio consistency
  7. Callback with results every 1-2 seconds
  
Data Output:
  {
    'hr': int (60-160 bpm),
    'spo2': int (90-100 %),
    'sqi': float (0-100, signal quality),
    'peaks': int (peak count in window),
    'measurement_duration': float (seconds)
  }
  
Thresholds:
  ✅ HR: 60-100 normal, <50 or >120 alert
  ✅ SpO2: 95-100 normal, <92 critical
```

#### `mlx90614_sensor.py` (~150 lines)
```python
Purpose: Infrared thermometer (temperature) sensor
Hardware:
  - Sensor: MLX90614 (I2C 0x5A)
  - Accuracy: ±0.5°C
  - Range: -70 to +380°C (we use 0-50°C)
  
Measurement:
  1. Read object temperature (infrared)
  2. Read ambient temperature (internal sensor)
  3. Apply emissivity correction (default: 1.0)
  4. Validate reading (±0.7°C from last)
  5. Callback with result
  
Data Output:
  {
    'object_temp': float (°C),
    'ambient_temp': float (°C),
    'emissivity': float
  }

Thresholds:
  ✅ Normal: 36.0 - 37.5°C
  ✅ Warning: 35.0 - 36.0 or 37.5 - 38.0°C
  ✅ Critical: <35.0 or >38.5°C
```

#### `blood_pressure_sensor.py` (~400 lines)
```python
Purpose: Oscillometric blood pressure measurement orchestrator
State Machine:
  ┌─────────────────────────────────────────────┐
  │ State Machine for BP Measurement            │
  ├─────────────────────────────────────────────┤
  │ IDLE (0):    Cuff deflated, ready           │
  │ INFLATE (1): Pump active, pressure rising   │
  │ ACQUIRE (2): Reading oscillations           │
  │ DEFLATE (3): Deflating, analyzing           │
  │ ANALYZE (4): Calculating results            │
  │ RESULT (5):  Results ready, wait for user   │
  └─────────────────────────────────────────────┘

Key Features:
  ✅ Motor control (pump: GPIO 26, valve: GPIO 16)
  ✅ ADC readback (HX710B via GPIO 5/17)
  ✅ Oscillation detection & peak analysis
  ✅ SYS/DIA/MAP calculation
  ✅ Safety timeouts & pressure limits
  ✅ Signal quality assessment
  ✅ Automatic deflation

Configuration (from app_config.yaml):
  inflate_target_mmhg: 165       # Stop inflate at this pressure
  deflate_rate_mmhg_s: 3.0       # Slow deflation rate
  max_pressure_mmhg: 200         # Safety cutoff
  pump_gpio: 26
  valve_gpio: 16
  sys_frac: 0.5   # SYS at 50% of max amplitude
  dia_frac: 0.8   # DIA at 80% of max amplitude
  
Data Output:
  BloodPressureMeasurement(
    systolic: int (80-200 mmHg),
    diastolic: int (40-150 mmHg),
    map: int (60-180 mmHg),
    heart_rate: int (40-200 bpm),
    measurement_time: float (seconds),
    quality: str ('good', 'fair', 'poor')
  )
```

#### `hx710b_driver.py` (~400 lines)
```python
Purpose: Low-level HX710B 24-bit ADC driver (bit-bang protocol)
Hardware:
  - Protocol: 2-wire (not I2C/SPI)
  - DOUT pin (GPIO 17): Data ready + output
  - SCK pin (GPIO 5): Clock input (pulse to read)
  
Bit-bang Protocol:
  1. Wait for DOUT to go LOW (data ready)
  2. Pull SCK HIGH, then LOW (1 clock cycle)
  3. Repeat 24 times to shift out 24 bits
  4. Use power-down mode selection:
     - Gain 128: SCK LOW (25 pulses)
     - Gain 64:  SCK HIGH (25 pulses)
     - Gain 32:  SCK HIGH (25-26 pulses)

Characteristics:
  ✅ 10-80 SPS (samples per second) depending on board
  ✅ 24-bit resolution (~0.001 mmHg per LSB)
  ✅ Differential input (between cuff and ground)
  ✅ Internal PGA (programmable gain amplifier)
  ✅ Onboard calibration (offset)

Key Methods:
  - read_adc() → int (24-bit count value)
  - wait_data_ready(timeout) → bool
  - set_gain(gain) → void
  - to_pressure(counts) → float (mmHg)
    Uses calibration: pressure = (counts - offset) * slope
    
Safety:
  ✅ Timeout protection (1s default)
  ✅ Debounce reads
  ✅ Checksum validation
  ✅ Non-blocking with callback
```

#### `hx710b_sensor.py` (~150 lines)
```python
Purpose: HX710B sensor adapter (implements BaseSensor)
Wrapper around hx710b_driver.py
  
Key Methods:
  - initialize() → bool
    ├─ Set GPIO directions
    ├─ Configure ADC gain
    ├─ Load calibration (offset/slope)
    └─ Start background thread
    
  - set_data_callback() → void
    └─ Register callback for new readings
    
  - read_sample() → float (mmHg)
    ├─ Call driver.read_adc()
    ├─ Convert to pressure
    └─ Return value
```

---

### **Communication Layer - 2,000+ lines**

#### `mqtt_client.py` (~500 lines)
```python
Purpose: MQTT client for HiveMQ Cloud broker
Key Class: IoTHealthMQTTClient

Initialization:
  broker: c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud
  port: 8883 (TLS required)
  keepalive: 60 seconds
  
Connection Management:
  ✅ Auto-reconnect (exponential backoff: 5s, 10s, 30s, 60s)
  ✅ Last Will & Testament (LWT) for offline status
  ✅ Clean session flag
  ✅ TLS/SSL certificate validation
  
Publishing:
  - publish_vitals(payload) → bool
    Topic: iot_health/device/{device_id}/vitals
    QoS: 1 (at least once)
    Retained: false
    
  - publish_alerts(payload) → bool
    Topic: iot_health/device/{device_id}/alerts
    QoS: 2 (exactly once)
    Retained: false
    
  - publish_status(payload) → bool
    Topic: iot_health/device/{device_id}/status
    QoS: 0 (fire and forget)
    Retained: true (for LWT)

Subscribing:
  - subscribe_commands() → void
    Topic: iot_health/patient/{patient_id}/commands
    QoS: 2
    Callback: on_command_received()
    
    Commands:
      - start_measurement: {"measurement_type": "blood_pressure"}
      - stop_measurement: {}
      - update_thresholds: {"vital_sign": "heart_rate", "min": 60, "max": 100}
      - calibrate_sensor: {"sensor": "hx710b", ...}

Error Handling:
  ✅ Reconnection on disconnect
  ✅ Queue messages if offline
  ✅ Log publish failures
  ✅ Retry with exponential backoff
  
Performance:
  ✅ Async pub/sub (non-blocking)
  ✅ Connection pooling
  ✅ Message batching optional
```

#### `mqtt_payloads.py` (~300 lines)
```python
Purpose: Payload schemas for MQTT messages
Key Classes:

1. VitalsPayload:
   {
     "timestamp": 1699518000.123,
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
       "spo2": {...},
       "temperature": {...},
       "blood_pressure": {...}
     }
   }

2. AlertPayload:
   {
     "timestamp": 1699518000.123,
     "device_id": "rpi_bp_001",
     "patient_id": "patient_001",
     "alert_type": "high_heart_rate",
     "severity": "high",
     "message": "Nhịp tim cao: 125 BPM",
     "vital_sign": "heart_rate",
     "current_value": 125,
     "threshold_value": 100
   }

3. DeviceStatusPayload:
   {
     "timestamp": 1699518000.123,
     "device_id": "rpi_bp_001",
     "status": "online",
     "uptime_seconds": 86400,
     "battery_level": 85,
     "wifi_signal": -45
   }

4. CommandPayload:
   {
     "command_id": "cmd_1699518000",
     "timestamp": 1699518000.123,
     "issuer": "android_app",
     "command": "start_measurement",
     "parameters": {...}
   }

Serialization:
  ✅ JSON encoding/decoding
  ✅ Type validation
  ✅ Schema compliance
  ✅ Timestamp normalization
```

#### `cloud_sync_manager.py` (~400 lines)
```python
Purpose: SQLite ↔ MySQL cloud synchronization
Key Class: CloudSyncManager

Sync Strategy (Device-Centric):
  1. Read local SQLite records (status: pending)
  2. Batch into groups of 100
  3. Send to MySQL (INSERT or UPDATE)
  4. Mark as synced in local DB
  5. Retry failed records on next sync
  
Sync Interval:
  - Auto mode: every 5 minutes (configurable)
  - Manual: on demand via settings
  - Conflict resolution: cloud_wins
  
MySQL Tables:
  - health_records
  - alerts
  - sensor_calibrations
  - patients
  - devices
  
Retry Strategy:
  ✅ Max 3 retry attempts
  ✅ Exponential backoff (60s base)
  ✅ Queue failed records for next cycle
  ✅ Log all failures for debugging
  
Error Handling:
  ✅ Network timeouts
  ✅ Authentication failures
  ✅ Database constraints
  ✅ Partial sync failures
  
Performance:
  ✅ Batch insert (100 records per request)
  ✅ Async sync (doesn't block UI)
  ✅ Compress data for transfer
  ✅ Local queue if offline
```

#### `rest_client.py` (~150 lines)
```python
Purpose: REST API client for historical data queries
Endpoints:
  
  GET /api/v1/health-records
    Query params: device_id, date_from, date_to, limit
    Returns: List of health records
    
  GET /api/v1/alerts
    Query params: device_id, severity, limit
    Returns: List of alerts
    
  POST /api/v1/sync
    Body: {records: [...]}
    Returns: {success: bool, count: int}

Authentication:
  ✅ API key header
  ✅ Token-based (future)
  
Timeout:
  ✅ 5 seconds default
  ✅ Retry on connection error
```

#### `sync_scheduler.py` (~100 lines)
```python
Purpose: Schedule automatic cloud sync
Scheduler:
  ✅ APScheduler or schedule library
  ✅ Run every 5 minutes (configurable)
  ✅ Non-blocking background task
  ✅ Handle missed sync gracefully

Triggers:
  - Periodic: every N seconds
  - On-demand: manual via GUI
  - On measurement: after each measurement
  - On alert: immediately publish alerts
```

#### `store_forward.py` (~150 lines)
```python
Purpose: Message queue for offline resilience
Queue Strategy:
  ✅ SQLite queue table
  ✅ Max 1000 pending messages
  ✅ FIFO (first in, first out)
  ✅ Automatic retry on reconnect
  
Operations:
  - enqueue_vitals(payload)
  - enqueue_alert(payload)
  - flush_queue()  # On network reconnect
  - get_queue_stats()
  
Persistence:
  ✅ Queue survives power cycles
  ✅ Deduplicate on flush
  ✅ Log all operations
```

---

### **Data Layer - 1,500+ lines**

#### `database.py` (~800 lines)
```python
Purpose: SQLite local database management
Key Class: DatabaseManager

Tables:
  1. health_records
     Columns: id, device_id, patient_id, timestamp, hr, spo2, temp, 
              systolic, diastolic, map, alert, sync_status, ...
  
  2. alerts
     Columns: id, device_id, patient_id, alert_type, severity, message,
              vital_sign, current_value, threshold_value, timestamp, ...
  
  3. patients
     Columns: patient_id, name, age, gender, device_id, ...
  
  4. sensor_calibrations
     Columns: device_id, sensor_name, offset, slope, calibration_date, ...
  
  5. sync_queue
     Columns: id, table_name, operation, record_id, data_snapshot, 
              sync_attempts, created_at, ...

Operations:
  ✅ INSERT health_records
  ✅ Query by date range
  ✅ Query by patient
  ✅ Aggregate statistics
  ✅ Delete old records (retention policy)
  ✅ Backup before critical operations
  
Performance:
  ✅ Indexed on (device_id, timestamp)
  ✅ Indexed on patient_id
  ✅ Batch inserts (100 at a time)
  ✅ Connection pooling
  ✅ Query caching (5 min)
  
Backup:
  ✅ Daily backups
  ✅ Keep 7 days of backups
  ✅ Path: data/backups/health_monitor.db.backup_YYYYMMDD_HHMMSS
```

#### `models.py` (~200 lines)
```python
Purpose: Data models (SQLAlchemy ORM)
Key Models:

class HealthRecord:
    id: int
    device_id: str
    patient_id: str
    timestamp: datetime
    heart_rate: int
    spo2: int
    temperature: float
    systolic: int
    diastolic: int
    map: int
    alert: Optional[str]
    sync_status: str ('pending', 'synced', 'failed')

class Alert:
    id: int
    device_id: str
    patient_id: str
    alert_type: str
    severity: str ('info', 'warning', 'critical')
    message: str
    timestamp: datetime
    acknowledged: bool
    
class Patient:
    patient_id: str
    name: str
    age: int
    gender: str
    emergency_contact: str
    
class SensorCalibration:
    device_id: str
    sensor_name: str
    offset: float
    slope: float
    calibration_date: datetime
```

#### `processor.py` (~200 lines)
```python
Purpose: Data processing & validation
Key Functions:

- validate_heart_rate(value) → bool
  ✅ Range: 40-200 bpm
  ✅ Check for outliers
  ✅ Consistency with previous reading

- validate_temperature(value) → bool
  ✅ Range: 34-40°C
  ✅ Deviation: ±1°C from previous
  
- validate_blood_pressure(sys, dia) → bool
  ✅ SYS range: 70-200 mmHg
  ✅ DIA range: 40-140 mmHg
  ✅ SYS >= DIA (always)
  
- detect_anomalies(data) → List[str]
  ✅ Use Isolation Forest
  ✅ Return anomaly reasons
  
- calculate_statistics(records) → Dict
  ✅ Mean, median, std dev
  ✅ Daily trends
  ✅ Weekly averages
```

#### `database_extensions.py` (~100 lines)
```python
Purpose: Extended database operations
Key Functions:

- migrate_schema(version) → bool
  ✅ Add new columns
  ✅ Modify indices
  ✅ Backward compatible

- export_to_csv(date_range) → str
  ✅ Path to generated CSV file
  
- cleanup_old_records(days) → int
  ✅ Count of deleted records
```

---

### **AI/Alerts Layer - 800+ lines**

#### `alert_system.py` (~300 lines)
```python
Purpose: Real-time alert generation & management
Key Class: AlertSystem

Thresholds (from config):
  Heart Rate:
    - Normal: 60-100 bpm
    - Warning: 50-59 or 101-120 bpm
    - Critical: <50 or >120 bpm
    
  SpO2:
    - Normal: 95-100%
    - Warning: 92-94%
    - Critical: <92%
    
  Temperature:
    - Normal: 36.0-37.5°C
    - Warning: 35.0-35.9 or 37.6-38.4°C
    - Critical: <35.0 or >38.5°C
    
  Blood Pressure (AHA):
    - Normal: SYS <120 AND DIA <80
    - Elevated: SYS 120-129 AND DIA <80
    - High: SYS ≥130 OR DIA ≥80

Alert Flow:
  1. Measurement completed
  2. Check against thresholds
  3. If breach: create alert
  4. Log to SQLite
  5. Publish via MQTT (QoS 2)
  6. TTS voice alert
  7. Show UI notification

Debounce:
  ✅ 30s debounce (don't repeat same alert)
  ✅ Avoid alert spam
```

#### `anomaly_detector.py` (~200 lines)
```python
Purpose: ML-based anomaly detection
Algorithm: Isolation Forest

Training:
  ✅ Learn from historical data
  ✅ Periodically retrain (weekly)
  ✅ Adapt to patient baseline
  
Detection:
  ✅ Flag unusual measurements
  ✅ Not an immediate alert
  ✅ Store anomaly flag in DB
  ✅ Display as info to user

Example:
  User normally: HR 60-80, SpO2 97-99%
  Today: HR 45 (low) → Anomaly detected
  Recommendation: Show to user as "unusual for you"
```

#### `trend_analyzer.py` (~200 lines)
```python
Purpose: Statistical trend analysis
Metrics:

- Daily trends
  ✅ Morning vs evening HR
  ✅ Temperature patterns
  ✅ SpO2 stability
  
- Weekly trends
  ✅ 7-day moving average
  ✅ Workday vs weekend
  ✅ Peak values
  
- Monthly trends
  ✅ 30-day trend line
  ✅ Variance analysis
  ✅ Correlation between metrics

Visualization (future):
  ✅ Line charts
  ✅ Trend arrows (↑ ↓ →)
  ✅ Forecast (ML prediction)
```

#### `chatbot_interface.py` (~100 lines)
```python
Purpose: Future AI chatbot for health insights
Status: Placeholder (not yet implemented)

Planned Features:
  ✅ Natural language queries
  ✅ Health recommendations
  ✅ Symptom checker
  ✅ Integration with LLM
```

---

### **Utilities Layer - 800+ lines**

#### `tts_manager.py` (~300 lines)
```python
Purpose: Text-to-speech with PiperTTS (Vietnamese)
Key Class: TTSManager

Scenarios (ScenarioID):
  - SYSTEM_START: "Hệ thống khởi động thành công"
  - SYSTEM_SHUTDOWN: "Hệ thống tắt"
  - MEASUREMENT_START: "Bắt đầu đo"
  - MEASUREMENT_COMPLETE: "Đo hoàn tất"
  - HR_NORMAL: "Nhịp tim bình thường"
  - HR_HIGH: "Cảnh báo: Nhịp tim cao"
  - HR_LOW: "Cảnh báo: Nhịp tim thấp"
  - etc.

Voice Engine:
  ✅ PiperTTS (offline, Vietnamese)
  ✅ Model: vi_VN-vais1000-medium.onnx
  ✅ Audio output: Speaker via MAX98357A
  ✅ Cache generated audio to /asset/tts/
  
Methods:
  - speak_scenario(scenario_id) → void
  - speak_custom(text, language) → void
  - set_volume(level) → void
  - stop() → void

Configuration:
  audio:
    voice_enabled: true
    tts_engine: piper
    locale: vi
    volume: 80
```

#### `logger.py` (~100 lines)
```python
Purpose: Structured logging
Configuration:
  - Log level: DEBUG/INFO/WARNING/ERROR
  - Format: [TIMESTAMP] [LEVEL] [MODULE] [FUNCTION] - MESSAGE
  - File: logs/health_monitor_YYYYMMDD.log
  - Max file size: 10 MB (rotate)
  - Retention: 30 days

Example:
  logger.info("📡 Connected to MQTT broker")
  logger.error("❌ Sensor initialization failed", exc_info=True)
  logger.debug("HR reading: 78 bpm (SQI: 89.5)")
```

#### `audio_converter.py` (~100 lines)
```python
Purpose: Audio format conversion & processing
Supported Formats:
  ✅ WAV (input/output)
  ✅ MP3 (input only)
  ✅ OGG (input only)

Operations:
  - convert_to_wav()
  - adjust_volume()
  - normalize_audio()
```

#### `health_validators.py` (~150 lines)
```python
Purpose: Validate health measurements
Key Functions:

- validate_heart_rate(value, age) → (bool, str)
  ✅ Check range
  ✅ Check consistency
  ✅ Age-adjusted thresholds

- validate_spo2(value) → (bool, str)
  ✅ Range 85-100%
  ✅ Warn if <92%

- validate_temperature(value) → (bool, str)
  ✅ Range 34-40°C
  ✅ Deviation check

- validate_blood_pressure(sys, dia) → (bool, str)
  ✅ Range checks
  ✅ AHA classification
```

#### `decorators.py` (~50 lines)
```python
Purpose: Utility decorators
Key Decorators:

@retry(max_attempts=3, delay=1)
  ✅ Auto-retry on exception
  ✅ Exponential backoff

@timer
  ✅ Log execution time
  ✅ Warn if > threshold

@thread_safe
  ✅ Lock-based synchronization
```

---

## 📊 **Overall Statistics**

| Component | Files | Lines | Purpose |
|-----------|-------|-------|---------|
| **GUI** | 8 | 5,410 | Kivy screens & app |
| **Sensors** | 7 | 2,200 | Hardware drivers |
| **Communication** | 7 | 2,000 | MQTT & cloud sync |
| **Data** | 4 | 1,500 | Database operations |
| **AI/Alerts** | 4 | 800 | Anomaly detection |
| **Utils** | 7 | 800 | Logging, TTS, validation |
| **Config** | 1 | 288 | YAML configuration |
| **Main** | 1 | 1,000+ | Entry point |
| **Total** | **39** | **~14,000** | **Full system** |

---

**Generated by:** GitHub Copilot  
**Date:** 28/11/2025  
**System Version:** 2.0.0
