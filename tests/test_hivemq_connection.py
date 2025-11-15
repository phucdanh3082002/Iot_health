#!/usr/bin/env python3
"""
Test HiveMQ Cloud MQTT Connection
Script để verify kết nối và publish/subscribe với HiveMQ Cloud broker

Usage:
    python tests/test_hivemq_connection.py
"""

import sys
import os
import time
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(project_root / '.env')

import yaml
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import MQTT client
from src.communication.mqtt_client import IoTHealthMQTTClient
from src.communication.mqtt_payloads import VitalsPayload


def load_config():
    """Load application config"""
    config_path = project_root / 'config' / 'app_config.yaml'
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def test_basic_connection():
    """Test basic MQTT connection to HiveMQ Cloud"""
    logger.info("=" * 70)
    logger.info("TEST 1: Basic Connection to HiveMQ Cloud")
    logger.info("=" * 70)
    
    try:
        # Load config
        config = load_config()
        
        # Show connection info
        mqtt_cfg = config['communication']['mqtt']
        logger.info(f"Broker: {mqtt_cfg['broker']}:{mqtt_cfg['port']}")
        logger.info(f"Username: {mqtt_cfg['username']}")
        logger.info(f"Device ID: {mqtt_cfg['device_id']}")
        logger.info(f"TLS Enabled: {mqtt_cfg.get('use_tls', True)}")
        
        # Create MQTT client
        logger.info("\n📡 Creating MQTT client...")
        client = IoTHealthMQTTClient(config)
        
        # Connect
        logger.info("🔌 Connecting to HiveMQ Cloud...")
        if client.connect():
            logger.info("✅ Connection initiated (async)")
            
            # Wait for connection
            logger.info("⏳ Waiting for connection confirmation...")
            for i in range(10):
                time.sleep(1)
                if client.is_connected:
                    logger.info(f"✅ Connected successfully after {i+1} seconds!")
                    break
                logger.info(f"   Waiting... ({i+1}/10)")
            else:
                logger.error("❌ Connection timeout after 10 seconds")
                return False
            
            # Show connection status
            status = client.get_connection_status()
            logger.info("\n📊 Connection Status:")
            logger.info(f"   Connected: {status['is_connected']}")
            logger.info(f"   Broker: {status['broker']}")
            logger.info(f"   Device ID: {status['device_id']}")
            logger.info(f"   Patient ID: {status['patient_id']}")
            logger.info(f"   TLS: {status['use_tls']}")
            
            # Disconnect
            logger.info("\n🔌 Disconnecting...")
            client.disconnect()
            time.sleep(2)
            logger.info("✅ Test 1 PASSED\n")
            return True
        else:
            logger.error("❌ Failed to initiate connection")
            return False
    
    except Exception as e:
        logger.error(f"❌ Test 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_publish_vitals():
    """Test publishing vitals data"""
    logger.info("=" * 70)
    logger.info("TEST 2: Publish Vitals Data")
    logger.info("=" * 70)
    
    try:
        # Load config
        config = load_config()
        
        # Create client
        client = IoTHealthMQTTClient(config)
        
        # Connect
        logger.info("🔌 Connecting...")
        client.connect()
        
        # Wait for connection
        for i in range(10):
            time.sleep(1)
            if client.is_connected:
                break
        
        if not client.is_connected:
            logger.error("❌ Not connected")
            return False
        
        logger.info("✅ Connected")
        
        # Create sample vitals payload
        logger.info("\n📦 Creating sample vitals payload...")
        vitals = VitalsPayload(
            timestamp=time.time(),
            device_id=config['communication']['mqtt']['device_id'],
            patient_id=config.get('patient', {}).get('id', 'patient_001'),
            measurements={
                'heart_rate': {
                    'value': 78,
                    'unit': 'bpm',
                    'valid': True,
                    'confidence': 0.95,
                    'source': 'MAX30102',
                    'raw_metrics': {
                        'ir_quality': 50000,
                        'peak_count': 18,
                        'sampling_rate': 50.0
                    }
                },
                'spo2': {
                    'value': 97,
                    'unit': '%',
                    'valid': True,
                    'confidence': 0.92,
                    'source': 'MAX30102',
                    'raw_metrics': {
                        'r_value': 0.85,
                        'ac_red': 48000,
                        'dc_red': 1000000
                    }
                },
                'temperature': {
                    'object_temp': 36.7,
                    'ambient_temp': 24.2,
                    'unit': 'celsius',
                    'valid': True,
                    'source': 'MLX90614'
                }
            },
            session={
                'session_id': f"test_session_{int(time.time())}",
                'measurement_sequence': 1,
                'total_duration': 30.0,
                'user_triggered': True
            }
        )
        
        logger.info(f"   Device ID: {vitals.device_id}")
        logger.info(f"   Patient ID: {vitals.patient_id}")
        logger.info(f"   HR: {vitals.measurements['heart_rate']['value']} bpm")
        logger.info(f"   SpO2: {vitals.measurements['spo2']['value']} %")
        logger.info(f"   Temp: {vitals.measurements['temperature']['object_temp']} °C")
        
        # Publish
        logger.info("\n📤 Publishing to HiveMQ Cloud...")
        if client.publish_vitals(vitals):
            logger.info("✅ Vitals published successfully!")
            
            # Show stats
            stats = client.stats
            logger.info(f"\n📊 Statistics:")
            logger.info(f"   Messages sent: {stats['messages_sent']}")
            logger.info(f"   Messages received: {stats['messages_received']}")
        else:
            logger.error("❌ Failed to publish vitals")
            return False
        
        # Wait a bit before disconnect
        time.sleep(2)
        
        # Disconnect
        logger.info("\n🔌 Disconnecting...")
        client.disconnect()
        time.sleep(1)
        
        logger.info("✅ Test 2 PASSED\n")
        return True
    
    except Exception as e:
        logger.error(f"❌ Test 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_subscribe_commands():
    """Test subscribing to commands topic"""
    logger.info("=" * 70)
    logger.info("TEST 3: Subscribe to Commands")
    logger.info("=" * 70)
    
    try:
        # Load config
        config = load_config()
        
        # Create client
        client = IoTHealthMQTTClient(config)
        
        # Define command handler
        def command_handler(topic, data):
            logger.info(f"\n📥 Command received on '{topic}':")
            logger.info(f"   Command: {data.get('command')}")
            logger.info(f"   Parameters: {data.get('parameters')}")
        
        # Connect
        logger.info("🔌 Connecting...")
        client.connect()
        
        # Wait for connection
        for i in range(10):
            time.sleep(1)
            if client.is_connected:
                break
        
        if not client.is_connected:
            logger.error("❌ Not connected")
            return False
        
        logger.info("✅ Connected")
        
        # Subscribe to commands
        logger.info("\n📡 Subscribing to commands topic...")
        if client.subscribe_to_commands(command_handler):
            logger.info("✅ Subscribed successfully!")
            logger.info(f"   Topic: iot_health/patient/{client.patient_id}/commands")
            logger.info("\n💡 Waiting 10 seconds for incoming commands...")
            logger.info("   (You can publish a test command from HiveMQ dashboard)")
            
            # Wait for messages
            time.sleep(10)
        else:
            logger.error("❌ Failed to subscribe")
            return False
        
        # Disconnect
        logger.info("\n🔌 Disconnecting...")
        client.disconnect()
        time.sleep(1)
        
        logger.info("✅ Test 3 PASSED\n")
        return True
    
    except Exception as e:
        logger.error(f"❌ Test 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    logger.info("\n" + "=" * 70)
    logger.info("HiveMQ Cloud MQTT Connection Tests")
    logger.info("=" * 70 + "\n")
    
    # Check environment variables
    mqtt_password = os.getenv('MQTT_PASSWORD')
    if not mqtt_password:
        logger.error("❌ MQTT_PASSWORD environment variable not set!")
        logger.error("   Please set it in .env file or export it:")
        logger.error("   export MQTT_PASSWORD='your_hivemq_password'")
        return
    
    logger.info("✅ Environment variables loaded")
    logger.info(f"   MQTT_PASSWORD: {'*' * len(mqtt_password)}\n")
    
    # Run tests
    results = []
    
    # Test 1: Basic connection
    results.append(("Basic Connection", test_basic_connection()))
    
    # Test 2: Publish vitals
    results.append(("Publish Vitals", test_publish_vitals()))
    
    # Test 3: Subscribe commands
    results.append(("Subscribe Commands", test_subscribe_commands()))
    
    # Summary
    logger.info("=" * 70)
    logger.info("TEST SUMMARY")
    logger.info("=" * 70)
    
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        logger.info(f"{name:.<50} {status}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    logger.info(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("\n🎉 All tests PASSED! HiveMQ Cloud connection working perfectly!")
    else:
        logger.error(f"\n⚠️  {total - passed} test(s) FAILED. Please check the errors above.")


if __name__ == '__main__':
    main()
