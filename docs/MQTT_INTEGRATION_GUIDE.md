# 🔌 MQTT Integration Guide - Main App

## **Tổng quan**

Guide này hướng dẫn tích hợp `IoTHealthMQTTClient` vào `main_app.py` để publish sensor data và handle remote commands.

---

## **1. Import và Initialization**

### **1.1. Update imports trong `main_app.py`**

```python
from src.communication.mqtt_client import IoTHealthMQTTClient
from src.communication.mqtt_payloads import (
    VitalsPayload,
    AlertPayload,
    DeviceStatusPayload,
    HRMetrics,
    SpO2Metrics,
    TemperatureMetrics,
    BPMetrics,
    BPRawMetrics
)
```

### **1.2. Initialize MQTT client trong `HealthMonitorApp.__init__`**

```python
class HealthMonitorApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # ... existing code ...
        
        # Initialize MQTT client
        try:
            self.mqtt_client = IoTHealthMQTTClient(self.config)
            self.logger.info("MQTT client initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize MQTT client: {e}")
            self.mqtt_client = None
    
    def build(self):
        # ... existing code ...
        
        # Connect to MQTT broker
        if self.mqtt_client:
            try:
                self.mqtt_client.connect()
                self.logger.info("MQTT connection initiated")
                
                # Subscribe to commands
                self.mqtt_client.subscribe_to_commands(
                    callback=self._handle_mqtt_command
                )
            except Exception as e:
                self.logger.error(f"MQTT connection failed: {e}")
        
        return self.sm
    
    def on_stop(self):
        """Called khi app đóng"""
        # Disconnect MQTT
        if self.mqtt_client:
            self.mqtt_client.disconnect()
        
        # ... existing cleanup code ...
```

---

## **2. Publishing Vitals Data**

### **2.1. Publish khi BP measurement hoàn thành**

Trong `bp_measurement_screen.py` → `_handle_result_on_main_thread()`:

```python
def _handle_result_on_main_thread(self, result: BloodPressureMeasurement):
    """
    Xử lý kết quả đo BP trên main thread (thread-safe)
    """
    try:
        # ... existing result processing ...
        
        # ===== MQTT PUBLISH =====
        self._publish_bp_vitals_to_mqtt(result)
        
    except Exception as e:
        self.logger.error(f"Error handling result: {e}")
```

### **2.2. Helper method để tạo VitalsPayload**

Thêm vào `bp_measurement_screen.py`:

```python
def _publish_bp_vitals_to_mqtt(self, bp_result: BloodPressureMeasurement):
    """
    Publish BP measurement đến MQTT broker
    
    Args:
        bp_result: BloodPressureMeasurement từ sensor
    """
    try:
        mqtt_client = MDApp.get_running_app().mqtt_client
        if not mqtt_client or not mqtt_client.is_connected:
            self.logger.warning("MQTT client not available - skipping publish")
            return
        
        # Get latest HR/SpO2 from MAX30102
        hr_sensor = MDApp.get_running_app().hr_sensor
        hr = hr_sensor.latest_hr if hr_sensor else None
        spo2 = hr_sensor.latest_spo2 if hr_sensor else None
        
        # Get temperature from MLX90614
        temp_sensor = MDApp.get_running_app().temp_sensor
        temp_obj = temp_sensor.object_temp if temp_sensor else None
        temp_amb = temp_sensor.ambient_temp if temp_sensor else None
        
        # Extract BP metadata
        metadata = bp_result.metadata or {}
        hx710b_data = metadata.get('hx710b', {})
        
        # Build BPRawMetrics
        bp_raw = BPRawMetrics(
            pulse_pressure=bp_result.systolic - bp_result.diastolic,
            heart_rate_bp=bp_result.heart_rate,
            max_pressure_reached=metadata.get('max_pressure', 0.0),
            deflate_rate_actual=metadata.get('deflate_rate', 0.0),
            oscillation_amplitude=metadata.get('oscillation_amplitude', 0.0),
            envelope_quality=metadata.get('envelope_quality', 0.0),
            hx710b_max_counts=hx710b_data.get('max_counts', 0),
            hx710b_map_counts=hx710b_data.get('map_counts', 0),
            hx710b_samples_collected=hx710b_data.get('samples', 0),
            hx710b_sampling_rate=hx710b_data.get('sps', 0.0),
            hx710b_offset_counts=hx710b_data.get('offset', 0),
            hx710b_slope_mmhg_per_count=hx710b_data.get('slope', 0.0),
            aami_validation=metadata.get('aami_validation', {})
        )
        
        # Build BPMetrics
        bp_metrics = BPMetrics(
            systolic=bp_result.systolic,
            diastolic=bp_result.diastolic,
            mean_arterial_pressure=bp_result.map,
            confidence=bp_result.confidence,
            quality_score=bp_result.quality_score,
            measurement_duration=metadata.get('duration', 0.0),
            raw_metrics=bp_raw
        )
        
        # Build VitalsPayload
        vitals = VitalsPayload.from_measurement(
            timestamp=time.time(),
            device_id=mqtt_client.device_id,
            patient_id=mqtt_client.patient_id,
            hr=hr,
            spo2=spo2,
            temp_object=temp_obj,
            temp_ambient=temp_amb,
            bp_metrics=bp_metrics,
            session_id=metadata.get('session_id', 'bp_' + str(int(time.time())))
        )
        
        # Publish
        success = mqtt_client.publish_vitals(vitals)
        if success:
            self.logger.info("✅ BP vitals published to MQTT")
        else:
            self.logger.error("❌ Failed to publish BP vitals")
    
    except Exception as e:
        self.logger.error(f"Error publishing BP vitals to MQTT: {e}")
```

