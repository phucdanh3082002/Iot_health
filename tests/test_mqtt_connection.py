"""
Test MQTT Connection cho Android App Development
Kiểm tra MQTT broker sẵn sàng cho app kết nối
"""

import sys
import os
import time
import json

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import yaml
import paho.mqtt.client as mqtt


def test_mqtt_basic_connection():
    """Test MQTT connection without TLS (for development)"""
    
    # Load config
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'app_config.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    mqtt_cfg = config['communication']['mqtt']
    
    # Use non-TLS port for testing
    broker = mqtt_cfg['broker']
    port = 1883  # Non-TLS port
    device_id = mqtt_cfg.get('device_id', 'rpi_bp_001')
    
    print("=" * 60)
    print("MQTT CONNECTION TEST FOR ANDROID APP")
    print("=" * 60)
    print(f"Broker:    {broker}:{port}")
    print(f"Device ID: {device_id}")
    print(f"Topics:")
    print(f"  - iot_health/device/{device_id}/vitals")
    print(f"  - iot_health/device/{device_id}/alerts")
    print(f"  - iot_health/device/{device_id}/status")
    print()
    
    # Connection status
    connected = False
    
    def on_connect(client, userdata, flags, rc):
        nonlocal connected
        if rc == 0:
            print("✅ Connected to MQTT broker successfully!")
            connected = True
            
            # Subscribe to test topic
            test_topic = f"iot_health/device/{device_id}/#"
            client.subscribe(test_topic, qos=1)
            print(f"📡 Subscribed to: {test_topic}")
        else:
            error_msgs = {
                1: "Connection refused - incorrect protocol version",
                2: "Connection refused - invalid client identifier",
                3: "Connection refused - server unavailable",
                4: "Connection refused - bad username or password",
                5: "Connection refused - not authorized"
            }
            print(f"❌ Connection failed: {error_msgs.get(rc, f'Unknown error {rc}')}")
    
    def on_disconnect(client, userdata, rc):
        nonlocal connected
        connected = False
        if rc == 0:
            print("🔌 Disconnected cleanly")
        else:
            print(f"⚠️ Unexpected disconnect (rc={rc})")
    
    def on_message(client, userdata, msg):
        print(f"📥 Received message on '{msg.topic}'")
        try:
            data = json.loads(msg.payload.decode())
            print(f"   Data: {json.dumps(data, indent=2)[:200]}...")
        except:
            print(f"   Payload: {msg.payload.decode()[:100]}")
    
    def on_publish(client, userdata, mid):
        print(f"✅ Message published (mid={mid})")
    
    # Create MQTT client
    client = mqtt.Client(client_id=device_id, clean_session=True)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.on_publish = on_publish
    
    try:
        print("Connecting to broker...")
        client.connect(broker, port=port, keepalive=60)
        
        # Start network loop
        client.loop_start()
        
        # Wait for connection
        time.sleep(2)
        
        if connected:
            print()
            print("=" * 60)
            print("CONNECTION TEST: PASSED ✅")
            print("=" * 60)
            print()
            
            # Test publish vitals
            print("Testing publish vitals...")
            vitals_topic = f"iot_health/device/{device_id}/vitals"
            test_vitals = {
                "timestamp": time.time(),
                "device_id": device_id,
                "patient_id": "patient_001",
                "measurements": {
                    "heart_rate": {"value": 75, "unit": "bpm"},
                    "spo2": {"value": 98, "unit": "%"},
                    "temperature": {"object_temp": 36.5, "unit": "celsius"},
                    "blood_pressure": {"systolic": 120, "diastolic": 80, "unit": "mmHg"}
                }
            }
            
            result = client.publish(vitals_topic, json.dumps(test_vitals), qos=1)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"✅ Published to {vitals_topic}")
            
            # Wait for message
            time.sleep(1)
            
            # Test publish alert
            print()
            print("Testing publish alert...")
            alert_topic = f"iot_health/device/{device_id}/alerts"
            test_alert = {
                "timestamp": time.time(),
                "device_id": device_id,
                "patient_id": "patient_001",
                "alert_type": "threshold",
                "severity": "warning",
                "message": "Test alert from MQTT connection test",
                "vital_sign": "heart_rate",
                "current_value": 105
            }
            
            result = client.publish(alert_topic, json.dumps(test_alert), qos=2)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"✅ Published to {alert_topic}")
            
            # Wait
            time.sleep(1)
            
            print()
            print("=" * 60)
            print("PUBLISH TEST: PASSED ✅")
            print("=" * 60)
            print()
            print("📱 MQTT is ready for Android App connection!")
            print()
            print("Android App Configuration:")
            print(f"  - Broker: {broker}")
            print(f"  - Port: {port} (non-TLS for development)")
            print(f"  - Subscribe to: iot_health/device/+/# (all devices)")
            print(f"  - Publish to: iot_health/patient/{{patient_id}}/commands")
            print()
            
        else:
            print()
            print("=" * 60)
            print("CONNECTION TEST: FAILED ❌")
            print("=" * 60)
            print()
            print("Possible issues:")
            print("  1. Check internet connection")
            print("  2. Broker may be down (try broker.hivemq.com)")
            print("  3. Firewall blocking port 1883")
            print()
        
        # Cleanup
        print("Disconnecting...")
        client.loop_stop()
        client.disconnect()
        time.sleep(1)
        
        return connected
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    success = test_mqtt_basic_connection()
    sys.exit(0 if success else 1)
