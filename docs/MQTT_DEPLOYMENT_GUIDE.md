# 📡 MQTT Deployment Guide - IoT Health Monitor

## **Tổng quan**

Guide này hướng dẫn triển khai MQTT broker (Mosquitto) với TLS/SSL encryption, authentication, và ACL cho production environment.

---

## **1. Cài đặt Mosquitto Broker**

### **Trên Ubuntu/Raspberry Pi OS:**

```bash
# Update package list
sudo apt update

# Cài Mosquitto broker + clients
sudo apt install mosquitto mosquitto-clients -y

# Enable service tự động khởi động
sudo systemctl enable mosquitto
sudo systemctl start mosquitto
```

### **Kiểm tra trạng thái:**

```bash
sudo systemctl status mosquitto
```

Expected output: `active (running)`

---

## **2. Tạo TLS/SSL Certificates**

### **2.1. Tạo CA (Certificate Authority)**

```bash
# Tạo thư mục lưu certificates
sudo mkdir -p /etc/mosquitto/certs
cd /etc/mosquitto/certs

# Generate CA private key (4096-bit RSA)
sudo openssl genrsa -out ca.key 4096

# Create CA certificate (valid 10 năm)
sudo openssl req -new -x509 -days 3650 -key ca.key -out ca.crt \
  -subj "/C=VN/ST=HCM/L=HoChiMinh/O=IoTHealth/CN=IoT Health CA"
```

### **2.2. Tạo Server Certificate**

```bash
# Generate server private key
sudo openssl genrsa -out server.key 2048

# Create certificate signing request (CSR)
sudo openssl req -new -key server.key -out server.csr \
  -subj "/C=VN/ST=HCM/L=HoChiMinh/O=IoTHealth/CN=mqtt.iothealth.local"

# Sign CSR với CA certificate
sudo openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out server.crt -days 3650
```

### **2.3. Tạo Client Certificates (mutual TLS)**

```bash
# Generate client private key
sudo openssl genrsa -out client.key 2048

# Create client CSR
sudo openssl req -new -key client.key -out client.csr \
  -subj "/C=VN/ST=HCM/L=HoChiMinh/O=IoTHealth/CN=rpi_bp_001"

# Sign với CA
sudo openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out client.crt -days 3650
```

### **2.4. Set permissions**

```bash
sudo chmod 600 /etc/mosquitto/certs/*.key
sudo chmod 644 /etc/mosquitto/certs/*.crt
sudo chown mosquitto:mosquitto /etc/mosquitto/certs/*
```

### **2.5. Copy client certificates đến Raspberry Pi**

```bash
# Tạo thư mục trên IoT device
mkdir -p ~/Desktop/IoT_health/config/certs

# Copy certificates
sudo cp /etc/mosquitto/certs/ca.crt ~/Desktop/IoT_health/config/certs/
sudo cp /etc/mosquitto/certs/client.crt ~/Desktop/IoT_health/config/certs/
sudo cp /etc/mosquitto/certs/client.key ~/Desktop/IoT_health/config/certs/

# Set owner
sudo chown pi:pi ~/Desktop/IoT_health/config/certs/*
```

---

## **3. Cấu hình Mosquitto Broker**

### **3.1. Tạo password file**

```bash
# Tạo user với password
sudo mosquitto_passwd -c /etc/mosquitto/passwd iot_health_device
# Nhập password khi prompted (e.g., "SecureP@ssw0rd!")

# Add thêm users (web dashboard, mobile app)
sudo mosquitto_passwd /etc/mosquitto/passwd web_dashboard
sudo mosquitto_passwd /etc/mosquitto/passwd mobile_app
```

### **3.2. Tạo ACL file (Access Control List)**

```bash
sudo nano /etc/mosquitto/acl
```

**Nội dung ACL:**

