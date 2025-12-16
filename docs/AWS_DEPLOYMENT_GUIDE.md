# AWS EC2 API Deployment Guide - IoT Health Monitor

## 📋 Tóm tắt

Hướng dẫn chi tiết để deploy **Backend API v2.1.0** (với AI threshold generation) lên AWS EC2 server.

**Server hiện tại:**
- IP: 47.130.193.237
- Port: 8000
- OS: Ubuntu/Linux
- Python: 3.8+

---

## 📦 Files cần upload

### **1. Backend API** (✅ ĐÃ CẬP NHẬT)
- `scripts/api.py` (v2.1.0 - đã thêm 2 endpoints mới)
- `scripts/ai_threshold_generator.py` (637 lines - engine tạo thresholds)

### **2. Dependencies mới** (requirements.txt)
```txt
flask>=2.3.0
flask-cors>=4.0.0
mysql-connector-python>=8.0.0
google-generativeai>=0.3.0  # ⚠️ YÊU CẦU GEMINI API KEY
PyYAML>=6.0.1
python-dotenv>=1.0.0
```

### **3. Environment Variables** (.env)
```bash
# MySQL Cloud (AWS RDS)
MYSQL_HOST=database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com
MYSQL_PORT=3306
MYSQL_DATABASE=iot_health_cloud
MYSQL_USER=pi_sync  # Hoặc user khác có quyền SELECT/INSERT/UPDATE
MYSQL_PASSWORD=<your_mysql_password>

# Google Gemini API (để refine AI thresholds)
GOOGLE_GEMINI_API_KEY=<your_gemini_api_key>  # ⚠️ BẮT BUỘC (nếu dùng AI refine)
```

---

## 🚀 Bước 1: Kết nối SSH đến EC2

```bash
ssh -i /path/to/your-key.pem ubuntu@47.130.193.237
```

**Lưu ý:**
- Thay `/path/to/your-key.pem` bằng đường dẫn đến SSH key của bạn
- Nếu dùng username khác (không phải `ubuntu`), thay đổi cho phù hợp
- Đảm bảo SSH key có quyền 400: `chmod 400 your-key.pem`

---

## 🔍 Bước 2: Tìm thư mục API hiện tại

```bash
# Kiểm tra tiến trình API đang chạy
ps aux | grep api.py

# Hoặc tìm file api.py
find /home -name "api.py" 2>/dev/null
find /opt -name "api.py" 2>/dev/null

# Thư mục phổ biến:
# /home/ubuntu/iot-health-api/
# /opt/iot-health/
# /var/www/api/
```

**Giả sử API đang ở:** `/home/ubuntu/iot-health-api/`

```bash
cd /home/ubuntu/iot-health-api/
ls -la
```

---

## 💾 Bước 3: Backup files cũ

```bash
cd /home/ubuntu/iot-health-api/

# Backup api.py cũ
cp api.py api.py.backup_$(date +%Y%m%d_%H%M%S)

# Nếu có scripts/ folder
if [ -d "scripts" ]; then
    mkdir -p scripts/backups
    cp scripts/*.py scripts/backups/ 2>/dev/null || true
fi

# Kiểm tra backup
ls -lh *.backup_*
```

---

## 📤 Bước 4: Upload files mới từ Pi

**Từ máy Pi (mở terminal mới):**

```bash
cd /home/pi/Desktop/IoT_health/

# Upload api.py
scp -i /path/to/your-key.pem \
    scripts/api.py \
    ubuntu@47.130.193.237:/home/ubuntu/iot-health-api/

# Upload ai_threshold_generator.py
scp -i /path/to/your-key.pem \
    scripts/ai_threshold_generator.py \
    ubuntu@47.130.193.237:/home/ubuntu/iot-health-api/scripts/

# Hoặc nếu không có scripts/ folder trên server:
scp -i /path/to/your-key.pem \
    scripts/ai_threshold_generator.py \
    ubuntu@47.130.193.237:/home/ubuntu/iot-health-api/
```

**Nếu không có SSH key từ Pi:**

1. Từ Pi, tạo archive:
   ```bash
   cd /home/pi/Desktop/IoT_health/scripts/
   tar -czf ~/api_update.tar.gz api.py ai_threshold_generator.py
   ```

2. Copy file này qua máy có SSH key (USB, SCP từ PC, etc.)

