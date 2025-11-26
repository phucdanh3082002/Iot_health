#!/usr/bin/env python3
"""
Test MQTT Publishing - Kiểm tra xem có publish được lên HiveMQ Cloud không
"""

import sys
import os
import time
import yaml
from pathlib import Path
from dotenv import load_dotenv

# Add src directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env file
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded environment variables from {env_path}")
else:
    print(f"⚠️  .env file not found at {env_path}")

from src.communication.mqtt_client import IoTHealthMQTTClient
from src.communication.mqtt_payloads import VitalsPayload, AlertPayload, DeviceStatusPayload
from src.utils.logger import setup_logger


def test_mqtt_connection():
    """Test MQTT connection and publishing"""
    print("\n" + "="*70)
    print("🧪 MQTT Publishing Test - HiveMQ Cloud")
    print("="*70)
    
    # Load config
    config_path = project_root / "config" / "app_config.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Setup logger
    logger = setup_logger("mqtt_test", str(config_path), "DEBUG")
    
    # Show environment variables
    print("\n🔐 Environment Variables:")
    print(f"   MQTT_PASSWORD: {'***set***' if os.getenv('MQTT_PASSWORD') else 'NOT SET'}")
    mqtt_cfg = config.get('communication', {}).get('mqtt', {})
    print(f"   MQTT Broker: {mqtt_cfg.get('broker')}")
    print(f"   MQTT Port: {mqtt_cfg.get('port')}")
    print(f"   MQTT Username: {mqtt_cfg.get('username')}")
    print(f"   Device ID: {mqtt_cfg.get('device_id')}")
    
    # Initialize MQTT client
    print("\n1️⃣  Initializing MQTT client...")
    mqtt_client = IoTHealthMQTTClient(config=config)
    
    # Connect
    print("2️⃣  Connecting to MQTT broker...")
    if not mqtt_client.connect():
        print("❌ Failed to initiate connection")
        return False
    
    # Wait for connection
    print("   Waiting for connection callback...")
    time.sleep(3)
    
    if not mqtt_client.is_connected:
        print("❌ Not connected after 3 seconds")
        print(f"   Connection status: {mqtt_client.get_connection_status()}")
        return False
    
    print("✅ Connected successfully!")
    
    # Test 1: Publish Device Status
    print("\n3️⃣  Test 1: Publishing device status...")
    status_payload = DeviceStatusPayload(
        timestamp=time.time(),
        device_id=mqtt_client.device_id,
        online=True,
        battery={'level': 95, 'charging': False},
        sensors={'max30102': 'ready', 'mlx90614': 'ready', 'hx710b': 'ready'},
        actuators={'pump': 'idle', 'valve': 'closed'},
        system={'uptime': 300, 'memory_usage': 45.2},
        network={'wifi_signal': -55, 'mqtt_connected': True}
    )
    
    if mqtt_client.publish_status(status_payload):
        print("   ✅ Status published successfully")
    else:
        print("   ❌ Status publish failed")
    
    time.sleep(1)
    
    # Test 2: Publish Vitals (simulated temperature measurement)
    print("\n4️⃣  Test 2: Publishing vitals (temperature)...")
    vitals_payload = VitalsPayload.from_sensor_data(
        device_id=mqtt_client.device_id,
        patient_id=mqtt_client.patient_id,
        sensor_data={
            'temperature': 36.5,
            'ambient_temperature': 25.0,
            'temperature_metadata': {
                'read_count': 10,
                'std_dev': 0.2
            }
        },
        session_id=f"test_session_{int(time.time())}",
        measurement_sequence=1,
        device_context={'test_mode': True}
    )
    
    if mqtt_client.publish_vitals(vitals_payload):
        print("   ✅ Vitals published successfully")
    else:
        print("   ❌ Vitals publish failed")
    
    time.sleep(1)
    
    # Test 3: Publish Alert
    print("\n5️⃣  Test 3: Publishing alert...")
    alert_payload = AlertPayload(
        timestamp=time.time(),
        device_id=mqtt_client.device_id,
        patient_id=mqtt_client.patient_id,
        alert_type='test_alert',
        severity='info',
        priority=3,
        current_measurement={'temperature': 36.5, 'unit': 'celsius'},
        thresholds={'min': 36.0, 'max': 37.5}
    )
    
    if mqtt_client.publish_alert(alert_payload):
        print("   ✅ Alert published successfully")
    else:
        print("   ❌ Alert publish failed")
    
    time.sleep(2)
    
    # Show statistics
    print("\n6️⃣  MQTT Statistics:")
    stats = mqtt_client.get_connection_status()
    print(f"   Messages sent: {stats['stats']['messages_sent']}")
    print(f"   Messages received: {stats['stats']['messages_received']}")
    print(f"   Connection attempts: {stats['stats']['connection_attempts']}")
    
    # Disconnect
    print("\n7️⃣  Disconnecting...")
    mqtt_client.disconnect()
    
    print("\n" + "="*70)
    print("✅ MQTT Test completed successfully!")
    print("="*70)
    print("\n💡 Next steps:")
    print("   1. Open MQTT Explorer (https://mqtt-explorer.com/)")
    print("   2. Connect to: c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud:8883")
    print("   3. Use TLS/SSL, username: rpi_bp_001, password from .env")
    print("   4. Subscribe to: iot_health/device/rpi_bp_001/#")
    print("   5. Run this test again and watch messages appear!\n")
    
    return True


if __name__ == "__main__":
    try:
        success = test_mqtt_connection()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
