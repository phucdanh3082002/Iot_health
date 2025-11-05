# MySQL Cloud Setup Guide

Hướng dẫn setup MySQL Cloud Database trên PC cá nhân để sync dữ liệu từ Raspberry Pi.

---

## 📋 **YÊU CẦU**

- **PC/Laptop** với Windows/Linux/macOS
- **MySQL Server 8.0+** (hoặc MariaDB 10.5+)
- **Network connectivity** giữa PC và Raspberry Pi (LAN/WiFi)
- **~500 MB disk space** cho database
- **Port 3306** available (hoặc custom port)

---

## 🔧 **BƯỚC 1: CÀI ĐẶT MYSQL SERVER**

### **Windows:**

1. Download MySQL Installer: https://dev.mysql.com/downloads/installer/
2. Chạy installer, chọn "Custom"
3. Chọn components:
   - MySQL Server 8.0+
   - MySQL Workbench (optional, for GUI management)
4. Cấu hình:
   - Root password: Đặt password mạnh
   - Port: 3306 (default)
   - Service: Chọn "Start MySQL at system startup"

### **Linux (Ubuntu/Debian):**

```bash
# Update package list
sudo apt update

# Install MySQL Server
sudo apt install mysql-server

# Secure installation
sudo mysql_secure_installation

# Start MySQL service
sudo systemctl start mysql
sudo systemctl enable mysql

# Check status
sudo systemctl status mysql
```

### **macOS:**

```bash
# Install via Homebrew
brew install mysql

# Start MySQL service
brew services start mysql

# Secure installation
mysql_secure_installation
```

---

## 🗄️ **BƯỚC 2: TẠO DATABASE VÀ USER**

### **Option A: Sử dụng MySQL Workbench (GUI)**

1. Mở MySQL Workbench
2. Connect to MySQL Server (localhost:3306)
3. Mở SQL Editor
4. Copy và execute script: `scripts/mysql_schema.sql`

### **Option B: Sử dụng Command Line**

```bash
# Login as root
mysql -u root -p

# Execute schema script
source /path/to/IoT_health/scripts/mysql_schema.sql

# Verify database created
SHOW DATABASES;
USE iot_health_cloud;
SHOW TABLES;
```

### **Tạo Sync User (QUAN TRỌNG):**

```sql
-- Create dedicated user for IoT sync
CREATE USER 'iot_sync_user'@'%' 
IDENTIFIED BY 'YourStrongPassword123!';

-- Grant necessary privileges
GRANT SELECT, INSERT, UPDATE ON iot_health_cloud.* 
TO 'iot_sync_user'@'%';

-- Grant procedure execution
GRANT EXECUTE ON PROCEDURE iot_health_cloud.sp_cleanup_old_records 
TO 'iot_sync_user'@'%';

GRANT EXECUTE ON PROCEDURE iot_health_cloud.sp_patient_statistics 
TO 'iot_sync_user'@'%';

-- Apply changes
FLUSH PRIVILEGES;

-- Verify user created
SELECT User, Host FROM mysql.user WHERE User = 'iot_sync_user';
```

**⚠️ GHI CHÚ:** 
- Thay `YourStrongPassword123!` bằng password thật
- `'%'` cho phép connect từ mọi IP (dùng IP cụ thể cho security tốt hơn)
- Ví dụ IP cụ thể: `'iot_sync_user'@'192.168.1.50'` (Pi IP)

---

## 🌐 **BƯỚC 3: CẤU HÌNH NETWORK**

### **3.1. Tìm IP Address của PC:**

**Windows:**
```cmd
ipconfig
```
Tìm "IPv4 Address" (ví dụ: 192.168.1.100)

**Linux/macOS:**
```bash
ip addr show
# hoặc
ifconfig
```
Tìm inet address (ví dụ: 192.168.1.100)

### **3.2. Cấu hình MySQL để accept remote connections:**

**Linux:**

```bash
# Edit MySQL config
sudo nano /etc/mysql/mysql.conf.d/mysqld.cnf

# Tìm dòng:
bind-address = 127.0.0.1

# Đổi thành (cho phép tất cả IPs):
bind-address = 0.0.0.0

# Hoặc (cho phép chỉ LAN):
bind-address = 192.168.1.100

# Restart MySQL
sudo systemctl restart mysql
```

**Windows:**

1. Mở MySQL Workbench
2. Server → Options File
3. Networking → Bind Address → 0.0.0.0
4. Apply → Restart MySQL Service

### **3.3. Cấu hình Firewall:**

**Windows:**

```powershell
# Mở PowerShell as Admin
New-NetFirewallRule -DisplayName "MySQL Server" -Direction Inbound -Protocol TCP -LocalPort 3306 -Action Allow
```

**Linux (Ubuntu):**

