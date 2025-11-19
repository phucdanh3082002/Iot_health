# 🖥️ IoT Health Monitor - Server Deployment Guide

## 📋 Server Information

### **Production Server**
- **Cloud Provider**: AWS EC2
- **Public IP**: `47.130.193.237`
- **Region**: Singapore (ap-southeast-1)
- **OS**: Ubuntu 20.04/22.04 LTS
- **Instance Type**: t2.micro / t3.small (recommended)

### **Database Server**
- **Service**: AWS RDS MySQL 8.0+
- **Endpoint**: `database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com`
- **Port**: 3306
- **Database**: `iot_health_cloud`
- **Schema Version**: 2.0.0

---

## 🏗️ Server Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Internet/Clients                          │
│  (Raspberry Pi, Android App, Web Dashboard)                 │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │   Public IP             │
        │   47.130.193.237        │
        │   (AWS EC2)             │
        └────────────┬─────────────┘
                     │
        ┌────────────▼─────────────┐
        │   Nginx (Port 80/443)    │
        │   Reverse Proxy          │
        └────────────┬─────────────┘
                     │
        ┌────────────▼─────────────┐
        │   Flask API (Port 8000)  │
        │   Gunicorn WSGI          │
        └────────────┬─────────────┘
                     │
        ┌────────────▼─────────────┐
        │   AWS RDS MySQL          │
        │   iot_health_cloud       │
        └──────────────────────────┘
```

---

## 📁 Server Directory Structure

```
/var/www/iot-health-api/
├── app.py                          # Main Flask application (flask_api_pairing.py)
├── .env                            # Environment variables (passwords, config)
├── requirements.txt                # Python dependencies
├── venv/                           # Python virtual environment
├── logs/
│   ├── api.log                     # Application logs
│   ├── error.log                   # Error logs
│   └── access.log                  # Access logs
└── backups/                        # Database backup scripts (optional)

/etc/nginx/
├── nginx.conf                      # Main Nginx config
└── sites-available/
    └── iot-health-api              # API site config

/etc/systemd/system/
└── iot-health-api.service          # Systemd service for auto-start

/home/ubuntu/
├── .ssh/                           # SSH keys
└── scripts/                        # Deployment scripts (optional)
```

---

## 🔧 Server Configuration

### **1. System Packages**
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y python3 python3-pip python3-venv nginx git curl

# Install MySQL client (for database access)
sudo apt install -y mysql-client
```

### **2. Python Environment**
```bash
# Create application directory
sudo mkdir -p /var/www/iot-health-api
sudo chown -R ubuntu:ubuntu /var/www/iot-health-api

# Create virtual environment
cd /var/www/iot-health-api
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install flask flask-cors mysql-connector-python python-dotenv gunicorn
```

**requirements.txt**:
```txt
flask==3.0.0
flask-cors==4.0.0
mysql-connector-python==8.2.0
python-dotenv==1.0.0
gunicorn==21.2.0
```

### **3. Environment Variables (.env)**
```bash
# /var/www/iot-health-api/.env
DB_HOST=database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com
DB_PORT=3306
DB_USER=admin
DB_NAME=iot_health_cloud
MYSQL_PASSWORD=<your_secure_password>

# Flask config
FLASK_ENV=production
FLASK_DEBUG=False
```

**Security**: 
```bash
# Set proper permissions
chmod 600 /var/www/iot-health-api/.env
chown ubuntu:ubuntu /var/www/iot-health-api/.env
```

---

## 🚀 Application Deployment

### **1. Deploy Flask API**
```bash
# Copy app.py from local to server
scp scripts/flask_api_pairing.py ubuntu@47.130.193.237:/var/www/iot-health-api/app.py

# Or clone from GitHub
cd /var/www/iot-health-api
git clone https://github.com/danhsidoi1234/Iot_health.git temp
cp temp/scripts/flask_api_pairing.py app.py
rm -rf temp
```

### **2. Test Flask Application**
```bash
cd /var/www/iot-health-api
source venv/bin/activate
python app.py
# Should see: * Running on http://0.0.0.0:8000

# Test from another terminal
curl http://localhost:8000/api/health
```

### **3. Setup Gunicorn Service**

**/etc/systemd/system/iot-health-api.service**:
```ini
[Unit]
Description=IoT Health Monitor API v2.0
After=network.target

[Service]
Type=notify
User=ubuntu
Group=ubuntu
WorkingDirectory=/var/www/iot-health-api
Environment="PATH=/var/www/iot-health-api/venv/bin"
ExecStart=/var/www/iot-health-api/venv/bin/gunicorn \
    --workers 4 \
    --bind 0.0.0.0:8000 \
    --timeout 120 \
    --access-logfile /var/www/iot-health-api/logs/access.log \
    --error-logfile /var/www/iot-health-api/logs/error.log \
    --log-level info \
    app:app

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Start service**:
```bash
# Create log directory
mkdir -p /var/www/iot-health-api/logs

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable iot-health-api
sudo systemctl start iot-health-api

