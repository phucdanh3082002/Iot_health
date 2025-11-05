# ✅ PHASE 2 CHECKLIST - MySQL Workbench Setup

Hướng dẫn từng bước setup MySQL trên PC với MySQL Workbench.

---

## 📦 **PHẦN 1: CÀI ĐẶT (30-45 phút)**

### **Bước 1.1: Download MySQL**
- [ ] Truy cập: https://dev.mysql.com/downloads/installer/
- [ ] Download **Windows (x86, 32-bit), MSI Installer** (~400MB)
- [ ] Click "No thanks, just start my download"

### **Bước 1.2: Cài đặt MySQL**
- [ ] Chạy installer
- [ ] Chọn **"Custom"** setup type
- [ ] Chọn components:
  - [ ] ✅ MySQL Server 8.0+
  - [ ] ✅ MySQL Workbench 8.0+
- [ ] Click Next → Execute → chờ cài đặt

### **Bước 1.3: Cấu hình MySQL Server**

**Type and Networking:**
- [ ] Config Type: **Development Computer**
- [ ] Port: **3306**
- [ ] ✅ Tick **"Open Windows Firewall port for network access"**

**Authentication:**
- [ ] Method: **Use Strong Password Encryption**
- [ ] Root Password: `_______________________` (GHI LẠI!)
- [ ] Ví dụ: `MySQL_Root@2025`

**Windows Service:**
- [ ] Service Name: **MySQL80**
- [ ] ✅ Tick **"Start at System Startup"**
- [ ] Click Execute → Finish

### **Bước 1.4: Verify Installation**
- [ ] Mở **MySQL Workbench** từ Start Menu
- [ ] Thấy connection: **"Local instance MySQL80"**

---

## 🗄️ **PHẦN 2: TẠO DATABASE (15-20 phút)**

### **Bước 2.1: Copy Schema File từ Pi sang PC**

**Option A: USB Drive**
- [ ] Trên Pi, copy file:
  ```bash
  cp ~/Desktop/IoT_health/scripts/mysql_schema.sql /media/usb/
  ```
- [ ] Rút USB, cắm vào PC
- [ ] Copy sang PC: `C:\mysql_schema.sql`

**Option B: SCP/SFTP**
- [ ] Dùng WinSCP hoặc FileZilla
- [ ] Connect to Pi (IP: `____________`, user: `pi`)
- [ ] Download: `/home/pi/Desktop/IoT_health/scripts/mysql_schema.sql`

**Option C: Manual Copy**
- [ ] Trên Pi:
  ```bash
  cat ~/Desktop/IoT_health/scripts/mysql_schema.sql
  ```
- [ ] Copy output, paste vào Notepad trên PC
- [ ] Save as: `C:\mysql_schema.sql`

### **Bước 2.2: Execute Schema trong Workbench**
- [ ] Mở **MySQL Workbench**
- [ ] Click **"Local instance MySQL80"**
- [ ] Nhập root password
- [ ] Menu: **File** → **Open SQL Script**
- [ ] Chọn file: `C:\mysql_schema.sql`
- [ ] Click biểu tượng **⚡ Execute** (hoặc Ctrl+Shift+Enter)
- [ ] Chờ 5-10 giây

### **Bước 2.3: Verify Database Created**
Chạy SQL:
```sql
SHOW DATABASES;
-- Phải thấy: iot_health_cloud

USE iot_health_cloud;
SHOW TABLES;
-- Phải thấy 8 tables: devices, patients, health_records, alerts, etc.
```

- [ ] Database `iot_health_cloud` exists
- [ ] 8 tables created successfully

### **Bước 2.4: Tạo Sync User**
Copy và chạy SQL sau trong Workbench:

```sql
CREATE USER 'iot_sync_user'@'%' 
IDENTIFIED BY 'IotSync@2025!';  -- Đổi password mạnh hơn nếu muốn

GRANT SELECT, INSERT, UPDATE ON iot_health_cloud.* 
TO 'iot_sync_user'@'%';

GRANT EXECUTE ON PROCEDURE iot_health_cloud.sp_cleanup_old_records 
TO 'iot_sync_user'@'%';

GRANT EXECUTE ON PROCEDURE iot_health_cloud.sp_patient_statistics 
TO 'iot_sync_user'@'%';

FLUSH PRIVILEGES;

SELECT User, Host FROM mysql.user WHERE User = 'iot_sync_user';
```

- [ ] User created successfully
- [ ] Password ghi nhớ: `_______________________`

---

## 🌐 **PHẦN 3: CẤU HÌNH NETWORK (10-15 phút)**

### **Bước 3.1: Tìm IP của PC**

**Windows:**
- [ ] Win + R → gõ `cmd` → Enter
- [ ] Gõ: `ipconfig`
- [ ] Tìm **IPv4 Address** (ví dụ: 192.168.1.100)
- [ ] Ghi lại IP: `_______________________`

### **Bước 3.2: Cấu hình MySQL cho Remote**

**Trong MySQL Workbench:**
- [ ] Menu **Server** → **Options File**
- [ ] Tab **Networking**
- [ ] Tìm **bind_address**:
  - Đổi `127.0.0.1` → `0.0.0.0`