```
# ===== DEVICE ROLE (IoT sensors) =====
# Pattern: rpi_bp_001, rpi_bp_002, ...
user iot_health_device

# Devices có thể publish vitals/alerts/status của chính nó
topic write iot_health/device/+/vitals
topic write iot_health/device/+/alerts
topic write iot_health/device/+/status

# Devices có thể subscribe commands cho chính nó
topic read iot_health/patient/+/commands
topic read iot_health/patient/+/predictions

# ===== WEB DASHBOARD ROLE =====
user web_dashboard

# Web có thể đọc TẤT CẢ data
topic read iot_health/device/#
topic read iot_health/patient/#

# Web có thể gửi commands
topic write iot_health/patient/+/commands

# ===== MOBILE APP ROLE =====
user mobile_app

# Mobile read vitals/alerts của patient
topic read iot_health/device/+/vitals
topic read iot_health/device/+/alerts
topic read iot_health/device/+/status

# Mobile có thể gửi commands
topic write iot_health/patient/+/commands
```

**Giải thích wildcards:**
- `+`: Single-level wildcard (match 1 level)
  - `iot_health/device/+/vitals` → matches `iot_health/device/rpi_001/vitals`
- `#`: Multi-level wildcard (match 0+ levels)
  - `iot_health/device/#` → matches ALL topics under `iot_health/device/`

### **3.3. Configure Mosquitto**

```bash
sudo nano /etc/mosquitto/mosquitto.conf
```

**Nội dung config:**

```conf
# ===== PERSISTENCE =====
persistence true
persistence_location /var/lib/mosquitto/

# ===== LOGGING =====
log_dest file /var/log/mosquitto/mosquitto.log
log_dest stdout
log_type error
log_type warning
log_type notice
log_type information
connection_messages true
log_timestamp true

# ===== SECURITY =====
# Disable anonymous access
allow_anonymous false

# Password file
password_file /etc/mosquitto/passwd

# ACL file
acl_file /etc/mosquitto/acl

# ===== TLS/SSL LISTENER (Port 8883) =====
listener 8883
protocol mqtt
cafile /etc/mosquitto/certs/ca.crt
certfile /etc/mosquitto/certs/server.crt
keyfile /etc/mosquitto/certs/server.key

# Require client certificates (mutual TLS)
require_certificate true
use_identity_as_username false

# TLS version (TLS 1.2+)
tls_version tlsv1.2

# ===== WEBSOCKETS LISTENER (Port 8884) - Optional =====
listener 8884
protocol websockets
cafile /etc/mosquitto/certs/ca.crt
certfile /etc/mosquitto/certs/server.crt
keyfile /etc/mosquitto/certs/server.key

# ===== NON-TLS LISTENER (localhost only) - For debugging =====
listener 1883 127.0.0.1
protocol mqtt
allow_anonymous true
```

### **3.4. Restart Mosquitto**

```bash
sudo systemctl restart mosquitto
sudo systemctl status mosquitto
```

**Check logs:**

```bash
sudo tail -f /var/log/mosquitto/mosquitto.log
```

---

## **4. Testing MQTT Connection**

### **4.1. Test với mosquitto_pub/sub (localhost)**

**Terminal 1 - Subscribe:**

```bash
mosquitto_sub -h localhost -p 1883 -t "test/topic" -v
```

**Terminal 2 - Publish:**

```bash
mosquitto_pub -h localhost -p 1883 -t "test/topic" -m "Hello MQTT!"
```

### **4.2. Test với TLS + Authentication**

**Terminal 1 - Subscribe:**

```bash
mosquitto_sub \
  -h <broker_ip> -p 8883 \
  --cafile /etc/mosquitto/certs/ca.crt \
  --cert ~/Desktop/IoT_health/config/certs/client.crt \
  --key ~/Desktop/IoT_health/config/certs/client.key \
  -u iot_health_device -P "SecureP@ssw0rd!" \
  -t "iot_health/device/+/vitals" -v
```

**Terminal 2 - Publish:**

```bash
mosquitto_pub \
  -h <broker_ip> -p 8883 \
  --cafile /etc/mosquitto/certs/ca.crt \
  --cert ~/Desktop/IoT_health/config/certs/client.crt \
  --key ~/Desktop/IoT_health/config/certs/client.key \
  -u iot_health_device -P "SecureP@ssw0rd!" \
  -t "iot_health/device/rpi_bp_001/vitals" \
  -m '{"hr": 75, "spo2": 98, "temp": 36.5}'
```

**Expected:** Terminal 1 nhận được message.

---

## **5. Cấu hình IoT Health App**

### **5.1. Update `app_config.yaml`**

