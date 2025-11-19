#!/usr/bin/env python3
"""
IoT Health Monitor - Flask REST API (v2.0.0)
Compatible with Database Schema v2.0.0
Deployed on: AWS EC2 (Ubuntu)
Database: AWS RDS MySQL
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import pymysql
from datetime import datetime, timedelta
import json
import os
from dotenv import load_dotenv
import hashlib
import secrets

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for web dashboard

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'admin'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME', 'iot_health_cloud'),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor,
    'autocommit': False
}

# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db_connection():
    """Create database connection"""
    try:
        connection = pymysql.connect(**DB_CONFIG)
        return connection
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def execute_query(query, params=None, fetch_one=False, fetch_all=False, commit=False):
    """Execute database query with error handling"""
    connection = get_db_connection()
    if not connection:
        return None
    
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params or ())
            
            if commit:
                connection.commit()
                return cursor.lastrowid
            elif fetch_one:
                return cursor.fetchone()
            elif fetch_all:
                return cursor.fetchall()
            else:
                return True
    except Exception as e:
        print(f"Query execution error: {e}")
        connection.rollback()
        return None
    finally:
        connection.close()

# ============================================================
# DEVICE ENDPOINTS
# ============================================================

@app.route('/api/v2/devices', methods=['GET'])
def get_devices():
    """Get all devices or filter by parameters"""
    try:
        is_active = request.args.get('is_active')
        device_type = request.args.get('device_type')
        
        query = "SELECT * FROM devices WHERE 1=1"
        params = []
        
        if is_active is not None:
            query += " AND is_active = %s"
            params.append(int(is_active))
        
        if device_type:
            query += " AND device_type = %s"
            params.append(device_type)
        
        query += " ORDER BY created_at DESC"
        
        devices = execute_query(query, tuple(params), fetch_all=True)
        
        return jsonify({
            'success': True,
            'count': len(devices) if devices else 0,
            'devices': devices or []
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v2/devices/<device_id>', methods=['GET'])
def get_device(device_id):
    """Get specific device details"""
    try:
        device = execute_query(
            "SELECT * FROM devices WHERE device_id = %s",
            (device_id,),
            fetch_one=True
        )
        
        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404
        
        return jsonify({
            'success': True,
            'device': device
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v2/devices/<device_id>/heartbeat', methods=['POST'])
def device_heartbeat(device_id):
    """Update device heartbeat (last_seen)"""
    try:
        data = request.get_json()
        
        query = """
            UPDATE devices 
            SET last_seen = NOW(),
                ip_address = %s
            WHERE device_id = %s
        """
        
        result = execute_query(
            query,
            (data.get('ip_address'), device_id),
            commit=True
        )
        
        if result:
            return jsonify({'success': True, 'message': 'Heartbeat updated'}), 200
        else:
            return jsonify({'success': False, 'error': 'Device not found'}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v2/devices/<device_id>/pairing', methods=['POST'])
def generate_pairing_code(device_id):
    """Generate pairing code for QR scanning"""
    try:
        # Generate 8-character pairing code
        pairing_code = secrets.token_hex(4).upper()
        
        # Create QR data
        qr_data = {
            'device_id': device_id,
            'pairing_code': pairing_code,
            'timestamp': datetime.utcnow().isoformat(),
            'expires_at': (datetime.utcnow() + timedelta(minutes=10)).isoformat()
        }
        
        query = """
            UPDATE devices
            SET pairing_code = %s,
                pairing_qr_data = %s
            WHERE device_id = %s
        """
        
        result = execute_query(
            query,
            (pairing_code, json.dumps(qr_data), device_id),
            commit=True
        )
        
        if result:
            return jsonify({
                'success': True,
                'pairing_code': pairing_code,
                'qr_data': qr_data
            }), 200
        else:
            return jsonify({'success': False, 'error': 'Device not found'}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v2/devices/verify-pairing', methods=['POST'])
def verify_pairing():
    """Verify pairing code from Android app"""
    try:
        data = request.get_json()
        pairing_code = data.get('pairing_code')
        user_id = data.get('user_id')
        
        if not pairing_code or not user_id:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Find device with pairing code
        device = execute_query(
            "SELECT * FROM devices WHERE pairing_code = %s",
            (pairing_code,),
            fetch_one=True
        )
        
        if not device:
            return jsonify({'success': False, 'error': 'Invalid pairing code'}), 404
        
        # Check if code expired (10 minutes)
        qr_data = json.loads(device['pairing_qr_data'])
        expires_at = datetime.fromisoformat(qr_data['expires_at'])
        
        if datetime.utcnow() > expires_at:
            return jsonify({'success': False, 'error': 'Pairing code expired'}), 400
        
        # Create device ownership
        ownership_query = """
            INSERT INTO device_ownership (user_id, device_id, role, added_at)
            VALUES (%s, %s, 'owner', NOW())
            ON DUPLICATE KEY UPDATE last_accessed = NOW()
        """
        
        execute_query(ownership_query, (user_id, device['device_id']), commit=True)
        
        # Update device paired status
        update_query = """
            UPDATE devices
            SET paired_by = %s,
                paired_at = NOW(),
                pairing_code = NULL
            WHERE device_id = %s
        """
        
        execute_query(update_query, (user_id, device['device_id']), commit=True)
        
        return jsonify({
            'success': True,
            'device': {
                'device_id': device['device_id'],
                'device_name': device['device_name'],
                'device_type': device['device_type']
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# PATIENT ENDPOINTS
# ============================================================

@app.route('/api/v2/patients', methods=['GET'])
def get_patients():
    """Get all patients or filter by device"""
    try:
        device_id = request.args.get('device_id')
        is_active = request.args.get('is_active', '1')
        
        query = "SELECT * FROM patients WHERE is_active = %s"
        params = [int(is_active)]
        
        if device_id:
            query += " AND device_id = %s"
            params.append(device_id)
        
        query += " ORDER BY created_at DESC"
        
        patients = execute_query(query, tuple(params), fetch_all=True)
        
        return jsonify({
            'success': True,
            'count': len(patients) if patients else 0,
            'patients': patients or []
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v2/patients/<patient_id>', methods=['GET'])
def get_patient(patient_id):
    """Get specific patient details"""
    try:
        patient = execute_query(
            "SELECT * FROM patients WHERE patient_id = %s",
            (patient_id,),
            fetch_one=True
        )
        
        if not patient:
            return jsonify({'success': False, 'error': 'Patient not found'}), 404
        
        return jsonify({
            'success': True,
            'patient': patient
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v2/patients/<patient_id>/thresholds', methods=['GET'])
def get_patient_thresholds(patient_id):
    """Get patient-specific thresholds"""
    try:
        thresholds = execute_query(
            "SELECT * FROM patient_thresholds WHERE patient_id = %s",
            (patient_id,),
            fetch_all=True
        )
        
        # Convert to dict format
        threshold_dict = {}
        if thresholds:
            for t in thresholds:
                threshold_dict[t['vital_sign']] = {
                    'min_normal': t['min_normal'],
                    'max_normal': t['max_normal'],
                    'min_critical': t['min_critical'],
                    'max_critical': t['max_critical']
                }
        
        return jsonify({
            'success': True,
            'patient_id': patient_id,
            'thresholds': threshold_dict
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# HEALTH RECORDS ENDPOINTS
# ============================================================

@app.route('/api/v2/health-records', methods=['GET'])
def get_health_records():
    """Get health records with filters"""
    try:
        patient_id = request.args.get('patient_id')
        device_id = request.args.get('device_id')
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')
        limit = int(request.args.get('limit', 100))
        
        query = "SELECT * FROM health_records WHERE 1=1"
        params = []
        
        if patient_id:
            query += " AND patient_id = %s"
            params.append(patient_id)
        
        if device_id:
            query += " AND device_id = %s"
            params.append(device_id)
        
        if start_time:
            query += " AND timestamp >= %s"
            params.append(start_time)
        
        if end_time:
            query += " AND timestamp <= %s"
            params.append(end_time)
        
        query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)
        
        records = execute_query(query, tuple(params), fetch_all=True)
        
        return jsonify({
            'success': True,
            'count': len(records) if records else 0,
            'records': records or []
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v2/health-records/latest', methods=['GET'])
def get_latest_vitals():
    """Get latest vitals for patient"""
    try:
        patient_id = request.args.get('patient_id')
        
        if not patient_id:
            return jsonify({'success': False, 'error': 'patient_id required'}), 400
        
        # Use view if available, otherwise query directly
        record = execute_query(
            """
            SELECT * FROM health_records
            WHERE patient_id = %s
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (patient_id,),
            fetch_one=True
        )
        
        if not record:
            return jsonify({'success': False, 'error': 'No records found'}), 404
        
        return jsonify({
            'success': True,
            'record': record
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v2/health-records/statistics', methods=['GET'])
def get_health_statistics():
    """Get health statistics for patient"""
    try:
        patient_id = request.args.get('patient_id')
        period = request.args.get('period', '24h')  # 24h, 7d, 30d
        
        if not patient_id:
            return jsonify({'success': False, 'error': 'patient_id required'}), 400
        
        # Calculate time range
        if period == '24h':
            time_delta = "INTERVAL 24 HOUR"
        elif period == '7d':
            time_delta = "INTERVAL 7 DAY"
        elif period == '30d':
            time_delta = "INTERVAL 30 DAY"
        else:
            time_delta = "INTERVAL 24 HOUR"
        
        query = f"""
            SELECT
                COUNT(*) as record_count,
                AVG(heart_rate) as avg_heart_rate,
                MIN(heart_rate) as min_heart_rate,
                MAX(heart_rate) as max_heart_rate,
                AVG(spo2) as avg_spo2,
                MIN(spo2) as min_spo2,
                MAX(spo2) as max_spo2,
                AVG(temperature) as avg_temperature,
                AVG(systolic_bp) as avg_systolic_bp,
                AVG(diastolic_bp) as avg_diastolic_bp,
                AVG(data_quality) as avg_data_quality
            FROM health_records
            WHERE patient_id = %s
            AND timestamp >= DATE_SUB(NOW(), {time_delta})
        """
        
        stats = execute_query(query, (patient_id,), fetch_one=True)
        
        return jsonify({
            'success': True,
            'patient_id': patient_id,
            'period': period,
            'statistics': stats or {}
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# ALERTS ENDPOINTS
# ============================================================

@app.route('/api/v2/alerts', methods=['GET'])
def get_alerts():
    """Get alerts with filters"""
    try:
        patient_id = request.args.get('patient_id')
        device_id = request.args.get('device_id')
        severity = request.args.get('severity')
        resolved = request.args.get('resolved')
        limit = int(request.args.get('limit', 50))
        
        query = "SELECT * FROM alerts WHERE 1=1"
        params = []
        
        if patient_id:
            query += " AND patient_id = %s"
            params.append(patient_id)
        
        if device_id:
            query += " AND device_id = %s"
            params.append(device_id)
        
        if severity:
            query += " AND severity = %s"
            params.append(severity)
        
        if resolved is not None:
            query += " AND resolved = %s"
            params.append(int(resolved))
        
        query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)
        
        alerts = execute_query(query, tuple(params), fetch_all=True)
        
        return jsonify({
            'success': True,
            'count': len(alerts) if alerts else 0,
            'alerts': alerts or []
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v2/alerts/<int:alert_id>/acknowledge', methods=['POST'])
def acknowledge_alert(alert_id):
    """Acknowledge an alert"""
    try:
        data = request.get_json()
        acknowledged_by = data.get('acknowledged_by', 'system')
        
        query = """
            UPDATE alerts
            SET acknowledged = TRUE,
                acknowledged_at = NOW(),
                acknowledged_by = %s
            WHERE id = %s
        """
        
        result = execute_query(query, (acknowledged_by, alert_id), commit=True)
        
        if result:
            return jsonify({'success': True, 'message': 'Alert acknowledged'}), 200
        else:
            return jsonify({'success': False, 'error': 'Alert not found'}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v2/alerts/<int:alert_id>/resolve', methods=['POST'])
def resolve_alert(alert_id):
    """Resolve an alert"""
    try:
        query = """
            UPDATE alerts
            SET resolved = TRUE,
                resolved_at = NOW()
            WHERE id = %s
        """
        
        result = execute_query(query, (alert_id,), commit=True)
        
        if result:
            return jsonify({'success': True, 'message': 'Alert resolved'}), 200
        else:
            return jsonify({'success': False, 'error': 'Alert not found'}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# SYNC QUEUE ENDPOINTS
# ============================================================

@app.route('/api/v2/sync-queue', methods=['GET'])
def get_sync_queue():
    """Get sync queue status"""
    try:
        device_id = request.args.get('device_id')
        sync_status = request.args.get('sync_status', 'pending')
        
        query = """
            SELECT * FROM sync_queue
            WHERE device_id = %s AND sync_status = %s
            ORDER BY priority DESC, created_at ASC
            LIMIT 100
        """
        
        queue_items = execute_query(query, (device_id, sync_status), fetch_all=True)
        
        return jsonify({
            'success': True,
            'count': len(queue_items) if queue_items else 0,
            'queue': queue_items or []
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# SENSOR CALIBRATION ENDPOINTS
# ============================================================

@app.route('/api/v2/calibrations', methods=['GET'])
def get_calibrations():
    """Get sensor calibrations"""
    try:
        device_id = request.args.get('device_id')
        sensor_name = request.args.get('sensor_name')
        is_active = request.args.get('is_active', '1')
        
        query = "SELECT * FROM sensor_calibrations WHERE is_active = %s"
        params = [int(is_active)]
        
        if device_id:
            query += " AND device_id = %s"
            params.append(device_id)
        
        if sensor_name:
            query += " AND sensor_name = %s"
            params.append(sensor_name)
        
        query += " ORDER BY calibrated_at DESC"
        
        calibrations = execute_query(query, tuple(params), fetch_all=True)
        
        return jsonify({
            'success': True,
            'count': len(calibrations) if calibrations else 0,
            'calibrations': calibrations or []
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# ANALYTICS & VIEWS ENDPOINTS
# ============================================================

@app.route('/api/v2/analytics/device-health', methods=['GET'])
def get_device_health():
    """Get device health status from view"""
    try:
        devices = execute_query(
            "SELECT * FROM v_device_health ORDER BY last_seen DESC",
            fetch_all=True
        )
        
        return jsonify({
            'success': True,
            'count': len(devices) if devices else 0,
            'devices': devices or []
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v2/analytics/sync-performance', methods=['GET'])
def get_sync_performance():
    """Get sync performance metrics"""
    try:
        device_id = request.args.get('device_id')
        
        query = "SELECT * FROM v_sync_performance"
        params = None
        
        if device_id:
            query += " WHERE device_id = %s"
            params = (device_id,)
        
        metrics = execute_query(query, params, fetch_all=True)
        
        return jsonify({
            'success': True,
            'metrics': metrics or []
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# HEALTH CHECK & INFO
# ============================================================

@app.route('/api/v2/health', methods=['GET'])
def health_check():
    """API health check"""
    try:
        # Test database connection
        result = execute_query("SELECT 1 as test", fetch_one=True)
        db_status = 'connected' if result else 'disconnected'
        
        return jsonify({
            'success': True,
            'api_version': '2.0.0',
            'database_status': db_status,
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'api_version': '2.0.0',
            'database_status': 'error',
            'error': str(e)
        }), 500

@app.route('/api/v2/info', methods=['GET'])
def api_info():
    """API information and endpoints"""
    return jsonify({
        'api_version': '2.0.0',
        'database_schema_version': '2.0.0',
        'endpoints': {
            'devices': '/api/v2/devices',
            'patients': '/api/v2/patients',
            'health_records': '/api/v2/health-records',
            'alerts': '/api/v2/alerts',
            'calibrations': '/api/v2/calibrations',
            'analytics': '/api/v2/analytics/*',
            'health': '/api/v2/health'
        }
    }), 200

# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    # Development server
    app.run(host='0.0.0.0', port=5000, debug=False)