```bash
# Allow MySQL port
sudo ufw allow 3306/tcp

# Check rules
sudo ufw status
```

### **3.4. Test connection từ Raspberry Pi:**

```bash
# Trên Raspberry Pi, test connection
mysql -h 192.168.1.100 -u iot_sync_user -p iot_health_cloud

# Nếu thành công, bạn sẽ thấy MySQL prompt:
# mysql>

# Exit
exit;
```

---

## 🔐 **BƯỚC 4: CẤU HÌNH SECURITY (Recommended)**

### **4.1. SSL/TLS Encryption (Optional nhưng recommended):**

```sql
-- Check SSL status
SHOW VARIABLES LIKE '%ssl%';

-- Require SSL for sync user
ALTER USER 'iot_sync_user'@'%' REQUIRE SSL;
```

Tạo SSL certificates (advanced):
```bash
# Generate certificates
sudo mysql_ssl_rsa_setup --uid=mysql
```

### **4.2. IP Whitelist (Recommended):**

```sql
-- Drop generic user
DROP USER 'iot_sync_user'@'%';

-- Create user with specific IP (Raspberry Pi IP)
CREATE USER 'iot_sync_user'@'192.168.1.50' 
IDENTIFIED BY 'YourStrongPassword123!';

-- Grant privileges
GRANT SELECT, INSERT, UPDATE ON iot_health_cloud.* 
TO 'iot_sync_user'@'192.168.1.50';

FLUSH PRIVILEGES;
```

### **4.3. Password trong Environment Variable (Raspberry Pi):**

```bash
# Trên Raspberry Pi
# Edit .bashrc or .profile
nano ~/.bashrc

# Thêm dòng:
export MYSQL_CLOUD_PASSWORD='YourStrongPassword123!'

# Reload
source ~/.bashrc

# Verify
echo $MYSQL_CLOUD_PASSWORD
```

---

## ⚙️ **BƯỚC 5: CẤU HÌNH RASPBERRY PI**

### **5.1. Cài đặt MySQL Client Library:**

```bash
# Trên Raspberry Pi
pip install pymysql

# Verify
python3 -c "import pymysql; print('PyMySQL installed successfully')"
```

### **5.2. Cập nhật app_config.yaml:**

```bash
cd ~/Desktop/IoT_health
nano config/app_config.yaml
```

**Tìm section `cloud:` và sửa:**

```yaml
cloud:
  enabled: true  # ✅ Bật cloud sync
  
  mysql:
    host: "192.168.1.100"  # ✅ IP của PC
    port: 3306
    database: "iot_health_cloud"
    user: "iot_sync_user"
    password_env: "MYSQL_CLOUD_PASSWORD"
    # password: "YourStrongPassword123!"  # Hoặc để trực tiếp (không khuyến nghị)
    
  sync:
    mode: "auto"  # Auto sync mỗi 5 phút
    interval_seconds: 300
    
  device:
    device_id: "rasp_pi_001"  # ✅ Đặt ID unique cho Pi
    device_name: "Living Room Monitor"  # ✅ Tên thiết bị
    location: "Home - Living Room"  # ✅ Vị trí
```

### **5.3. Test CloudSyncManager:**

```bash
cd ~/Desktop/IoT_health

# Test connection
python3 << 'EOF'
import sys
sys.path.append('.')
import yaml
from src.data.database import DatabaseManager

# Load config
with open('config/app_config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# Create database manager (will auto-init cloud sync)
db = DatabaseManager(config)
db.initialize()

# Check cloud sync status
if db.cloud_sync_manager:
    status = db.cloud_sync_manager.get_sync_status()
    print("Cloud Sync Status:")
    for key, value in status.items():
        print(f"  {key}: {value}")
    
    # Test connection
    if db.cloud_sync_manager.check_cloud_connection():
        print("\n✅ Cloud connection successful!")
    else:
        print("\n❌ Cloud connection failed!")
else:
    print("Cloud sync not enabled")

db.close()
EOF
```

**Kết quả mong đợi:**
```
Cloud Sync Status:
  is_online: True
  device_id: rasp_pi_001
  last_sync_time: None
  sync_mode: auto
  queue_size: 0
  cloud_connected: True
  sync_enabled: True

✅ Cloud connection successful!
```

---

## 🧪 **BƯỚC 6: TESTING**

### **6.1. Test manual push:**

```python
import sys
sys.path.append('.')
import yaml
from src.data.database import DatabaseManager
from datetime import datetime

# Load config
with open('config/app_config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# Init database
db = DatabaseManager(config)
db.initialize()

# Create test health record
test_data = {
    'patient_id': 'patient_001',
    'timestamp': datetime.now(),
    'heart_rate': 75.0,
    'spo2': 98.0,
    'temperature': 36.6
}

# Save to local (will auto-sync to cloud)
record_id = db.save_health_record(test_data)
print(f"Saved record ID: {record_id}")

# Check sync statistics
stats = db.cloud_sync_manager.get_sync_statistics()
print(f"\nSync Stats: {stats}")

db.close()
```

