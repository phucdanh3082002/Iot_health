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


API :
#!/usr/bin/env python3
"""
Flask API Implementation cho IoT Health Monitor (v2.0.0)
Triển khai trên AWS EC2 với endpoint /api/pair-device theo specification
Compatible with Database Schema v2.0.0
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
import os
from datetime import datetime, timedelta
import json
import secrets

app = Flask(__name__)
CORS(app)  # Enable CORS for web dashboard and Android app

# Database configuration
DB_CONFIG = {
    'host': 'database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com',
    'user': os.getenv('DB_USER', 'admin'),
    'password': os.getenv('MYSQL_PASSWORD', 'your_mysql_password'),
    'database': 'iot_health_cloud',
    'port': 3306,
    'charset': 'utf8mb4'
}

def get_db_connection():
    """Get database connection"""
    return mysql.connector.connect(**DB_CONFIG)

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM devices")
        device_count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return jsonify({
            'status': 'ok',
            'database': 'connected',
            'timestamp': datetime.utcnow().isoformat(),
            'api_version': '2.0.0',
            'schema_version': '2.0.0',
            'device_count': device_count
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'database': 'disconnected',
            'error': str(e)
        }), 500

@app.route('/api/pair-device', methods=['POST'])
def pair_device():
    """
    Pair device endpoint - Patient info sẽ được thêm sau từ Android app
    Response trả về patient_info = null nếu chưa có thông tin
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400

        pairing_code = data.get('pairing_code')
        user_id = data.get('user_id')
        nickname = data.get('nickname')

        if not all([pairing_code, user_id, nickname]):
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields: pairing_code, user_id, nickname'
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 1. Verify pairing code exists and get device info
        cursor.execute("""
            SELECT d.*, p.patient_id, p.name as patient_name, p.age, p.gender
            FROM devices d
            LEFT JOIN patients p ON d.device_id = p.device_id
            WHERE d.pairing_code = %s AND d.is_active = 1
        """, (pairing_code,))

        device_result = cursor.fetchone()

        if not device_result:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Invalid pairing code or device not active'
            }), 400
        
        # Check pairing code expiry (10 minutes from creation)
        if device_result.get('pairing_qr_data'):
            try:
                qr_data = json.loads(device_result['pairing_qr_data'])
                expires_at = datetime.fromisoformat(qr_data.get('expires_at', ''))
                if datetime.utcnow() > expires_at:
                    cursor.close()
                    conn.close()
                    return jsonify({
                        'status': 'error',
                        'message': 'Pairing code expired. Please generate a new code.'
                    }), 400
            except (json.JSONDecodeError, ValueError, KeyError):
                pass  # Continue if QR data is invalid or missing expiry

        device_id = device_result['device_id']

        # 2. Check if device already paired with this user
        cursor.execute("""
            SELECT * FROM device_ownership
            WHERE device_id = %s AND user_id = %s
        """, (device_id, user_id))

        existing_pairing = cursor.fetchone()

        if existing_pairing:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Device already paired with this user'
            }), 409

        # 3. Check if device already paired with another user
        cursor.execute("""
            SELECT * FROM device_ownership
            WHERE device_id = %s
        """, (device_id,))

        other_pairing = cursor.fetchone()

        if other_pairing and other_pairing['user_id'] != user_id:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Device already paired with another user'
            }), 409

        # 4. Insert/update device ownership
        cursor.execute("""
            INSERT INTO device_ownership (user_id, device_id, role, nickname, added_at, last_accessed)
            VALUES (%s, %s, 'owner', %s, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                nickname = VALUES(nickname),
                last_accessed = NOW()
        """, (user_id, device_id, nickname))
        
        # 5. Update device paired status and clear pairing code
        cursor.execute("""
            UPDATE devices
            SET paired_by = %s,
                paired_at = NOW(),
                pairing_code = NULL,
                pairing_qr_data = NULL,
                last_seen = NOW()
            WHERE device_id = %s
        """, (user_id, device_id))

        # 6. Get patient thresholds (nếu patient_id có sẵn)
        thresholds = {}
        if device_result.get('patient_id'):
            cursor.execute("""
                SELECT vital_sign, min_normal, max_normal, min_critical, max_critical
                FROM patient_thresholds
                WHERE patient_id = %s
                ORDER BY vital_sign
            """, (device_result['patient_id'],))

            thresholds_result = cursor.fetchall()

            # Convert thresholds to dict format
            for threshold in thresholds_result:
                thresholds[threshold['vital_sign']] = {
                    'min_normal': float(threshold['min_normal']),
                    'max_normal': float(threshold['max_normal']),
                    'min_critical': float(threshold['min_critical']),
                    'max_critical': float(threshold['max_critical'])
                }

        conn.commit()
        cursor.close()
        conn.close()

        # 7. Build response - patient_info = null nếu chưa có
        patient_info = None
        commands_topic = None
        
        if device_result.get('patient_id'):
            patient_info = {
                'patient_id': device_result['patient_id'],
                'name': device_result['patient_name'],
                'age': device_result['age'],
                'gender': device_result['gender']
            }
            commands_topic = f'iot_health/patient/{device_result["patient_id"]}/commands'
        
        response_data = {
            'device_info': {
                'device_id': device_result['device_id'],
                'device_name': device_result['device_name'],
                'device_type': device_result['device_type'],
                'location': device_result['location'],
                'nickname': nickname
            },
            'patient_info': patient_info,
            'mqtt_topics': {
                'vitals': f'iot_health/device/{device_id}/vitals',
                'alerts': f'iot_health/device/{device_id}/alerts',
                'status': f'iot_health/device/{device_id}/status',
                'commands': commands_topic
            },
            'thresholds': thresholds
        }

        return jsonify({
            'status': 'success',
            'message': 'Device paired successfully',
            'data': response_data
        })

    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/devices/<user_id>', methods=['GET'])
