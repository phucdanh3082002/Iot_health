-- Script sửa dữ liệu pairing để phù hợp với Android API
-- user_id trong Android app là "user_001", nhưng database hiện tại dùng "user_001_default"

USE iot_health_cloud;

-- 1. Thêm device_ownership record cho user_id = 'user_001' (Android app default)
INSERT INTO device_ownership (user_id, device_id, role, nickname, added_at)
VALUES ('user_001', 'rasp_pi_001', 'owner', 'Thiết bị chính', NOW())
ON DUPLICATE KEY UPDATE
    nickname = VALUES(nickname),
    added_at = VALUES(added_at);

-- 2. Tạo pairing code mới cho testing
UPDATE devices
SET pairing_code = 'ABC123XYZ',
    is_active = 1
WHERE device_id = 'rasp_pi_001';

-- 3. Verify dữ liệu sau khi sửa
SELECT '=== UPDATED DEVICE OWNERSHIP ===' as section;
SELECT user_id, device_id, nickname, added_at FROM device_ownership WHERE device_id = 'rasp_pi_001';

SELECT '=== UPDATED DEVICES ===' as section;
SELECT device_id, device_name, pairing_code, is_active FROM devices WHERE device_id = 'rasp_pi_001';

-- 4. Test API query với user_id = 'user_001'
SELECT '=== API TEST WITH user_id = user_001 ===' as section;
SELECT
    d.device_id,
    d.device_name,
    d.device_type,
    d.location,
    do.nickname,
    p.patient_id,
    p.name as patient_name,
    p.age,
    p.gender
FROM devices d
LEFT JOIN device_ownership do ON d.device_id = do.device_id AND do.user_id = 'user_001'
LEFT JOIN patients p ON d.device_id = p.device_id
WHERE d.pairing_code = 'ABC123XYZ';

-- 5. Test thresholds query
SELECT '=== THRESHOLDS FOR PATIENT ===' as section;
SELECT
    pt.vital_sign,
    pt.min_normal,
    pt.max_normal,
    pt.min_critical,
    pt.max_critical
FROM patient_thresholds pt
WHERE pt.patient_id = 'patient_001'
ORDER BY pt.vital_sign;