# Check status
sudo systemctl status iot-health-api

# View logs
sudo journalctl -u iot-health-api -f
```

---

## 🌐 Nginx Configuration

### **/etc/nginx/sites-available/iot-health-api**
```nginx
# HTTP server (redirect to HTTPS in production)
server {
    listen 80;
    listen [::]:80;
    server_name 47.130.193.237;

    # API endpoint
    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # CORS headers (if needed)
        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Content-Type, Authorization' always;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Health check
    location /health {
        proxy_pass http://127.0.0.1:8000/api/health;
        access_log off;
    }

    # API documentation (optional)
    location / {
        return 200 '{"status":"ok","api_version":"2.0.0","endpoints":["/api/health","/api/pair-device","/api/devices/<user_id>","/api/patient","/api/generate-pairing-code","/api/devices/<device_id>/status"]}';
        add_header Content-Type application/json;
    }
}
```

**Enable site**:
```bash
# Create symlink
sudo ln -s /etc/nginx/sites-available/iot-health-api /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

---

## 🔒 Security Configuration

### **1. Firewall (UFW)**
```bash
# Enable UFW
sudo ufw enable

# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Check status
sudo ufw status
```

### **2. SSH Hardening**
```bash
# Edit SSH config
sudo nano /etc/ssh/sshd_config

# Recommended settings:
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
Port 22

# Restart SSH
sudo systemctl restart sshd
```

### **3. Database Security**
- ✅ RDS Security Group: Only allow EC2 instance IP
- ✅ Use strong password (minimum 16 characters)
- ✅ Rotate credentials regularly
- ✅ Enable SSL/TLS for MySQL connections

### **4. Application Security**
```bash
# Set proper file permissions
sudo chown -R ubuntu:ubuntu /var/www/iot-health-api
sudo chmod 755 /var/www/iot-health-api
sudo chmod 600 /var/www/iot-health-api/.env
sudo chmod 644 /var/www/iot-health-api/app.py
```

---

## 📊 Monitoring & Maintenance

### **1. System Monitoring**
```bash
# CPU and Memory
htop

# Disk usage
df -h

# Network connections
sudo netstat -tulnp | grep :8000

# Process status
ps aux | grep gunicorn
```

### **2. Application Logs**
```bash
# API logs
tail -f /var/www/iot-health-api/logs/access.log
tail -f /var/www/iot-health-api/logs/error.log

# System logs
sudo journalctl -u iot-health-api -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### **3. Database Monitoring**
```bash
# Connect to MySQL
mysql -h database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com \
      -u admin -p iot_health_cloud

# Check tables
SHOW TABLES;

# Check device count
SELECT COUNT(*) FROM devices;

# Check recent health records
SELECT COUNT(*) FROM health_records 
WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR);
```

### **4. Performance Tuning**
```bash
# Gunicorn workers (2-4 × CPU cores)
# Edit /etc/systemd/system/iot-health-api.service
--workers 4

# Nginx worker processes
# Edit /etc/nginx/nginx.conf
worker_processes auto;
worker_connections 1024;
```

---

## 🔄 Deployment Workflow

### **Development → Production**
```bash
# 1. Test locally on Raspberry Pi
cd /home/pi/Desktop/IoT_health
python scripts/flask_api_pairing.py

# 2. Commit to GitHub
git add scripts/flask_api_pairing.py
git commit -m "Update API to v2.0.0"
git push origin main

# 3. Deploy to server
ssh ubuntu@47.130.193.237
cd /var/www/iot-health-api
git pull origin main  # If using git
# OR
# Use scp to copy file

# 4. Restart service
sudo systemctl restart iot-health-api

# 5. Verify deployment
curl http://localhost:8000/api/health
```

---

## 🧪 API Testing (From Server)

### **1. Health Check**
```bash
curl http://localhost:8000/api/health
```

**Expected Response**:
```json
{
  "status": "ok",
  "database": "connected",
  "timestamp": "2025-11-20T10:30:00.123456",
  "api_version": "2.0.0",
  "schema_version": "2.0.0",
  "device_count": 1
}
```

### **2. Generate Pairing Code**
```bash
curl -X POST http://localhost:8000/api/generate-pairing-code \
  -H "Content-Type: application/json" \
  -d '{"device_id":"rpi_bp_001"}'