3. Từ PC upload lên EC2:
   ```bash
   scp -i your-key.pem api_update.tar.gz ubuntu@47.130.193.237:/home/ubuntu/
   
   # SSH vào EC2 và extract
   ssh -i your-key.pem ubuntu@47.130.193.237
   cd /home/ubuntu/iot-health-api/
   tar -xzf ~/api_update.tar.gz
   ```

---

## 📦 Bước 5: Install dependencies

**Trên EC2 server:**

```bash
cd /home/ubuntu/iot-health-api/

# Kiểm tra Python version (cần >= 3.8)
python3 --version

# Kiểm tra pip
pip3 --version

# Install dependencies mới
pip3 install google-generativeai --user

# Hoặc nếu có requirements.txt:
pip3 install -r requirements.txt --user

# Verify installation
python3 -c "import google.generativeai as genai; print('google-generativeai OK')"
```

**Nếu gặp lỗi permission:**
```bash
# Dùng virtualenv (recommended)
cd /home/ubuntu/iot-health-api/
python3 -m venv venv
source venv/bin/activate
pip install google-generativeai flask flask-cors mysql-connector-python python-dotenv PyYAML
```

---

## 🔐 Bước 6: Cấu hình environment variables

### **Option 1: Dùng .env file** (Recommended)

```bash
cd /home/ubuntu/iot-health-api/

# Tạo .env file
nano .env
```

**Nội dung .env:**
```bash
# MySQL Cloud (AWS RDS Singapore)
MYSQL_HOST=database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com
MYSQL_PORT=3306
MYSQL_DATABASE=iot_health_cloud
MYSQL_USER=pi_sync  # Hoặc user khác có quyền INSERT/UPDATE
MYSQL_PASSWORD=your_actual_password_here

# Google Gemini API
GOOGLE_GEMINI_API_KEY=your_gemini_api_key_here

# Optional: Server settings
FLASK_ENV=production
FLASK_DEBUG=0
```

**Bảo mật .env:**
```bash
chmod 600 .env
chown ubuntu:ubuntu .env
```

### **Option 2: Export trực tiếp** (Temporary)

```bash
export MYSQL_HOST="database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com"
export MYSQL_PORT="3306"
export MYSQL_DATABASE="iot_health_cloud"
export MYSQL_USER="pi_sync"
export MYSQL_PASSWORD="your_password"
export GOOGLE_GEMINI_API_KEY="your_gemini_key"

# Kiểm tra
echo $MYSQL_HOST
echo $GOOGLE_GEMINI_API_KEY
```

**⚠️ Lưu ý:** Variables này chỉ tồn tại trong session hiện tại. Để persistent, thêm vào `~/.bashrc` hoặc dùng systemd service (xem Bước 8).

---

## 🧪 Bước 7: Test API trước khi restart

```bash
cd /home/ubuntu/iot-health-api/

# Load environment variables (nếu dùng .env)
export $(cat .env | xargs)

# Test import
python3 -c "
from scripts.ai_threshold_generator import ThresholdGenerator
print('✅ ThresholdGenerator import OK')
"

# Test API health endpoint (chỉ test syntax, chưa chạy server)
python3 -c "
import sys
sys.path.insert(0, '.')
from api import app
print('✅ Flask app OK')
"

# Test database connection
python3 -c "
import mysql.connector
import os
conn = mysql.connector.connect(
    host=os.getenv('MYSQL_HOST'),
    port=int(os.getenv('MYSQL_PORT', 3306)),
    user=os.getenv('MYSQL_USER'),
    password=os.getenv('MYSQL_PASSWORD'),
    database=os.getenv('MYSQL_DATABASE')
)
print('✅ MySQL connection OK')
conn.close()
"
```

**Nếu test thành công, tiến hành restart service.**

---

## 🔄 Bước 8: Restart API service

### **Trường hợp 1: API chạy bằng systemd service**

```bash
# Kiểm tra service name
sudo systemctl list-units | grep -i health
sudo systemctl list-units | grep -i api

# Ví dụ: iot-health-api.service
sudo systemctl status iot-health-api

# Restart service
sudo systemctl restart iot-health-api

# Kiểm tra log
sudo journalctl -u iot-health-api -f
```

**Nếu cần update service file để load .env:**
```bash
sudo nano /etc/systemd/system/iot-health-api.service
```

Thêm `EnvironmentFile`:
```ini
[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/iot-health-api
EnvironmentFile=/home/ubuntu/iot-health-api/.env
ExecStart=/usr/bin/python3 /home/ubuntu/iot-health-api/api.py
Restart=always
```

