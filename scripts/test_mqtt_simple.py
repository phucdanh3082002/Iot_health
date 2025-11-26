#!/usr/bin/env python3
"""
Simple MQTT Test - Direct paho-mqtt without custom wrapper
"""

import paho.mqtt.client as mqtt
import ssl
import time
import os
import json
from dotenv import load_dotenv
from pathlib import Path

# Load environment
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# MQTT Config
BROKER = "c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud"
PORT = 8883
USERNAME = "rpi_bp_001"
PASSWORD = os.getenv("MQTT_PASSWORD")
CLIENT_ID = "rpi_bp_001_test"

print("="*70)
print("🧪 Simple MQTT Test (Direct Paho)")
print("="*70)
print(f"Broker: {BROKER}:{PORT}")
print(f"Username: {USERNAME}")
print(f"Password: {'***' + PASSWORD[-4:] if PASSWORD else 'NOT SET'}")
print(f"Client ID: {CLIENT_ID}")
print("="*70)

if not PASSWORD:
    print("❌ MQTT_PASSWORD not set in environment!")
    exit(1)

# Connection callback
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Connected successfully!")
        print(f"   flags: {flags}")
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
    if rc == 0:
        print("🔌 Disconnected cleanly")
    else:
        print(f"⚠️  Unexpected disconnect (rc={rc})")

def on_publish(client, userdata, mid):
    print(f"   ✅ Message {mid} published")

def on_log(client, userdata, level, buf):
    print(f"   [LOG] {buf}")

# Create client
client = mqtt.Client(client_id=CLIENT_ID, clean_session=True)
client.username_pw_set(USERNAME, PASSWORD)

# Setup callbacks
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_publish = on_publish
# client.on_log = on_log  # Uncomment for detailed logs

# Setup TLS
client.tls_set(
    ca_certs=None,
    certfile=None,
    keyfile=None,
    cert_reqs=ssl.CERT_REQUIRED,
    tls_version=ssl.PROTOCOL_TLS,
    ciphers=None
)
client.tls_insecure_set(False)

print("\n📡 Connecting...")
try:
    client.connect(BROKER, PORT, keepalive=60)
    client.loop_start()
    
    # Wait for connection
    time.sleep(3)
    
    if client.is_connected():
        print("\n📤 Publishing test messages...")
        
        # Publish status
        topic = f"iot_health/device/{USERNAME}/status"
        payload = json.dumps({
            "timestamp": time.time(),
            "device_id": USERNAME,
            "online": True,
            "test": True
        })
        result = client.publish(topic, payload, qos=1)
        print(f"1. Status -> {topic}")
        
        time.sleep(1)
        
        # Publish vitals
        topic = f"iot_health/device/{USERNAME}/vitals"
        payload = json.dumps({
            "timestamp": time.time(),
            "device_id": USERNAME,
            "patient_id": "patient_001",
            "measurements": {
                "temperature": {"value": 36.5, "unit": "celsius"}
            },
            "test": True
        })
        result = client.publish(topic, payload, qos=1)
        print(f"2. Vitals -> {topic}")
        
        time.sleep(2)
        
        print("\n✅ All messages published!")
        print("\n💡 Check messages at:")
        print(f"   Topic: iot_health/device/{USERNAME}/#")
        print("   Use MQTT Explorer or HiveMQ Cloud dashboard")
        
    else:
        print("\n❌ Not connected after 3 seconds")
    
    client.loop_stop()
    client.disconnect()
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*70)
