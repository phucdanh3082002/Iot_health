#!/usr/bin/env python3
"""
MQTT Subscriber - Monitor real-time messages từ Pi device
"""

import paho.mqtt.client as mqtt
import ssl
import time
import os
import json
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime

# Load environment
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# MQTT Config
BROKER = "c8c0b20138314154b4f21f4c7d1e19a5.s1.eu.hivemq.cloud"
PORT = 8883
USERNAME = "rpi_bp_001"
PASSWORD = os.getenv("MQTT_PASSWORD")
CLIENT_ID = "rpi_bp_001_monitor"

print("="*70)
print("📡 MQTT Monitor - Real-time Message Viewer")
print("="*70)
print(f"Broker: {BROKER}:{PORT}")
print(f"Subscribing to: iot_health/device/rpi_bp_001/#")
print("="*70)
print("Press Ctrl+C to stop\n")

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Connected to broker")
        # Subscribe to all device topics
        client.subscribe("iot_health/device/rpi_bp_001/#", qos=1)
        client.subscribe("iot_health/patient/patient_001/#", qos=1)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 📡 Subscribed to topics")
    else:
        print(f"❌ Connection failed (rc={rc})")

def on_message(client, userdata, msg):
    timestamp = datetime.now().strftime('%H:%M:%S')
    topic = msg.topic
    
    try:
        payload = json.loads(msg.payload.decode())
        
        # Format output based on topic
        if '/vitals' in topic:
            print(f"\n[{timestamp}] 📊 VITALS")
            if 'measurements' in payload:
                for key, value in payload['measurements'].items():
                    if isinstance(value, dict) and 'value' in value:
                        print(f"   {key}: {value['value']} {value.get('unit', '')}")
        
        elif '/alerts' in topic:
            severity_emoji = {'info': 'ℹ️', 'warning': '⚠️', 'critical': '🚨'}
            emoji = severity_emoji.get(payload.get('severity', 'info'), '📢')
            print(f"\n[{timestamp}] {emoji} ALERT")
            print(f"   Type: {payload.get('alert_type')}")
            print(f"   Severity: {payload.get('severity')}")
            if 'current_measurement' in payload:
                print(f"   Current: {payload['current_measurement']}")
        
        elif '/status' in topic:
            status = '🟢' if payload.get('online') else '🔴'
            print(f"\n[{timestamp}] {status} STATUS")
            print(f"   Online: {payload.get('online')}")
            if 'sensors' in payload:
                print(f"   Sensors: {payload['sensors']}")
        
        elif '/commands' in topic:
            print(f"\n[{timestamp}] 🎮 COMMAND")
            print(f"   Command: {payload.get('command')}")
            print(f"   Parameters: {payload.get('parameters', {})}")
        
        else:
            print(f"\n[{timestamp}] 📨 {topic}")
            print(f"   {json.dumps(payload, indent=2)}")
    
    except json.JSONDecodeError:
        print(f"\n[{timestamp}] 📨 {topic}")
        print(f"   Raw: {msg.payload.decode()}")

# Create client
client = mqtt.Client(client_id=CLIENT_ID, clean_session=True)
client.username_pw_set(USERNAME, PASSWORD)
client.on_connect = on_connect
client.on_message = on_message

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

try:
    client.connect(BROKER, PORT, keepalive=60)
    client.loop_forever()
except KeyboardInterrupt:
    print("\n\n⏹️  Stopping monitor...")
    client.disconnect()
except Exception as e:
    print(f"\n❌ Error: {e}")