Reload và restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart iot-health-api
```

### **Trường hợp 2: API chạy bằng nohup/background**

```bash
# Tìm PID của tiến trình api.py
ps aux | grep api.py

# Kill tiến trình cũ
pkill -f api.py
# Hoặc
kill <PID>

# Start lại với nohup
cd /home/ubuntu/iot-health-api/
nohup python3 api.py > api.log 2>&1 &

# Kiểm tra log
tail -f api.log
```

### **Trường hợp 3: API chạy bằng screen/tmux**

```bash
# List screen sessions
screen -ls

# Attach vào session
screen -r <session_name>

# Ctrl+C để stop API
# Start lại
python3 api.py

# Detach: Ctrl+A, D
```

---

## ✅ Bước 9: Verify deployment

### **1. Kiểm tra API có chạy không**

```bash
# Check tiến trình
ps aux | grep api.py

# Check port 8000
sudo netstat -tulpn | grep 8000
# Hoặc
sudo ss -tulpn | grep 8000
```

### **2. Test health endpoint**

```bash
# Từ EC2 server
curl http://localhost:8000/api/health

# Expected output:
# {
#   "status": "healthy",
#   "version": "2.1.0",
#   "timestamp": "2025-01-20T10:30:00Z",
#   "database": "connected"
# }
```

### **3. Test new AI endpoints**

**Test POST /api/ai/generate-thresholds:**
```bash
curl -X POST http://localhost:8000/api/ai/generate-thresholds \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "test_patient_001",
    "age": 65,
    "gender": "male",
    "chronic_diseases": ["Hypertension"],
    "method": "rule_based"
  }'
```

**Expected output (rule-based):**
```json
{
  "success": true,
  "patient_id": "test_patient_001",
  "thresholds": {
    "heart_rate": {"min_normal": 65, "max_normal": 85, ...},
    "systolic_bp": {"min_normal": 90, "max_normal": 110, ...},
    ...
  },
  "generation_method": "rule_based",
  "rules_applied": 4,
  "confidence_score": 0.90
}
```

**Test AI-powered (requires GOOGLE_GEMINI_API_KEY):**
```bash
curl -X POST http://localhost:8000/api/ai/generate-thresholds \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "test_patient_002",
    "age": 45,
    "gender": "female",
    "chronic_diseases": ["Diabetes"],
    "medications": ["Metformin"],
    "method": "ai_powered"
  }'
```

### **4. Test từ Pi device**

**Từ Raspberry Pi:**
```bash
# Test health endpoint
curl http://47.130.193.237:8000/api/health

# Test list patients
curl http://47.130.193.237:8000/api/patients
```

### **5. Test từ Android App**

- Mở Android App
- Tạo patient mới với AI thresholds (nếu có UI)
- Kiểm tra log trên EC2 xem có request POST /api/patients không

---

## 🐛 Troubleshooting

### **Lỗi 1: ModuleNotFoundError: No module named 'google.generativeai'**

**Giải pháp:**
```bash
pip3 install google-generativeai --user
# Hoặc trong virtualenv:
source venv/bin/activate
pip install google-generativeai
```

### **Lỗi 2: MySQL connection failed**

**Giải pháp:**
```bash
# Kiểm tra environment variables
echo $MYSQL_HOST
echo $MYSQL_USER
echo $MYSQL_PASSWORD

# Kiểm tra security group AWS RDS cho phép IP của EC2
# Hoặc test connection thủ công:
mysql -h database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com \
      -u pi_sync -p \
      iot_health_cloud
```

### **Lỗi 3: Port 8000 already in use**

**Giải pháp:**
```bash
# Tìm tiến trình đang dùng port 8000
sudo lsof -i :8000

# Kill tiến trình đó
sudo kill <PID>
```

### **Lỗi 4: GOOGLE_GEMINI_API_KEY not set**

**Giải pháp:**
```bash
# Thêm vào .env
echo "GOOGLE_GEMINI_API_KEY=your_key_here" >> .env

# Hoặc export
export GOOGLE_GEMINI_API_KEY="your_key_here"

# Restart API
sudo systemctl restart iot-health-api
```

### **Lỗi 5: ImportError: cannot import name 'ThresholdGenerator'**

**Nguyên nhân:** File `ai_threshold_generator.py` không đúng vị trí.

**Giải pháp:**
```bash
# Kiểm tra cấu trúc thư mục
cd /home/ubuntu/iot-health-api/
tree -L 2  # Hoặc ls -R