```yaml
communication:
  mqtt:
    broker: <broker_ip_hoặc_domain>  # e.g., mqtt.iothealth.local hoặc 192.168.1.100
    port: 8883
    username: iot_health_device
    password: SecureP@ssw0rd!  # Hoặc dùng env variable
    device_id: rpi_bp_001
    use_tls: true
    ca_cert: config/certs/ca.crt
    cert_file: config/certs/client.crt
    key_file: config/certs/client.key
```

### **5.2. Chạy app và kiểm tra kết nối**

```bash
cd ~/Desktop/IoT_health
python3 main.py
```

**Check logs:**

```
INFO - ✅ Connected to MQTT broker: mqtt.iothealth.local:8883
INFO - 📡 Auto-subscribed to iot_health/patient/P12345/commands
```

---

## **6. Monitoring & Debugging**

### **6.1. Monitor broker logs**

```bash
sudo tail -f /var/log/mosquitto/mosquitto.log
```

### **6.2. Check active connections**

```bash
# Install mosquitto clients nếu chưa có
sudo apt install mosquitto-clients

# Subscribe to $SYS topics (broker statistics)
mosquitto_sub -h localhost -p 1883 -t '$SYS/broker/clients/connected' -v
mosquitto_sub -h localhost -p 1883 -t '$SYS/broker/messages/#' -v
```

### **6.3. Common issues**

**Issue 1: Connection refused**
- Check firewall: `sudo ufw allow 8883/tcp`
- Check broker running: `sudo systemctl status mosquitto`

**Issue 2: Certificate verification failed**
- Check CA cert path in config
- Verify cert validity: `openssl x509 -in ca.crt -text -noout`

**Issue 3: Authentication failed**
- Verify username/password: `sudo cat /etc/mosquitto/passwd`
- Check ACL permissions

---

## **7. Cloud MQTT Brokers (Alternative)**

Nếu không muốn self-host, có thể dùng cloud brokers:

### **7.1. HiveMQ Cloud** (Free tier)

- URL: https://www.hivemq.com/mqtt-cloud-broker/
- Free: 100 connections, 10 GB data/month
- TLS built-in

**Setup:**
1. Tạo account tại HiveMQ Cloud
2. Tạo cluster mới
3. Lấy broker URL (e.g., `abc123.s1.eu.hivemq.cloud`)
4. Tạo credentials trong dashboard
5. Update `app_config.yaml`:

```yaml
mqtt:
  broker: abc123.s1.eu.hivemq.cloud
  port: 8883
  username: your_username
  password: your_password
  use_tls: true
  ca_cert: ''  # HiveMQ dùng public CA
  cert_file: ''
  key_file: ''
```

### **7.2. AWS IoT Core**

- Tích hợp với AWS services (Lambda, DynamoDB, S3)
- Pricing: $1/million messages

### **7.3. Azure IoT Hub**

- Enterprise-grade với built-in device management
- Free tier: 8,000 messages/day

---

## **8. Web Dashboard Integration (Vue.js Example)**

### **8.1. Install MQTT.js**

```bash
npm install mqtt
```

### **8.2. Connect to broker**

```javascript
import mqtt from 'mqtt'

const client = mqtt.connect('wss://mqtt.iothealth.local:8884/mqtt', {
  username: 'web_dashboard',
  password: 'WebDashP@ss',
  clientId: 'web_' + Math.random().toString(16).substr(2, 8),
  ca: fs.readFileSync('certs/ca.crt'),  // Load CA cert
  reconnectPeriod: 5000
})

client.on('connect', () => {
  console.log('✅ Connected to MQTT broker')
  
  // Subscribe to all devices
  client.subscribe('iot_health/device/+/vitals')
  client.subscribe('iot_health/device/+/alerts')
})

client.on('message', (topic, message) => {
  const data = JSON.parse(message.toString())
  
  if (topic.includes('/vitals')) {
    updateVitalsChart(data)
  } else if (topic.includes('/alerts')) {
    showAlertNotification(data)
  }
})

// Send command
function startBPMeasurement(patientId) {
  const payload = {
    command: 'start_measurement',
    timestamp: Date.now() / 1000,
    source: 'web_dashboard',
    parameters: {
      inflate_target_mmhg: 180,
      deflate_rate_mmhg_s: 3.0
    }
  }
  
  client.publish(
    `iot_health/patient/${patientId}/commands`,
    JSON.stringify(payload),
    { qos: 2 }
  )
}
```