### **2.3. Publish periodic vitals (HR/SpO2/Temp)**

Trong `dashboard_screen.py`, thêm scheduled publish mỗi 30 giây:

```python
from kivy.clock import Clock

class DashboardScreen(MDScreen):
    def on_enter(self):
        """Called when screen is displayed"""
        super().on_enter()
        
        # ... existing code ...
        
        # Schedule periodic MQTT publish (every 30s)
        self.mqtt_publish_event = Clock.schedule_interval(
            self._publish_vitals_periodic,
            30.0  # 30 seconds
        )
    
    def on_leave(self):
        """Called when leaving screen"""
        # Cancel scheduled events
        if hasattr(self, 'mqtt_publish_event'):
            self.mqtt_publish_event.cancel()
        
        super().on_leave()
    
    def _publish_vitals_periodic(self, dt):
        """
        Publish current vitals to MQTT (scheduled task)
        
        Args:
            dt: Delta time (từ Clock.schedule_interval)
        """
        try:
            app = MDApp.get_running_app()
            mqtt_client = app.mqtt_client
            
            if not mqtt_client or not mqtt_client.is_connected:
                self.logger.debug("MQTT not connected - skipping periodic publish")
                return
            
            # Get current sensor values
            hr = app.hr_sensor.latest_hr if app.hr_sensor else None
            spo2 = app.hr_sensor.latest_spo2 if app.hr_sensor else None
            temp_obj = app.temp_sensor.object_temp if app.temp_sensor else None
            temp_amb = app.temp_sensor.ambient_temp if app.temp_sensor else None
            
            # Skip if no data
            if all(v is None for v in [hr, spo2, temp_obj]):
                self.logger.debug("No sensor data available - skipping publish")
                return
            
            # Build minimal vitals payload (no BP)
            vitals = VitalsPayload.from_measurement(
                timestamp=time.time(),
                device_id=mqtt_client.device_id,
                patient_id=mqtt_client.patient_id,
                hr=hr,
                spo2=spo2,
                temp_object=temp_obj,
                temp_ambient=temp_amb,
                bp_metrics=None,
                session_id=None
            )
            
            # Publish
            mqtt_client.publish_vitals(vitals)
            self.logger.debug("📤 Periodic vitals published")
        
        except Exception as e:
            self.logger.error(f"Error in periodic MQTT publish: {e}")
```

---

## **3. Publishing Alerts**

### **3.1. Trong `alert_system.py` → `_trigger_alert()`**