def get_user_devices(user_id):
    """Get all devices paired with a user"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                d.device_id,
                d.device_name,
                d.device_type,
                d.location,
                d.firmware_version,
                d.os_version,
                do.nickname,
                do.role,
                do.added_at,
                do.last_accessed,
                d.last_seen,
                d.is_active,
                p.patient_id,
                p.name as patient_name,
                p.age,
                p.gender,
                p.is_active as patient_active
            FROM devices d
            JOIN device_ownership do ON d.device_id = do.device_id
            LEFT JOIN patients p ON d.device_id = p.device_id AND p.is_active = 1
            WHERE do.user_id = %s
            ORDER BY do.added_at DESC
        """, (user_id,))

        devices = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'devices': devices
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/patients', methods=['POST'])
def create_patient():
    """
    Tạo patient mới (không cần device ngay)
    Cho phép user tạo thông tin bệnh nhân trước, gán device sau
    Owner và Caregiver đều có quyền tạo
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400

        user_id = data.get('user_id')
        name = data.get('name')
        age = data.get('age')
        gender = data.get('gender')
        medical_conditions = data.get('medical_conditions')  # Array hoặc JSON
        emergency_contact = data.get('emergency_contact')    # JSON object
        patient_id = data.get('patient_id')  # Optional, auto-generate nếu không có

        if not all([user_id, name]):
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields: user_id, name'
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Generate patient_id if not provided
        if not patient_id:
            import hashlib
            patient_id = f"patient_{hashlib.md5((user_id + name + str(datetime.utcnow())).encode()).hexdigest()[:12]}"

        # Convert JSON fields to string
        medical_conditions_json = json.dumps(medical_conditions) if medical_conditions else None
        emergency_contact_json = json.dumps(emergency_contact) if emergency_contact else None

        # Create new patient (device_id = NULL ban đầu)
        cursor.execute("""
            INSERT INTO patients (patient_id, device_id, name, age, gender, medical_conditions, emergency_contact, is_active, created_at)
            VALUES (%s, NULL, %s, %s, %s, %s, %s, 1, NOW())
        """, (patient_id, name, age, gender, medical_conditions_json, emergency_contact_json))

        # Tạo default thresholds cho patient mới
        default_thresholds = [
            (patient_id, 'heart_rate', 60, 100, 40, 120),
            (patient_id, 'spo2', 95, 100, 90, 100),
            (patient_id, 'temperature', 36.1, 37.2, 35.0, 39.0),
            (patient_id, 'systolic_bp', 90, 120, 70, 180),
            (patient_id, 'diastolic_bp', 60, 80, 40, 110)
        ]

        cursor.executemany("""
            INSERT INTO patient_thresholds (patient_id, vital_sign, min_normal, max_normal, min_critical, max_critical)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, default_thresholds)

        conn.commit()

        # Get created patient info
        cursor.execute("""
            SELECT patient_id, device_id, name, age, gender, medical_conditions, emergency_contact, is_active
            FROM patients
            WHERE patient_id = %s
        """, (patient_id,))

        patient = cursor.fetchone()

        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'message': 'Patient created successfully',
            'data': {
                'patient_id': patient['patient_id'],
                'device_id': patient['device_id'],
                'name': patient['name'],
                'age': patient['age'],
                'gender': patient['gender'],
                'medical_conditions': json.loads(patient['medical_conditions']) if patient['medical_conditions'] else None,
                'emergency_contact': json.loads(patient['emergency_contact']) if patient['emergency_contact'] else None,
                'is_active': bool(patient['is_active'])
            }
        })

    except mysql.connector.IntegrityError as e:
        return jsonify({
            'status': 'error',
            'message': f'Patient ID already exists or constraint violation: {str(e)}'
        }), 409
    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/patients/<patient_id>', methods=['PUT'])