```

### **3. Pair Device**
```bash
curl -X POST http://localhost:8000/api/pair-device \
  -H "Content-Type: application/json" \
  -d '{
    "pairing_code":"A1B2C3D4",
    "user_id":"test_user_001",
    "nickname":"Test Device"
  }'
```

### **4. Get Device Status**
```bash
curl http://localhost:8000/api/devices/rpi_bp_001/status
```

### **5. Get User Devices**
```bash
curl http://localhost:8000/api/devices/test_user_001
```

---

## 🌍 External Access (From Raspberry Pi/Android)

### **Base URL**: `http://47.130.193.237`

### **Endpoints**:
```python
# Python (Raspberry Pi)
import requests

BASE_URL = "http://47.130.193.237"

# Generate pairing code
response = requests.post(
    f"{BASE_URL}/api/generate-pairing-code",
    json={"device_id": "rpi_bp_001"}
)

# Verify device pairing
response = requests.post(
    f"{BASE_URL}/api/pair-device",
    json={
        "pairing_code": "A1B2C3D4",
        "user_id": "android_user_123",
        "nickname": "My BP Monitor"
    }
)
```

```kotlin
// Kotlin (Android App)
val baseUrl = "http://47.130.193.237"

// Verify pairing
val response = httpClient.post("$baseUrl/api/pair-device") {
    contentType(ContentType.Application.Json)
    setBody(mapOf(
        "pairing_code" to "A1B2C3D4",
        "user_id" to userId,
        "nickname" to deviceNickname
    ))
}
```

---

## 🔧 Troubleshooting

### **API not responding**
```bash
# Check service status
sudo systemctl status iot-health-api

# Check logs
sudo journalctl -u iot-health-api -n 50

# Restart service
sudo systemctl restart iot-health-api
```

### **Database connection errors**
```bash
# Test MySQL connection
mysql -h database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com \
      -u admin -p

# Check RDS Security Group (AWS Console)
# Allow EC2 instance security group

# Verify credentials in .env
cat /var/www/iot-health-api/.env
```

### **Nginx errors**
```bash
# Check Nginx status
sudo systemctl status nginx

# Test configuration
sudo nginx -t

# View error logs
sudo tail -f /var/log/nginx/error.log

# Restart Nginx
sudo systemctl restart nginx
```

### **Port already in use**
```bash
# Find process using port 8000
sudo lsof -i :8000

# Kill process
sudo kill -9 <PID>

# Restart service
sudo systemctl restart iot-health-api
```

---

## 📦 Backup & Recovery

### **Database Backup**
```bash
# Backup MySQL database
mysqldump -h database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com \
          -u admin -p iot_health_cloud > backup_$(date +%Y%m%d).sql

# Restore from backup
mysql -h database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com \
      -u admin -p iot_health_cloud < backup_20251120.sql
```

### **Application Backup**
```bash
# Backup application code
tar -czf iot-health-api-backup-$(date +%Y%m%d).tar.gz \
    /var/www/iot-health-api

# Backup environment variables
sudo cp /var/www/iot-health-api/.env \
    /home/ubuntu/backups/.env.$(date +%Y%m%d)
```

---

## 📈 Scaling Considerations

### **Vertical Scaling (Upgrade Instance)**
- t2.micro → t3.small (2 vCPU, 2GB RAM)
- t3.small → t3.medium (2 vCPU, 4GB RAM)

### **Horizontal Scaling (Load Balancer)**
```
AWS ELB → EC2 Instance 1 (47.130.193.237)
       → EC2 Instance 2 (New IP)
       → EC2 Instance 3 (New IP)
```

### **Database Scaling**
- RDS Read Replicas for read-heavy workloads
- Multi-AZ deployment for high availability

---

## 📞 Quick Reference

### **SSH Access**
```bash
ssh ubuntu@47.130.193.237
```

### **Important Commands**
```bash
# Restart API
sudo systemctl restart iot-health-api

# View logs
sudo journalctl -u iot-health-api -f

# Restart Nginx
sudo systemctl restart nginx

# Test API
curl http://localhost:8000/api/health

# Connect to database
mysql -h database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com -u admin -p
```

### **File Locations**
- Application: `/var/www/iot-health-api/app.py`
- Environment: `/var/www/iot-health-api/.env`
- Logs: `/var/www/iot-health-api/logs/`
- Service: `/etc/systemd/system/iot-health-api.service`
- Nginx: `/etc/nginx/sites-available/iot-health-api`

---

*Last Updated: 2025-11-20*  
*Server IP: 47.130.193.237*  
*API Version: 2.0.0*  
*Database Schema: 2.0.0*