```python
def _trigger_alert(self, alert_data: Dict[str, Any]):
    """
    Trigger alert với TTS + UI + MQTT
    
    Args:
        alert_data: Alert information
    """
    try:
        # ... existing TTS/UI code ...
        
        # ===== MQTT PUBLISH ALERT =====
        self._publish_alert_to_mqtt(alert_data)
        
    except Exception as e:
        self.logger.error(f"Error triggering alert: {e}")

def _publish_alert_to_mqtt(self, alert_data: Dict[str, Any]):
    """
    Publish alert đến MQTT broker
    
    Args:
        alert_data: Dict chứa alert info
    """
    try:
        from src.communication.mqtt_payloads import AlertPayload
        
        app = MDApp.get_running_app()
        mqtt_client = app.mqtt_client
        
        if not mqtt_client or not mqtt_client.is_connected:
            self.logger.warning("MQTT not connected - alert not published")
            return
        
        # Get historical data cho trend analysis
        db = app.database
        recent_measurements = db.get_recent_measurements(limit=3)
        
        previous_measurements = []
        for m in recent_measurements:
            previous_measurements.append({
                'timestamp': m.get('timestamp'),
                'hr': m.get('hr'),
                'spo2': m.get('spo2'),
                'temp': m.get('temp'),
                'bp_sys': m.get('bp_sys'),
                'bp_dia': m.get('bp_dia')
            })
        
        # Build AlertPayload
        alert_payload = AlertPayload(
            timestamp=time.time(),
            device_id=mqtt_client.device_id,
            patient_id=mqtt_client.patient_id,
            alert_type=alert_data.get('type', 'unknown'),
            severity=alert_data.get('severity', 'medium'),
            current_measurement={
                'hr': alert_data.get('hr'),
                'spo2': alert_data.get('spo2'),
                'temp': alert_data.get('temp'),
                'bp_sys': alert_data.get('bp_sys'),
                'bp_dia': alert_data.get('bp_dia')
            },
            thresholds={
                'hr_min': 60,
                'hr_max': 100,
                'spo2_min': 95,
                'temp_max': 37.5,
                'bp_sys_max': 140,
                'bp_dia_max': 90,
                'source': 'AHA_2023'
            },
            trend={
                'previous_measurements': previous_measurements,
                'direction': alert_data.get('trend_direction', 'stable'),
                'rate_of_change': alert_data.get('rate_of_change', 0.0)
            },
            actions_taken=['tts_announcement', 'ui_popup', 'mqtt_publish', 'db_log'],
            recommendations=alert_data.get('recommendations', [])
        )
        
        # Publish with QoS 2 (exactly once)
        success = mqtt_client.publish_alert(alert_payload)
        if success:
            self.logger.warning("🚨 Alert published to MQTT")
    
    except Exception as e:
        self.logger.error(f"Error publishing alert to MQTT: {e}")
```

---

## **4. Publishing Device Status**

### **4.1. Scheduled status publish (every 5 minutes)**

Trong `main_app.py`:

```python
class HealthMonitorApp(MDApp):
    def build(self):
        # ... existing code ...
        
        # Schedule periodic status publish
        Clock.schedule_interval(self._publish_device_status, 300)  # Every 5 minutes
        
        return self.sm
    
    def _publish_device_status(self, dt):
        """
        Publish device status đến MQTT
        
        Args:
            dt: Delta time (từ Clock)
        """
        try:
            if not self.mqtt_client or not self.mqtt_client.is_connected:
                return
            
            from src.communication.mqtt_payloads import DeviceStatusPayload
            import psutil
            
            # Get battery info (if available)
            try:
                battery = psutil.sensors_battery()
                battery_level = battery.percent if battery else 100
                battery_voltage = 5.0  # Assume USB power
                battery_charging = battery.power_plugged if battery else True
            except:
                battery_level = 100
                battery_voltage = 5.0
                battery_charging = True
            
            # Get sensor status
            sensors_status = {
                'MAX30102': {
                    'operational': self.hr_sensor is not None,
                    'last_reading': time.time() if self.hr_sensor else None,
                    'error_count': 0
                },
                'MLX90614': {
                    'operational': self.temp_sensor is not None,
                    'last_reading': time.time() if self.temp_sensor else None,
                    'error_count': 0
                },
                'HX710B': {
                    'operational': True,  # Assume operational
                    'last_reading': time.time(),
                    'calibration_drift': 0.0,
                    'calibration_age_days': 30,
                    'performance_score': 0.95
                }
            }
            
            # Get system info
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Build DeviceStatusPayload
            status = DeviceStatusPayload(
                timestamp=time.time(),
                device_id=self.mqtt_client.device_id,
                battery={
                    'level': battery_level,
                    'voltage': battery_voltage,
                    'charging': battery_charging,
                    'health': 'good'
                },
                sensors=sensors_status,
                actuators={
                    'pump': {'gpio': 26, 'state': 'idle'},
                    'valve': {'gpio': 16, 'state': 'idle'}
                },
                system={
                    'cpu_usage': cpu_percent,
                    'memory_usage': memory.percent,
                    'disk_usage': disk.percent,
                    'uptime': time.time() - self.start_time,
                    'audio_output': 'MAX98357A',
                    'display_output': 'Waveshare_3.5inch'
                },
                network={
                    'wifi_connected': True,
                    'wifi_ssid': 'IoTHealth',
                    'wifi_signal_strength': -60,
                    'mqtt_connected': self.mqtt_client.is_connected
                }
            )
            
            # Publish with QoS 0 (fire and forget)
            self.mqtt_client.publish_status(status)
            self.logger.debug("📊 Device status published")
        
        except Exception as e:
            self.logger.error(f"Error publishing device status: {e}")
```