def update_patient(patient_id):
    """
    Cập nhật thông tin patient
    Owner và Caregiver có quyền sửa
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400

        user_id = data.get('user_id')
        name = data.get('name')
        age = data.get('age')
        gender = data.get('gender')
        medical_conditions = data.get('medical_conditions')
        emergency_contact = data.get('emergency_contact')

        if not user_id:
            return jsonify({
                'status': 'error',
                'message': 'Missing required field: user_id'
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get patient's device_id (nếu có)
        cursor.execute("""
            SELECT device_id FROM patients WHERE patient_id = %s
        """, (patient_id,))

        patient = cursor.fetchone()

        if not patient:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Patient not found'
            }), 404

        # Verify user có quyền (owner hoặc caregiver)
        if patient['device_id']:
            cursor.execute("""
                SELECT role FROM device_ownership
                WHERE device_id = %s AND user_id = %s
                AND role IN ('owner', 'caregiver')
            """, (patient['device_id'], user_id))

            ownership = cursor.fetchone()

            if not ownership:
                cursor.close()
                conn.close()
                return jsonify({
                    'status': 'error',
                    'message': 'User does not have permission to update this patient'
                }), 403

        # Update patient info
        update_fields = []
        update_values = []

        if name is not None:
            update_fields.append('name = %s')
            update_values.append(name)
        if age is not None:
            update_fields.append('age = %s')
            update_values.append(age)
        if gender is not None:
            update_fields.append('gender = %s')
            update_values.append(gender)
        if medical_conditions is not None:
            update_fields.append('medical_conditions = %s')
            update_values.append(json.dumps(medical_conditions))
        if emergency_contact is not None:
            update_fields.append('emergency_contact = %s')
            update_values.append(json.dumps(emergency_contact))

        update_fields.append('updated_at = NOW()')
        update_values.append(patient_id)

        cursor.execute(f"""
            UPDATE patients
            SET {', '.join(update_fields)}
            WHERE patient_id = %s
        """, tuple(update_values))

        conn.commit()

        # Get updated patient info
        cursor.execute("""
            SELECT patient_id, device_id, name, age, gender, medical_conditions, emergency_contact, is_active
            FROM patients
            WHERE patient_id = %s
        """, (patient_id,))

        updated_patient = cursor.fetchone()

        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'message': 'Patient updated successfully',
            'data': {
                'patient_id': updated_patient['patient_id'],
                'device_id': updated_patient['device_id'],
                'name': updated_patient['name'],
                'age': updated_patient['age'],
                'gender': updated_patient['gender'],
                'medical_conditions': json.loads(updated_patient['medical_conditions']) if updated_patient['medical_conditions'] else None,
                'emergency_contact': json.loads(updated_patient['emergency_contact']) if updated_patient['emergency_contact'] else None,
                'is_active': bool(updated_patient['is_active'])
            }
        })

    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/patients/<patient_id>/assign-device', methods=['POST'])
def assign_device_to_patient(patient_id):
    """
    Gán device cho patient (sau khi đã pair device)
    Owner và Caregiver có quyền gán
    1 device = 1 patient (1:1 relationship)
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400

        user_id = data.get('user_id')
        device_id = data.get('device_id')

        if not all([user_id, device_id]):
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields: user_id, device_id'
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Verify user owns/manages this device (owner hoặc caregiver)
        cursor.execute("""
            SELECT role FROM device_ownership
            WHERE device_id = %s AND user_id = %s
            AND role IN ('owner', 'caregiver')
        """, (device_id, user_id))

        ownership = cursor.fetchone()

        if not ownership:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'User does not have permission for this device'
            }), 403

        # Verify patient exists
        cursor.execute("""
            SELECT patient_id, device_id, name FROM patients WHERE patient_id = %s
        """, (patient_id,))

        patient = cursor.fetchone()

        if not patient:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Patient not found'
            }), 404

        # Check if device already assigned to another patient
        cursor.execute("""
            SELECT patient_id, name FROM patients
            WHERE device_id = %s AND patient_id != %s AND is_active = 1
        """, (device_id, patient_id))

        existing_assignment = cursor.fetchone()

        if existing_assignment:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': f'Device already assigned to patient: {existing_assignment["name"]} ({existing_assignment["patient_id"]})'
            }), 409

        # Assign device to patient
        cursor.execute("""
            UPDATE patients
            SET device_id = %s,
                updated_at = NOW()
            WHERE patient_id = %s
        """, (device_id, patient_id))

        conn.commit()

        # Get updated info
        cursor.execute("""
            SELECT p.patient_id, p.device_id, p.name, p.age, p.gender,
                   d.device_name, do.nickname
            FROM patients p
            JOIN devices d ON p.device_id = d.device_id
            LEFT JOIN device_ownership do ON d.device_id = do.device_id AND do.user_id = %s
            WHERE p.patient_id = %s
        """, (user_id, patient_id))

        result = cursor.fetchone()

        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'message': 'Device assigned to patient successfully',
            'data': {
                'patient_id': result['patient_id'],
                'patient_name': result['name'],
                'device_id': result['device_id'],
                'device_name': result['device_name'],
                'device_nickname': result['nickname'],
                'mqtt_commands_topic': f'iot_health/patient/{patient_id}/commands'
            }
        })

    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/patients', methods=['GET'])