- [ ] Click **Apply**
- [ ] Restart MySQL:
  - Menu **Server** → **Startup / Shutdown**
  - **Stop Server** → chờ 2s → **Start Server**

### **Bước 3.3: Firewall**

**Option A: GUI**
- [ ] Win + R → gõ `wf.msc` → Enter
- [ ] **Inbound Rules** → **New Rule...**
- [ ] Port → TCP → 3306 → Allow → All profiles
- [ ] Name: **MySQL Server 3306**

**Option B: PowerShell (nhanh hơn)**
- [ ] Win + X → **PowerShell (Admin)**
- [ ] Chạy:
  ```powershell
  New-NetFirewallRule -DisplayName "MySQL Server" -Direction Inbound -Protocol TCP -LocalPort 3306 -Action Allow
  ```

---

## 🔌 **PHẦN 4: TEST CONNECTION TỪ PI (5-10 phút)**

### **Bước 4.1: Install MySQL Client**
Trên Raspberry Pi:
```bash
sudo apt update
sudo apt install mysql-client -y
```
- [ ] MySQL client installed

### **Bước 4.2: Test Connection**
Thay `192.168.1.XXX` bằng IP PC từ bước 3.1:
```bash
mysql -h 192.168.1.XXX -u iot_sync_user -p iot_health_cloud
```
Nhập password: `IotSync@2025!` (hoặc password bạn đặt)

- [ ] Connection successful (thấy `mysql>` prompt)

**Test query:**
```sql
SHOW TABLES;
exit;
```
- [ ] Tables hiển thị OK

**Nếu thất bại, check:**
- [ ] MySQL service running trên PC
- [ ] Firewall rule created
- [ ] bind-address = 0.0.0.0
- [ ] User/password correct

---

## ⚙️ **PHẦN 5: CẤU HÌNH RASPBERRY PI (10 phút)**

### **Bước 5.1: Install PyMySQL**
```bash
cd ~/Desktop/IoT_health
source .venv/bin/activate  # Nếu dùng venv
pip install pymysql
```
- [ ] PyMySQL installed
- [ ] Verify: `python3 -c "import pymysql; print('OK')"`

### **Bước 5.2: Set Password Environment Variable**
```bash
nano ~/.bashrc

# Thêm dòng cuối file:
export MYSQL_CLOUD_PASSWORD='IotSync@2025!'

# Lưu: Ctrl+X → Y → Enter

source ~/.bashrc
echo $MYSQL_CLOUD_PASSWORD  # Verify
```
- [ ] Environment variable set
- [ ] Verify shows password

### **Bước 5.3: Update app_config.yaml**
```bash
cd ~/Desktop/IoT_health
nano config/app_config.yaml
```

**Sửa section `cloud:`:**
```yaml
cloud:
  enabled: true  # ✅ Đổi từ false → true
  
  mysql:
    host: "192.168.1.XXX"  # ✅ Thay bằng IP PC từ bước 3.1
    port: 3306
    database: "iot_health_cloud"
    user: "iot_sync_user"
    password_env: "MYSQL_CLOUD_PASSWORD"
    
  device:
    device_id: "rasp_pi_001"  # ✅ Unique ID
    device_name: "Living Room Monitor"  # ✅ Friendly name
    location: "Home - Living Room"  # ✅ Location
```

- [ ] `cloud.enabled = true`
- [ ] `cloud.mysql.host` = IP PC
- [ ] `device_id` unique và descriptive
- [ ] Lưu file: Ctrl+X → Y → Enter

---

## 🧪 **PHẦN 6: TESTING (15 phút)**

### **Bước 6.1: Quick Connection Test**
```bash
cd ~/Desktop/IoT_health
python3 tests/quick_cloud_test.py
```

**Kết quả mong đợi:**
```
✅ Cloud sync enabled
✅ DatabaseManager initialized
✅ CloudSyncManager initialized
✅ MySQL connection successful!
✅ Saved health record locally: ID=1
🎉 AUTO-SYNC WORKING! Data pushed to cloud successfully!
```

- [ ] All tests pass
- [ ] No errors

**Nếu thất bại:**
- [ ] Check error message
- [ ] Verify all previous steps
- [ ] Check PC IP reachable: `ping 192.168.1.XXX`

### **Bước 6.2: Verify Data in MySQL Workbench**

**Trên PC, trong MySQL Workbench:**
```sql
USE iot_health_cloud;

-- Check device registered
SELECT * FROM devices;
-- Phải thấy: rasp_pi_001

-- Check health record synced
SELECT * FROM health_records ORDER BY timestamp DESC LIMIT 5;
-- Phải thấy record vừa tạo (HR=75, SpO2=98, Temp=36.6)
```

- [ ] Device registered in `devices` table
- [ ] Health record in `health_records` table
- [ ] Timestamp correct

### **Bước 6.3: Full Test Suite (Optional)**
```bash
python3 tests/test_cloud_sync.py
```
- [ ] All 6 tests pass

---

## 🎉 **COMPLETION CHECKLIST**