# Đảm bảo có:
# api.py
# scripts/
#   ai_threshold_generator.py

# Nếu thiếu, tạo scripts/ folder
mkdir -p scripts
mv ai_threshold_generator.py scripts/
```

### **Lỗi 6: API không ghi log**

**Giải pháp:**
```bash
# Kiểm tra log file
ls -l api.log

# Nếu không có, redirect output:
nohup python3 api.py > api.log 2>&1 &

# Xem log real-time
tail -f api.log

# Hoặc dùng journalctl (systemd)
sudo journalctl -u iot-health-api -f
```

---

## 📊 Monitoring API sau khi deploy

### **1. Real-time log monitoring**

```bash
# systemd service
sudo journalctl -u iot-health-api -f

# nohup/background
tail -f /home/ubuntu/iot-health-api/api.log
```

### **2. Check request logs**

**Thêm logging vào api.py** (nếu chưa có):
```python
import logging
logging.basicConfig(
    filename='api_requests.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

@app.before_request
def log_request():
    logging.info(f"{request.method} {request.path} - {request.remote_addr}")
```

### **3. Monitor database queries**

```bash
# Từ EC2, connect vào MySQL
mysql -h database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com \
      -u pi_sync -p iot_health_cloud

# Kiểm tra recent threshold generations
SELECT patient_id, vital_sign, generation_method, generation_timestamp, confidence_score
FROM patient_thresholds
WHERE generation_timestamp > NOW() - INTERVAL 1 HOUR
ORDER BY generation_timestamp DESC;
```

---

## 🔒 Security Checklist

- ✅ `.env` file có quyền 600 (chỉ owner đọc/ghi)
- ✅ Không commit `.env` vào git
- ✅ MySQL user `pi_sync` chỉ có quyền SELECT/INSERT/UPDATE (không DROP/DELETE tables)
- ✅ API không expose sensitive data trong error messages
- ✅ HTTPS/TLS cho production (nếu có domain)
- ✅ Firewall rules cho phép port 8000 từ Pi devices
- ✅ Rate limiting (nếu cần) để tránh DDoS

---

## 📝 Post-Deployment Tasks

### **1. Test end-to-end flow**

1. **Từ Android App:** Tạo patient mới với AI thresholds
2. **Verify MySQL:** Kiểm tra `patients` và `patient_thresholds` tables
3. **Từ Pi:** Đợi 60 giây để CloudSyncManager sync thresholds
4. **Verify SQLite:** Check Pi's local database có thresholds mới
5. **Test alert:** Trigger vital signs ngoài threshold → verify alert TTS

### **2. Update Pi devices**

**Đảm bảo Pi đã có config mới:**
```yaml
# /home/pi/Desktop/IoT_health/config/app_config.yaml

cloud:
  enabled: true
  mysql:
    host: database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com
    user: pi_sync
    password_env: "MYSQL_CLOUD_PASSWORD"

threshold_management:
  sync_interval_seconds: 60
  auto_reload: true
  fallback_to_baseline: true
```

### **3. Monitor for 24h**

- Kiểm tra API logs: Có errors không?
- Kiểm tra MySQL: Thresholds được tạo đúng không?
- Kiểm tra Pi sync logs: Sync thresholds thành công không?
- Kiểm tra AlertSystem: Alerts dùng đúng thresholds không?

---

## 🎉 Deployment Complete Checklist

- ✅ API v2.1.0 uploaded và running
- ✅ `ai_threshold_generator.py` uploaded
- ✅ Dependencies installed (`google-generativeai`)
- ✅ Environment variables configured (`.env`)
- ✅ Service restarted successfully
- ✅ Health endpoint returns 200 OK
- ✅ New endpoints `/api/ai/generate-thresholds` tested
- ✅ MySQL connection verified
- ✅ Gemini API key configured (if using AI refine)
- ✅ Pi devices can connect to API
- ✅ Logs monitoring active
- ✅ Security checklist completed

---

## 📞 Support

Nếu gặp vấn đề khi deploy, kiểm tra:
1. Log file: `api.log` hoặc `journalctl -u iot-health-api`
2. MySQL connection: Test trực tiếp với `mysql` command
3. Python imports: Test `python3 -c "from scripts.ai_threshold_generator import ThresholdGenerator"`
4. Environment variables: `echo $GOOGLE_GEMINI_API_KEY`

---

**Updated:** 2025-01-20
**API Version:** 2.1.0
**Author:** IoT Health Monitor Team