def get_patients():
    """
    Lấy danh sách patients của user (dựa trên devices đã pair)
    """
    try:
        user_id = request.args.get('user_id')

        if not user_id:
            return jsonify({
                'status': 'error',
                'message': 'Missing required parameter: user_id'
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get all patients associated with user's devices
        cursor.execute("""
            SELECT
                p.patient_id,
                p.device_id,
                p.name,
                p.age,
                p.gender,
                p.medical_conditions,
                p.emergency_contact,
                p.is_active,
                p.created_at,
                p.updated_at,
                d.device_name,
                do.nickname as device_nickname,
                do.role as user_role
            FROM patients p
            LEFT JOIN devices d ON p.device_id = d.device_id
            LEFT JOIN device_ownership do ON d.device_id = do.device_id AND do.user_id = %s
            WHERE p.is_active = 1
            ORDER BY p.created_at DESC
        """, (user_id,))

        patients = cursor.fetchall()

        cursor.close()
        conn.close()

        # Format response
        result = []
        for patient in patients:
            result.append({
                'patient_id': patient['patient_id'],
                'device_id': patient['device_id'],
                'name': patient['name'],
                'age': patient['age'],
                'gender': patient['gender'],
                'medical_conditions': json.loads(patient['medical_conditions']) if patient['medical_conditions'] else None,
                'emergency_contact': json.loads(patient['emergency_contact']) if patient['emergency_contact'] else None,
                'is_active': bool(patient['is_active']),
                'created_at': patient['created_at'].isoformat() if patient['created_at'] else None,
                'updated_at': patient['updated_at'].isoformat() if patient['updated_at'] else None,
                'device_name': patient['device_name'],
                'device_nickname': patient['device_nickname'],
                'user_role': patient['user_role']
            })

        return jsonify({
            'status': 'success',
            'count': len(result),
            'patients': result
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/patients/<patient_id>', methods=['DELETE'])
def delete_patient(patient_id):
    """
    Xóa patient vĩnh viễn (DELETE)
    Chỉ owner và caregiver có quyền xóa
    """
    try:
        user_id = request.args.get('user_id')

        if not user_id:
            return jsonify({
                'status': 'error',
                'message': 'Missing required parameter: user_id'
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get patient's device_id
        cursor.execute("""
            SELECT device_id, name FROM patients WHERE patient_id = %s
        """, (patient_id,))

        patient = cursor.fetchone()

        if not patient:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Patient not found'
            }), 404

        # Verify user có quyền (owner hoặc caregiver)
        if patient['device_id']:
            cursor.execute("""
                SELECT role FROM device_ownership
                WHERE device_id = %s AND user_id = %s
                AND role IN ('owner', 'caregiver')
            """, (patient['device_id'], user_id))

            ownership = cursor.fetchone()

            if not ownership:
                cursor.close()
                conn.close()
                return jsonify({
                    'status': 'error',
                    'message': 'User does not have permission to delete this patient'
                }), 403

        # Delete patient (CASCADE sẽ xóa health_records, alerts, thresholds)
        cursor.execute("""
            DELETE FROM patients WHERE patient_id = %s
        """, (patient_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'message': f'Patient {patient["name"]} deleted successfully'
        })

    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/generate-pairing-code', methods=['POST'])
def generate_pairing_code():
    """
    Generate new pairing code for device (called from Pi GUI)
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400
        
        device_id = data.get('device_id')
        
        if not device_id:
            return jsonify({
                'status': 'error',
                'message': 'Missing required field: device_id'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Verify device exists
        cursor.execute("SELECT * FROM devices WHERE device_id = %s", (device_id,))
        device = cursor.fetchone()
        
        if not device:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Device not found'
            }), 404
        
        # Generate 8-character pairing code
        pairing_code = secrets.token_hex(4).upper()
        
        # Create QR data with expiry (10 minutes)
        qr_data = {
            'device_id': device_id,
            'pairing_code': pairing_code,
            'timestamp': datetime.utcnow().isoformat(),
            'expires_at': (datetime.utcnow() + timedelta(minutes=10)).isoformat()
        }
        
        # Update device with new pairing code
        cursor.execute("""
            UPDATE devices
            SET pairing_code = %s,
                pairing_qr_data = %s
            WHERE device_id = %s
        """, (pairing_code, json.dumps(qr_data), device_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'status': 'success',
            'message': 'Pairing code generated successfully',
            'data': {
                'pairing_code': pairing_code,
                'qr_data': qr_data,
                'expires_in_minutes': 10
            }
        })
        
    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/devices/<device_id>/nickname', methods=['PUT'])
def update_device_nickname(device_id):
    """
    Update device nickname sau khi đã pair
    Cho phép user đổi tên device theo ý muốn
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400
        
        user_id = data.get('user_id')
        nickname = data.get('nickname')
        
        if not all([user_id, nickname]):
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields: user_id, nickname'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Verify user owns this device
        cursor.execute("""
            SELECT * FROM device_ownership
            WHERE device_id = %s AND user_id = %s
        """, (device_id, user_id))
        
        ownership = cursor.fetchone()
        
        if not ownership:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'User does not own this device'
            }), 403
        
        # Update nickname
        cursor.execute("""
            UPDATE device_ownership
            SET nickname = %s,
                last_accessed = NOW()
            WHERE device_id = %s AND user_id = %s
        """, (nickname, device_id, user_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'status': 'success',
            'message': 'Device nickname updated successfully',
            'data': {
                'device_id': device_id,
                'nickname': nickname
            }
        })
        
    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/devices/<device_id>/status', methods=['GET'])
def get_device_status(device_id):
    """
    Get device online status and health metrics
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT 
                d.device_id,
                d.device_name,
                d.is_active,
                d.last_seen,
                TIMESTAMPDIFF(SECOND, d.last_seen, NOW()) as seconds_offline,
                COUNT(hr.id) as records_24h,
                AVG(hr.data_quality) as avg_quality_24h
            FROM devices d
            LEFT JOIN health_records hr ON d.device_id = hr.device_id
                AND hr.timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            WHERE d.device_id = %s
            GROUP BY d.device_id
        """, (device_id,))
        
        device = cursor.fetchone()
        
        if not device:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Device not found'
            }), 404
        
        # Determine online status (offline if no heartbeat in 5 minutes)
        is_online = device['seconds_offline'] < 300 if device['last_seen'] else False
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'status': 'success',
            'data': {
                'device_id': device['device_id'],
                'device_name': device['device_name'],
                'is_online': is_online,
                'is_active': bool(device['is_active']),
                'last_seen': device['last_seen'].isoformat() if device['last_seen'] else None,
                'seconds_offline': device['seconds_offline'],
                'records_24h': device['records_24h'],
                'avg_data_quality': float(device['avg_quality_24h']) if device['avg_quality_24h'] else None
            }
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

if __name__ == '__main__':
    # Production: Use gunicorn instead
    # gunicorn -w 4 -b 0.0.0.0:8000 flask_api_pairing:app
    app.run(host='0.0.0.0', port=8000, debug=False)