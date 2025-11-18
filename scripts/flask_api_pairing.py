#!/usr/bin/env python3
"""
Flask API Implementation cho IoT Health Monitor
Triển khai trên AWS EC2 với endpoint /api/pair-device theo specification
"""

from flask import Flask, request, jsonify
import mysql.connector
import os
from datetime import datetime
import json

app = Flask(__name__)

# Database configuration
DB_CONFIG = {
    'host': 'database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com',
    'user': 'pi_sync',
    'password': os.getenv('MYSQL_PASSWORD', 'your_mysql_password'),
    'database': 'iot_health_cloud',
    'port': 3306
}

def get_db_connection():
    """Get database connection"""
    return mysql.connector.connect(**DB_CONFIG)

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({
            'status': 'ok',
            'database': 'connected',
            'timestamp': datetime.utcnow().isoformat(),
            'version': '1.0.0'
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
                'message': 'Invalid pairing code or code expired'
            }), 400

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
            INSERT INTO device_ownership (user_id, device_id, role, nickname, added_at)
            VALUES (%s, %s, 'owner', %s, NOW())
            ON DUPLICATE KEY UPDATE
                nickname = VALUES(nickname),
                added_at = VALUES(added_at)
        """, (user_id, device_id, nickname))

        # 5. Update device paired info
        cursor.execute("""
            UPDATE devices
            SET paired_at = NOW(), paired_by = %s
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
                do.nickname,
                d.last_seen,
                d.is_active,
                p.patient_id,
                p.name as patient_name,
                p.age,
                p.gender
            FROM devices d
            JOIN device_ownership do ON d.device_id = do.device_id
            LEFT JOIN patients p ON d.device_id = p.device_id
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

@app.route('/api/patient', methods=['POST'])
def create_or_update_patient():
    """
    Tạo hoặc cập nhật thông tin bệnh nhân từ Android app
    Called sau khi pairing để thêm thông tin người dùng
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400

        device_id = data.get('device_id')
        user_id = data.get('user_id')
        name = data.get('name')
        age = data.get('age')
        gender = data.get('gender')
        medical_conditions = data.get('medical_conditions')  # JSON
        emergency_contact = data.get('emergency_contact')    # JSON

        if not all([device_id, user_id, name]):
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields: device_id, user_id, name'
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

        # Check if patient already exists for this device
        cursor.execute("""
            SELECT patient_id FROM patients WHERE device_id = %s
        """, (device_id,))

        existing_patient = cursor.fetchone()

        # Convert JSON fields to string if provided
        medical_conditions_json = json.dumps(medical_conditions) if medical_conditions else None
        emergency_contact_json = json.dumps(emergency_contact) if emergency_contact else None

        if existing_patient:
            # Update existing patient
            patient_id = existing_patient['patient_id']
            cursor.execute("""
                UPDATE patients
                SET name = %s,
                    age = %s,
                    gender = %s,
                    medical_conditions = %s,
                    emergency_contact = %s,
                    updated_at = NOW()
                WHERE patient_id = %s
            """, (name, age, gender, medical_conditions_json, emergency_contact_json, patient_id))
        else:
            # Create new patient
            patient_id = f'patient_{device_id}_{user_id}'
            cursor.execute("""
                INSERT INTO patients (patient_id, device_id, name, age, gender, medical_conditions, emergency_contact)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (patient_id, device_id, name, age, gender, medical_conditions_json, emergency_contact_json))

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

        # Get updated patient info
        cursor.execute("""
            SELECT patient_id, name, age, gender, medical_conditions, emergency_contact
            FROM patients
            WHERE patient_id = %s
        """, (patient_id,))

        patient = cursor.fetchone()

        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'message': 'Patient information saved successfully',
            'data': {
                'patient_id': patient['patient_id'],
                'name': patient['name'],
                'age': patient['age'],
                'gender': patient['gender'],
                'medical_conditions': json.loads(patient['medical_conditions']) if patient['medical_conditions'] else None,
                'emergency_contact': json.loads(patient['emergency_contact']) if patient['emergency_contact'] else None,
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)