---

## **9. Mobile App Integration (Flutter Example)**

### **9.1. Add dependency**

```yaml
dependencies:
  mqtt_client: ^10.0.0
```

### **9.2. Connect code**

```dart
import 'package:mqtt_client/mqtt_client.dart';
import 'package:mqtt_client/mqtt_server_client.dart';

final client = MqttServerClient.withPort(
  'mqtt.iothealth.local',
  'mobile_app_${DateTime.now().millisecondsSinceEpoch}',
  8883
);

client.secure = true;
client.securityContext = SecurityContext.defaultContext;
client.securityContext.setTrustedCertificates('assets/certs/ca.crt');

await client.connect('mobile_app', 'MobileP@ss');

if (client.connectionStatus!.state == MqttConnectionState.connected) {
  print('✅ Connected to MQTT broker');
  
  // Subscribe
  client.subscribe('iot_health/device/+/alerts', MqttQos.atLeastOnce);
  
  // Listen
  client.updates!.listen((List<MqttReceivedMessage<MqttMessage>> messages) {
    final message = messages[0].payload as MqttPublishMessage;
    final payload = MqttPublishPayload.bytesToStringAsString(message.payload.message);
    
    final data = jsonDecode(payload);
    showNotification(data);
  });
}
```

---

## **10. Security Best Practices**

✅ **DO:**
- Dùng TLS/SSL cho production
- Rotate passwords định kỳ (mỗi 90 ngày)
- Use strong passwords (12+ characters, mixed case, symbols)
- Implement ACL để limit access
- Monitor broker logs cho suspicious activity
- Use mutual TLS (client certs) cho critical systems
- Keep Mosquitto updated (`sudo apt upgrade mosquitto`)

❌ **DON'T:**
- Commit passwords/keys vào Git
- Dùng `allow_anonymous true` trên production
- Expose port 1883 (non-TLS) ra internet
- Share client certificates giữa nhiều devices
- Hardcode credentials trong source code

---

## **11. Troubleshooting Checklist**

### **Connection failed:**
- [ ] Broker đang chạy? (`sudo systemctl status mosquitto`)
- [ ] Port 8883 mở? (`sudo netstat -tulnp | grep 8883`)
- [ ] Firewall allow? (`sudo ufw status`)
- [ ] Certificates valid? (`openssl verify -CAfile ca.crt client.crt`)
- [ ] Username/password đúng?

### **Certificate errors:**
- [ ] CA cert path đúng trong config?
- [ ] Client cert signed bởi CA?
- [ ] Permissions đúng? (600 cho .key, 644 cho .crt)
- [ ] Cert chưa expire? (`openssl x509 -in client.crt -noout -dates`)

### **ACL permission denied:**
- [ ] User có trong `/etc/mosquitto/passwd`?
- [ ] ACL rules đúng topic pattern?
- [ ] Restart broker sau khi sửa ACL? (`sudo systemctl restart mosquitto`)

---

## **12. Production Deployment Checklist**

### **Broker Setup:**
- [ ] Mosquitto cài đặt và enabled
- [ ] TLS certificates generated và installed
- [ ] Password file tạo với strong passwords
- [ ] ACL configured theo roles
- [ ] Firewall rules configured (8883/tcp)
- [ ] Logs monitoring setup
- [ ] Backup certificates ra ngoài server

### **IoT Device:**
- [ ] Certificates copied đến device
- [ ] `app_config.yaml` updated với broker info
- [ ] Test connection thành công
- [ ] Auto-reconnect hoạt động
- [ ] Store-forward enabled cho offline periods

### **Web/Mobile:**
- [ ] MQTT client library integrated
- [ ] Credentials secured (env variables/keystore)
- [ ] Subscribe to đúng topics
- [ ] Handle reconnection gracefully
- [ ] UI updates realtime

---

## **📞 Support**

- **MQTT Docs:** https://mosquitto.org/documentation/
- **Paho MQTT Python:** https://eclipse.dev/paho/index.php?page=clients/python/index.php
- **HiveMQ Learning:** https://www.hivemq.com/mqtt-essentials/

---

**Chúc deploy thành công! 🚀**