### **PC (MySQL Server):**
- [ ] MySQL Server 8.0+ installed
- [ ] MySQL Workbench installed
- [ ] Database `iot_health_cloud` created
- [ ] 8 tables exist (devices, patients, health_records, etc.)
- [ ] User `iot_sync_user` created với privileges
- [ ] Firewall allows port 3306
- [ ] bind-address = 0.0.0.0
- [ ] MySQL service running
- [ ] PC IP known: `_______________________`

### **Raspberry Pi:**
- [ ] PyMySQL installed
- [ ] Environment variable `MYSQL_CLOUD_PASSWORD` set
- [ ] `app_config.yaml` updated:
  - [ ] `cloud.enabled = true`
  - [ ] `cloud.mysql.host` = PC IP
  - [ ] `device.device_id` unique
- [ ] MySQL client can connect to PC
- [ ] Quick test passed
- [ ] Data appears in MySQL Workbench

### **Network:**
- [ ] PC and Pi on same LAN/WiFi
- [ ] PC IP is 192.168.x.x or 10.x.x.x (not 127.0.0.1)
- [ ] Ping works: Pi → PC
- [ ] MySQL port 3306 accessible
- [ ] No VPN/proxy blocking connection

---

## 📊 **POST-SETUP MONITORING**

### **Daily Checks (PC - MySQL Workbench):**
```sql
-- Database size
SELECT 
    ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'Size_MB'
FROM information_schema.TABLES 
WHERE table_schema = 'iot_health_cloud';

-- Record counts
SELECT 
    'devices' as table_name, COUNT(*) as count FROM devices
UNION ALL
SELECT 'health_records', COUNT(*) FROM health_records
UNION ALL
SELECT 'alerts', COUNT(*) FROM alerts;

-- Latest activity
SELECT * FROM v_device_status;
SELECT * FROM v_latest_vitals;
```

### **Weekly Maintenance:**
```sql
-- Cleanup old records (keep 90 days)
CALL sp_cleanup_old_records(90);

-- Optimize tables
OPTIMIZE TABLE health_records;
OPTIMIZE TABLE alerts;
```

---

## 🆘 **TROUBLESHOOTING GUIDE**

### **Problem: "Can't connect to MySQL server"**
**Checklist:**
- [ ] MySQL service running: Workbench → Server → Startup/Shutdown
- [ ] Firewall rule exists: `wf.msc` → check Inbound Rules
- [ ] bind-address correct: Workbench → Server → Options File → Networking
- [ ] PC IP correct: `ipconfig` in cmd
- [ ] Ping works from Pi: `ping PC_IP`

### **Problem: "Access denied for user"**
**Checklist:**
- [ ] User exists: `SELECT * FROM mysql.user WHERE User='iot_sync_user';`
- [ ] Password correct in environment variable: `echo $MYSQL_CLOUD_PASSWORD`
- [ ] Privileges granted: `SHOW GRANTS FOR 'iot_sync_user'@'%';`
- [ ] Flush privileges run: `FLUSH PRIVILEGES;`

### **Problem: "No data in cloud"**
**Checklist:**
- [ ] `cloud.enabled = true` in config
- [ ] CloudSyncManager initialized: check quick_cloud_test.py output
- [ ] Queue size: check sync statistics
- [ ] Network online: `ping PC_IP`
- [ ] Check Pi logs: `tail -f logs/health_monitor.log`

### **Problem: "Slow sync"**
**Solution:**
```sql
-- Add indexes if missing
CREATE INDEX idx_patient_timestamp ON health_records(patient_id, timestamp);
CREATE INDEX idx_device_timestamp ON health_records(device_id, timestamp);

-- Optimize tables
OPTIMIZE TABLE health_records;
```

---

## 📚 **USEFUL QUERIES**

### **View all devices:**
```sql
SELECT device_id, device_name, location, last_seen, is_active 
FROM devices 
ORDER BY last_seen DESC;
```

### **Latest vitals per patient:**
```sql
SELECT * FROM v_latest_vitals;
```

### **Active alerts:**
```sql
SELECT * FROM v_active_alerts;
```

### **Patient statistics:**
```sql
CALL sp_patient_statistics('patient_001');
```

### **Health records count by day:**
```sql
SELECT 
    DATE(timestamp) as date,
    COUNT(*) as record_count,
    AVG(heart_rate) as avg_hr,
    AVG(spo2) as avg_spo2
FROM health_records
WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY DATE(timestamp)
ORDER BY date DESC;
```

---

## ✅ **SUCCESS CRITERIA**

Bạn đã hoàn thành Phase 2 khi:

✅ **MySQL running trên PC**
✅ **Database created với 8 tables**
✅ **Raspberry Pi connect được đến MySQL**
✅ **Quick test passed**
✅ **Data sync automatically từ Pi → PC**
✅ **Data visible trong MySQL Workbench**

---

**🎊 Chúc mừng! Bạn đã hoàn thành Phase 2!**

**Next Steps:**
- Run full application: `python3 main.py`
- Take measurements → data auto-syncs to cloud
- Monitor via MySQL Workbench
- Setup backup strategy (see MYSQL_SETUP_GUIDE.md)

