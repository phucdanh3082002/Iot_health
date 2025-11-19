#!/bin/bash
# find_fields_to_update.sh
# Script để tìm tất cả nơi cần thêm device_id sau khi migrate database

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  FINDING FIELDS THAT NEED device_id AFTER DATABASE MIGRATION  ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

cd /home/pi/Desktop/IoT_health

echo "1️⃣  Searching for Health Record Creation..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep -rn "save_health_record" src/ --include="*.py" | grep -v "def save_health_record" | grep -v "^Binary"
echo ""

echo "2️⃣  Searching for Alert Creation..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep -rn "save_alert" src/ --include="*.py" | grep -v "def save_alert" | grep -v "^Binary"
echo ""

echo "3️⃣  Searching for Sensor Calibration..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep -rn "save_sensor_calibration" . --include="*.py" | grep -v "def save_sensor_calibration" | grep -v "^Binary"
echo ""

echo "4️⃣  Checking CloudSyncManager push methods..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep -n "def push_" src/communication/cloud_sync_manager.py 2>/dev/null
echo ""

echo "5️⃣  Searching Test Files with health_data..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep -rn "health_data = {" tests/ --include="*.py" | head -10
echo ""

echo "6️⃣  Searching for alert_data dictionaries..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep -rn "alert_data = {" src/ --include="*.py" | head -10
echo ""

echo "7️⃣  Searching for calibration_data dictionaries..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep -rn "calibration_data = {" . --include="*.py" | head -10
echo ""

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  SEARCH COMPLETE                                               ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "📝 Review the files above and add device_id field where needed."
echo "💡 Tip: device_id = config['cloud']['device']['device_id']"
echo ""
echo "📄 See FIELDS_TO_UPDATE.md for detailed instructions."
