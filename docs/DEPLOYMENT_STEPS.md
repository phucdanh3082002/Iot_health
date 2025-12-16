# Hướng dẫn Deploy API v2.1.0 lên Server AWS EC2

## 📍 Thông tin Server

**Server path:** `/var/www/iot-health-api`
**File hiện tại:** `app.py` (production)
**Environment:** Python venv + Gunicorn
**IP:** 47.130.193.237

---

## 🚀 Bước 1: Backup file cũ trên server

```bash
cd /var/www/iot-health-api

# Backup app.py hiện tại
sudo cp app.py app.py.backup_$(date +%Y%m%d_%H%M%S)

# Verify backup
ls -lh app.py.backup_*
```

---

## 📤 Bước 2: Upload files mới từ Pi

### **Option A: Dùng SCP (nếu có SSH key)**

**Từ Pi terminal:**

```bash
cd /home/pi/Desktop/IoT_health/

# Upload api.py → app.py trên server
scp -i ~/.ssh/your-key.pem scripts/api.py ubuntu@47.130.193.237:/tmp/app.py

# Upload ai_threshold_generator.py
scp -i ~/.ssh/your-key.pem scripts/ai_threshold_generator.py ubuntu@47.130.193.237:/tmp/
```

**Trên server:**

```bash
# Di chuyển files vào thư mục production
sudo mv /tmp/app.py /var/www/iot-health-api/app.py
sudo mkdir -p /var/www/iot-health-api/scripts
sudo mv /tmp/ai_threshold_generator.py /var/www/iot-health-api/scripts/

# Fix permissions
sudo chown -R ubuntu:ubuntu /var/www/iot-health-api/
```

### **Option B: Dùng Git (recommended)**

**Trên server:**

```bash
cd /var/www/iot-health-api

# Clone hoặc pull repo (nếu dùng git)
# Hoặc tạo files thủ công:

# Tạo app.py mới
sudo nano app.py
# (Copy nội dung từ scripts/api.py của Pi, paste vào đây, Ctrl+X, Y, Enter)

# Tạo scripts/ai_threshold_generator.py
sudo mkdir -p scripts
sudo nano scripts/ai_threshold_generator.py
# (Copy nội dung từ scripts/ai_threshold_generator.py của Pi)
```

### **Option C: Dùng SFTP/FileZilla (GUI)**

1. Kết nối SFTP đến server (47.130.193.237)
2. Navigate đến `/var/www/iot-health-api/`
3. Upload `scripts/api.py` → rename thành `app.py`
4. Tạo folder `scripts/`
5. Upload `scripts/ai_threshold_generator.py`

---

## 📦 Bước 3: Install dependencies

**Trên server:**

```bash
cd /var/www/iot-health-api

# Activate virtual environment
source venv/bin/activate

# Install dependency mới
pip install google-generativeai

# Verify installation
pip list | grep google-generativeai

# Optional: Update requirements.txt
pip freeze > requirements.txt
```

---

## 🔐 Bước 4: Cấu hình environment variables

**Tạo/update file .env:**

```bash
cd /var/www/iot-health-api

# Tạo hoặc edit .env
sudo nano .env
```

**Nội dung .env:**

```bash
# MySQL Cloud (AWS RDS)
MYSQL_HOST=database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com
MYSQL_PORT=3306
MYSQL_DATABASE=iot_health_cloud
MYSQL_USER=pi_sync
MYSQL_PASSWORD=your_actual_mysql_password_here

# Google Gemini API (để refine AI thresholds)
GOOGLE_GEMINI_API_KEY=your_gemini_api_key_here

# Flask settings
FLASK_ENV=production
FLASK_DEBUG=0
```

**Bảo mật .env:**

```bash
sudo chmod 600 .env
sudo chown ubuntu:ubuntu .env
```

---

## 🧪 Bước 5: Test API trước khi restart

**Test import:**

```bash
cd /var/www/iot-health-api
source venv/bin/activate

# Test import modules
python3 -c "
from scripts.ai_threshold_generator import ThresholdGenerator
print('✓ ThresholdGenerator import OK')
"

# Test Flask app
python3 -c "
import sys
sys.path.insert(0, '.')
from app import app
print('✓ Flask app OK')
print('Routes:', [str(rule) for rule in app.url_map.iter_rules()])
"
```

**Expected output:**

```
✓ ThresholdGenerator import OK
✓ Flask app OK
Routes: ['/api/health', '/api/patients', '/api/ai/generate-thresholds', ...]
```

---

## 🔄 Bước 6: Restart API service

### **Tìm service name:**

```bash
# Kiểm tra service đang chạy
sudo systemctl list-units | grep -i api
sudo systemctl list-units | grep -i gunicorn
sudo systemctl list-units | grep -i health

# Hoặc check processes
ps aux | grep gunicorn
ps aux | grep app.py
```

### **Restart service:**

**Option A: Systemd service**

```bash
# Giả sử service name là iot-health-api hoặc gunicorn
sudo systemctl restart iot-health-api
# Hoặc
sudo systemctl restart gunicorn

# Check status
sudo systemctl status iot-health-api

# View logs
sudo journalctl -u iot-health-api -f
```

**Option B: Gunicorn trực tiếp**