---

## **5. Handling Remote Commands**

### **5.1. Command handler trong `main_app.py`**

```python
class HealthMonitorApp(MDApp):
    def _handle_mqtt_command(self, topic: str, data: Dict[str, Any]):
        """
        Xử lý commands từ MQTT (web/mobile)
        
        Args:
            topic: MQTT topic
            data: Parsed command data
        """
        try:
            cmd = data.get('command')
            params = data.get('parameters', {})
            source = data.get('source', 'unknown')
            
            self.logger.info(f"📥 MQTT Command: {cmd} from {source}")
            
            if cmd == 'start_measurement':
                # Navigate to BP screen và start measurement
                self._handle_start_bp_command(params)
            
            elif cmd == 'calibrate_sensor':
                sensor_type = params.get('sensor_type')
                self._handle_calibrate_command(sensor_type, params)
            
            elif cmd == 'emergency_deflate':
                self._handle_emergency_deflate()
            
            else:
                self.logger.warning(f"Unknown MQTT command: {cmd}")
        
        except Exception as e:
            self.logger.error(f"Error handling MQTT command: {e}")
    
    def _handle_start_bp_command(self, params: Dict[str, Any]):
        """
        Handle start_measurement command từ remote
        
        Args:
            params: Command parameters (inflate_target, deflate_rate)
        """
        try:
            # Navigate to BP screen
            self.sm.current = 'bp_measurement'
            
            # Wait for screen to load
            Clock.schedule_once(
                lambda dt: self._trigger_bp_measurement(params),
                0.5
            )
        
        except Exception as e:
            self.logger.error(f"Error starting BP measurement: {e}")
    
    def _trigger_bp_measurement(self, params: Dict[str, Any]):
        """
        Trigger BP measurement với custom params
        
        Args:
            params: inflate_target_mmhg, deflate_rate_mmhg_s
        """
        try:
            bp_screen = self.sm.get_screen('bp_measurement')
            
            # Update params if provided
            if 'inflate_target_mmhg' in params:
                # Update BP sensor config
                self.bp_sensor.inflate_target = params['inflate_target_mmhg']
            
            if 'deflate_rate_mmhg_s' in params:
                self.bp_sensor.deflate_rate = params['deflate_rate_mmhg_s']
            
            # Start measurement
            bp_screen._start_measurement()
            
            self.logger.info("✅ BP measurement started from MQTT command")
        
        except Exception as e:
            self.logger.error(f"Error triggering BP measurement: {e}")
    
    def _handle_calibrate_command(self, sensor_type: str, params: Dict[str, Any]):
        """
        Handle calibrate_sensor command
        
        Args:
            sensor_type: 'HX710B', 'MAX30102', etc.
            params: Calibration parameters
        """
        self.logger.info(f"Calibration request for {sensor_type}: {params}")
        
        if sensor_type == 'HX710B':
            if 'zero_offset' in params:
                # Update HX710B offset
                self.bp_sensor.hx710b_driver.set_offset(params['zero_offset'])
            
            if 'slope' in params:
                # Update slope
                self.bp_sensor.hx710b_driver.set_slope(params['slope'])
            
            self.logger.info("✅ HX710B calibration updated from MQTT")
    
    def _handle_emergency_deflate(self):
        """
        Handle emergency_deflate command
        """
        self.logger.warning("⚠️ EMERGENCY DEFLATE triggered from MQTT!")
        
        if self.bp_sensor:
            self.bp_sensor.stop_measurement(emergency=True)
```

---

## **6. Testing MQTT Integration**

### **6.1. Test với mosquitto_sub**

**Terminal 1 - Monitor vitals:**

