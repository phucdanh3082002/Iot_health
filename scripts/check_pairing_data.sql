-- Script kiểm tra và bổ sung dữ liệu cho QR Pairing
-- Chạy sau khi import database dump

USE iot_health_cloud;

-- 1. Kiểm tra dữ liệu hiện tại
SELECT '=== DEVICES TABLE ===' as section;
SELECT device_id, device_name, pairing_code, is_active, paired_at, paired_by FROM devices;

SELECT '=== DEVICE OWNERSHIP TABLE ===' as section;
SELECT user_id, device_id, nickname, added_at FROM device_ownership;

SELECT '=== PATIENTS TABLE ===' as section;
SELECT patient_id, device_id, name, age, gender FROM patients;

SELECT '=== PATIENT THRESHOLDS TABLE ===' as section;
SELECT patient_id, vital_sign, min_normal, max_normal, min_critical, max_critical FROM patient_thresholds;

-- 2. Thêm dữ liệu mặc định cho patient_thresholds (thiếu trong dump)
INSERT IGNORE INTO patient_thresholds (patient_id, vital_sign, min_normal, max_normal, min_critical, max_critical, is_active) VALUES
('patient_001', 'heart_rate', 60.00, 100.00, 40.00, 120.00, 1),
('patient_001', 'spo2', 95.00, 100.00, 90.00, 100.00, 1),
('patient_001', 'temperature', 36.10, 37.20, 35.00, 39.00, 1),
('patient_001', 'systolic_bp', 90.00, 120.00, 70.00, 180.00, 1),
('patient_001', 'diastolic_bp', 60.00, 80.00, 40.00, 110.00, 1);

-- 3. Kiểm tra lại sau khi thêm
SELECT '=== PATIENT THRESHOLDS AFTER INSERT ===' as section;
SELECT patient_id, vital_sign, min_normal, max_normal, min_critical, max_critical FROM patient_thresholds WHERE patient_id = 'patient_001';

-- 4. Tạo pairing code mới cho testing (nếu cần)
-- UPDATE devices SET pairing_code = 'TEST123', is_active = 1 WHERE device_id = 'rasp_pi_001';

-- 5. Verify MQTT topics structure (sẽ được trả về từ API)
SELECT '=== MQTT TOPICS STRUCTURE (HARDCODED IN API) ===' as section;
SELECT
    'iot_health/device/{device_id}/vitals' as vitals_topic,
    'iot_health/device/{device_id}/alerts' as alerts_topic,
    'iot_health/device/{device_id}/status' as status_topic,
    'iot_health/patient/{patient_id}/commands' as commands_topic;

-- 6. Kiểm tra foreign key constraints
SELECT '=== FOREIGN KEY CHECK ===' as section;
SELECT COUNT(*) as total_devices FROM devices;
SELECT COUNT(*) as total_patients FROM patients;
SELECT COUNT(*) as total_ownership FROM device_ownership;

-- 7. Test query cho API /api/pair-device
SELECT '=== API PAIR-DEVICE TEST QUERY ===' as section;
SELECT
    d.device_id,
    d.device_name,
    d.device_type,
    d.location,
    do.nickname,
    p.patient_id,
    p.name as patient_name,
    p.age,
    p.gender,
    pt.vital_sign,
    pt.min_normal,
    pt.max_normal,
    pt.min_critical,
    pt.max_critical
FROM devices d
LEFT JOIN device_ownership do ON d.device_id = do.device_id AND do.user_id = 'user_001'
LEFT JOIN patients p ON d.device_id = p.device_id
LEFT JOIN patient_thresholds pt ON p.patient_id = pt.patient_id
WHERE d.pairing_code = 'A7X9K2'  -- Test với pairing code hiện tại
ORDER BY pt.vital_sign;

-- 8. Kiểm tra dữ liệu sau khi pairing thành công
SELECT '=== POST-PAIRING VERIFICATION ===' as section;
SELECT
    'Device Info:' as section,
    d.device_id, d.device_name, d.device_type, d.location,
    'Patient Info:' as section,
    p.patient_id, p.name, p.age, p.gender,
    'Ownership:' as section,
    do.user_id, do.nickname, do.added_at,
    'Thresholds Count:' as section,
    COUNT(pt.id) as thresholds_count
FROM devices d
LEFT JOIN patients p ON d.device_id = p.device_id
LEFT JOIN device_ownership do ON d.device_id = do.device_id
LEFT JOIN patient_thresholds pt ON p.patient_id = pt.patient_id
WHERE d.device_id = 'rasp_pi_001'
GROUP BY d.device_id, d.device_name, d.device_type, d.location,
         p.patient_id, p.name, p.age, p.gender,
         do.user_id, do.nickname, do.added_at;