```bash
# Kill gunicorn processes
sudo pkill -f gunicorn

# Start lại
cd /var/www/iot-health-api
source venv/bin/activate
gunicorn -c gunicorn_config.py app:app &

# Hoặc nếu có start script
./start.sh
```

**Option C: Kiểm tra gunicorn_config.py**

```bash
cat gunicorn_config.py
# Xem config để biết cách start
```

---

## ✅ Bước 7: Verify deployment

### **1. Check API chạy chưa**

```bash
# Trên server
curl http://localhost:8000/api/health

# Expected:
# {"status": "healthy", "version": "2.1.0", ...}
```

### **2. Test endpoint mới**

```bash
# Test AI threshold generation
curl -X POST http://localhost:8000/api/ai/generate-thresholds \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "test_deploy_001",
    "age": 65,
    "gender": "male",
    "chronic_diseases": ["Hypertension"],
    "method": "rule_based"
  }'
```

**Expected output:**

```json
{
  "success": true,
  "patient_id": "test_deploy_001",
  "thresholds": {
    "heart_rate": {
      "min_normal": 65,
      "max_normal": 85,
      ...
    },
    ...
  },
  "generation_method": "rule_based",
  "rules_applied": 4,
  "confidence_score": 0.90
}
```

### **3. Test từ Pi device**

```bash
# Từ Pi
curl http://47.130.193.237:8000/api/health

# Test threshold generation
curl -X POST http://47.130.193.237:8000/api/ai/generate-thresholds \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "patient_001",
    "age": 70,
    "gender": "male",
    "chronic_diseases": ["Diabetes"],
    "method": "rule_based"
  }'
```

---

## 🐛 Troubleshooting

### **Lỗi: ModuleNotFoundError: No module named 'google.generativeai'**

```bash
cd /var/www/iot-health-api
source venv/bin/activate
pip install google-generativeai
sudo systemctl restart iot-health-api
```

### **Lỗi: ImportError: cannot import name 'ThresholdGenerator'**

```bash
# Kiểm tra file tồn tại
ls -l /var/www/iot-health-api/scripts/ai_threshold_generator.py

# Nếu không có, upload lại
```

### **Lỗi: GOOGLE_GEMINI_API_KEY not set**

```bash
# Kiểm tra .env
cat /var/www/iot-health-api/.env | grep GOOGLE

# Nếu thiếu, thêm vào
echo "GOOGLE_GEMINI_API_KEY=your_key_here" | sudo tee -a .env
```

### **Lỗi: Port 8000 already in use**

```bash
# Tìm process đang dùng port 8000
sudo lsof -i :8000

# Kill process
sudo kill <PID>

# Restart service
sudo systemctl restart iot-health-api
```

### **Lỗi: Permission denied**

```bash
# Fix ownership
sudo chown -R ubuntu:ubuntu /var/www/iot-health-api/

# Fix permissions
sudo chmod 755 /var/www/iot-health-api/
sudo chmod 644 /var/www/iot-health-api/app.py
sudo chmod 600 /var/www/iot-health-api/.env
```

---

## 📊 Monitoring sau khi deploy

### **Real-time logs:**

```bash
# Systemd logs
sudo journalctl -u iot-health-api -f

# Hoặc nếu có log file
tail -f /var/www/iot-health-api/logs/api.log
tail -f /var/log/gunicorn/access.log
```

### **Check API health:**

```bash
# Setup cron để check health mỗi 5 phút
crontab -e

# Thêm dòng:
# */5 * * * * curl -s http://localhost:8000/api/health || echo "API DOWN" | mail -s "API Alert" admin@example.com
```

---

## 📋 Checklist hoàn thành

- [ ] Backup app.py cũ
- [ ] Upload app.py mới (từ scripts/api.py)
- [ ] Upload scripts/ai_threshold_generator.py
- [ ] Install google-generativeai
- [ ] Cấu hình .env (MYSQL_PASSWORD, GOOGLE_GEMINI_API_KEY)
- [ ] Test import modules
- [ ] Restart service (gunicorn/systemd)
- [ ] Test /api/health endpoint
- [ ] Test /api/ai/generate-thresholds endpoint
- [ ] Test từ Pi device (external IP)
- [ ] Monitor logs 15 phút

---

## 🎯 Quick Commands Summary

```bash
# === TRÊN SERVER ===

# 1. Backup
cd /var/www/iot-health-api
sudo cp app.py app.py.backup_$(date +%Y%m%d_%H%M%S)

# 2. Upload files (chọn 1 trong các option A/B/C ở trên)

# 3. Install dependency
source venv/bin/activate
pip install google-generativeai

# 4. Configure .env
sudo nano .env
# (Thêm GOOGLE_GEMINI_API_KEY)

# 5. Test
python3 -c "from scripts.ai_threshold_generator import ThresholdGenerator; print('OK')"

# 6. Restart
sudo systemctl restart iot-health-api
# Hoặc: sudo pkill -f gunicorn && gunicorn -c gunicorn_config.py app:app &

# 7. Verify
curl http://localhost:8000/api/health
curl -X POST http://localhost:8000/api/ai/generate-thresholds \
  -H "Content-Type: application/json" \
  -d '{"patient_id":"test","age":65,"gender":"male","method":"rule_based"}'
```

---

**Cập nhật:** 2025-01-20  
**API Version:** 2.1.0  
**Server Path:** /var/www/iot-health-api  