### **6.2. Verify data in MySQL:**

```sql
-- Trên PC MySQL
USE iot_health_cloud;

-- Check devices
SELECT * FROM devices;

-- Check health records
SELECT * FROM health_records ORDER BY timestamp DESC LIMIT 5;

-- Check sync statistics
SELECT 
    COUNT(*) as total_records,
    MIN(timestamp) as first_record,
    MAX(timestamp) as last_record
FROM health_records;
```

---

## 📊 **BƯỚC 7: MONITORING & MAINTENANCE**

### **7.1. Create monitoring script (PC):**

**monitor_db.sh:**
```bash
#!/bin/bash

mysql -u root -p iot_health_cloud << 'EOF'
SELECT 'Database Size:' as metric;
SELECT 
    ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'Size (MB)'
FROM information_schema.TABLES 
WHERE table_schema = 'iot_health_cloud';

SELECT '\nTable Record Counts:' as metric;
SELECT 
    table_name,
    table_rows
FROM information_schema.TABLES
WHERE table_schema = 'iot_health_cloud'
ORDER BY table_rows DESC;

SELECT '\nLatest Device Activity:' as metric;
SELECT * FROM v_device_status;

SELECT '\nActive Alerts:' as metric;
SELECT COUNT(*) as alert_count FROM v_active_alerts;
EOF
```

### **7.2. Automated cleanup (weekly cron job):**

```bash
# Add to crontab
crontab -e

# Cleanup old records every Sunday at 2 AM
0 2 * * 0 mysql -u root -p'password' iot_health_cloud -e "CALL sp_cleanup_old_records(90);"
```

### **7.3. Backup script:**

```bash
#!/bin/bash
# backup_mysql.sh

BACKUP_DIR="/path/to/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/iot_health_cloud_$DATE.sql"

# Create backup
mysqldump -u root -p iot_health_cloud > $BACKUP_FILE

# Compress
gzip $BACKUP_FILE

# Delete backups older than 30 days
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete

echo "Backup completed: $BACKUP_FILE.gz"
```

---

## 🐛 **TROUBLESHOOTING**

### **Problem 1: Connection refused**

```bash
# Check MySQL running
sudo systemctl status mysql

# Check port listening
netstat -tuln | grep 3306

# Check firewall
sudo ufw status
```

### **Problem 2: Access denied**

```sql
-- Verify user privileges
SHOW GRANTS FOR 'iot_sync_user'@'%';

-- Reset user password
ALTER USER 'iot_sync_user'@'%' IDENTIFIED BY 'NewPassword';
FLUSH PRIVILEGES;
```

### **Problem 3: Slow sync**

```sql
-- Check table optimization
OPTIMIZE TABLE health_records;
OPTIMIZE TABLE alerts;

-- Check indexes
SHOW INDEX FROM health_records;
```

### **Problem 4: Partition errors**

```sql
-- Add new partition for next year
ALTER TABLE health_records 
ADD PARTITION (
    PARTITION p2028 VALUES LESS THAN (2029)
);
```

---

## ✅ **CHECKLIST**

- [ ] MySQL Server installed và running
- [ ] Database `iot_health_cloud` created
- [ ] User `iot_sync_user` created với correct privileges
- [ ] Firewall configured (port 3306 open)
- [ ] MySQL bind-address set to 0.0.0.0 hoặc PC IP
- [ ] Connection tested từ Raspberry Pi
- [ ] Password set trong environment variable (Pi)
- [ ] `app_config.yaml` updated với correct IP/credentials
- [ ] CloudSyncManager test passed
- [ ] Test record synced successfully
- [ ] Monitoring scripts setup
- [ ] Backup strategy in place

---

## 📚 **TÀI LIỆU THAM KHẢO**

- MySQL Documentation: https://dev.mysql.com/doc/
- SQLAlchemy Documentation: https://docs.sqlalchemy.org/
- PyMySQL Documentation: https://pymysql.readthedocs.io/

---

## 🆘 **HỖ TRỢ**

Nếu gặp vấn đề, check logs:

**Raspberry Pi:**
```bash
tail -f ~/Desktop/IoT_health/logs/health_monitor.log
```

**MySQL (Linux):**
```bash
sudo tail -f /var/log/mysql/error.log
```

**MySQL (Windows):**
```
C:\ProgramData\MySQL\MySQL Server 8.0\Data\*.err
```

---

**Chúc bạn setup thành công! 🎉**