```bash
mosquitto_sub \
  -h localhost -p 8883 \
  --cafile config/certs/ca.crt \
  --cert config/certs/client.crt \
  --key config/certs/client.key \
  -u iot_health_device -P "SecureP@ssw0rd!" \
  -t "iot_health/device/+/vitals" -v | jq .
```

**Terminal 2 - Monitor alerts:**

```bash
mosquitto_sub \
  -h localhost -p 8883 \
  --cafile config/certs/ca.crt \
  --cert config/certs/client.crt \
  --key config/certs/client.key \
  -u iot_health_device -P "SecureP@ssw0rd!" \
  -t "iot_health/device/+/alerts" -v | jq .
```

### **6.2. Send test command**

```bash
mosquitto_pub \
  -h localhost -p 8883 \
  --cafile config/certs/ca.crt \
  --cert config/certs/client.crt \
  --key config/certs/client.key \
  -u web_dashboard -P "WebDashP@ss" \
  -t "iot_health/patient/P12345/commands" \
  -m '{
    "command": "start_measurement",
    "timestamp": 1234567890.5,
    "source": "web_dashboard",
    "parameters": {
      "inflate_target_mmhg": 180,
      "deflate_rate_mmhg_s": 3.0
    }
  }'
```

**Expected:** IoT device nhận command và start BP measurement.

---

## **7. Error Handling**

### **7.1. Handle MQTT disconnections**

MQTT client tự động reconnect với exponential backoff. App vẫn hoạt động bình thường khi offline, chỉ không publish data.

### **7.2. Store-and-Forward (Optional Enhancement)**

Nếu cần lưu messages khi offline:

```python
class HealthMonitorApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Message queue for offline buffering
        self.mqtt_message_queue = []
        self.max_queue_size = 100
    
    def _publish_vitals_with_fallback(self, vitals_payload):
        """
        Publish vitals with offline buffering
        """
        if self.mqtt_client and self.mqtt_client.is_connected:
            # Online - publish directly
            success = self.mqtt_client.publish_vitals(vitals_payload)
            
            if success:
                # Try to send queued messages
                self._flush_message_queue()
        else:
            # Offline - buffer message
            if len(self.mqtt_message_queue) < self.max_queue_size:
                self.mqtt_message_queue.append({
                    'type': 'vitals',
                    'payload': vitals_payload,
                    'timestamp': time.time()
                })
                self.logger.debug(f"Message queued (size={len(self.mqtt_message_queue)})")
    
    def _flush_message_queue(self):
        """
        Send buffered messages khi reconnect
        """
        while self.mqtt_message_queue:
            msg = self.mqtt_message_queue.pop(0)
            
            if msg['type'] == 'vitals':
                success = self.mqtt_client.publish_vitals(msg['payload'])
                if not success:
                    # Re-queue if failed
                    self.mqtt_message_queue.insert(0, msg)
                    break
```

---

## **8. Configuration Examples**

### **8.1. Development (local broker, no TLS)**

```yaml
communication:
  mqtt:
    broker: localhost
    port: 1883
    username: iot_health_device
    password: test123
    device_id: rpi_bp_dev_001
    use_tls: false
```

### **8.2. Production (HiveMQ Cloud, TLS)**

```yaml
communication:
  mqtt:
    broker: abc123.s1.eu.hivemq.cloud
    port: 8883
    username: iot_health_device
    password: $MQTT_PASSWORD  # From environment variable
    device_id: rpi_bp_prod_001
    use_tls: true
    ca_cert: ''  # HiveMQ uses public CA
    cert_file: ''
    key_file: ''
```

---

## **9. Monitoring Dashboard (Optional)**

Tạo simple Node-RED dashboard để visualize data:

1. Install Node-RED:
   ```bash
   npm install -g node-red
   ```

2. Install MQTT nodes:
   ```bash
   cd ~/.node-red
   npm install node-red-dashboard
   ```

3. Import flow (paste vào Node-RED):
   ```json
   [
     {
       "id": "mqtt_in",
       "type": "mqtt in",
       "broker": "mqtt_broker",
       "topic": "iot_health/device/+/vitals",
       "qos": "1"
     },
     {
       "id": "mqtt_broker",
       "type": "mqtt-broker",
       "broker": "localhost",
       "port": "8883",
       "tls": "tls_config"
     }
   ]
   ```

---

**✅ MQTT integration complete! Device giờ có thể sync data realtime với web/mobile apps.**
