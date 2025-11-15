"""
MQTT Client - Production Ready
MQTT client cho real-time data transmission và remote monitoring

Features:
- TLS/SSL encryption (HiveMQ Cloud compatible)
- Auto-reconnect với exponential backoff
- QoS support (0, 1, 2)
- Thread-safe operations
- Last Will & Testament
- Message handlers
- Connection monitoring
"""

from typing import Dict, Any, Optional, Callable, List
import logging
import json
import ssl
import time
import os
import paho.mqtt.client as mqtt
from threading import Lock, Thread
from pathlib import Path

from .mqtt_payloads import (
    VitalsPayload,
    AlertPayload,
    DeviceStatusPayload,
    CommandPayload
)


class IoTHealthMQTTClient:
    """
    MQTT client cho IoT Health Monitoring System
    
    Attributes:
        config (Dict): MQTT configuration
        client (mqtt.Client): Paho MQTT client instance
        is_connected (bool): Connection status
        device_id (str): Unique device identifier
        patient_id (str): Patient identifier
        message_handlers (Dict): Dictionary of message handlers
        connection_lock (Lock): Thread lock for connection operations
        retry_count (int): Current retry count for reconnection
        max_retries (int): Maximum reconnection attempts
        base_retry_delay (float): Base delay for exponential backoff
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize MQTT client
        
        Args:
            config: Full app configuration dictionary
        """
        self.logger = logging.getLogger(__name__)
        self.config = config
        
        # Extract MQTT config
        mqtt_cfg = config.get('communication', {}).get('mqtt', {})
        
        # Connection parameters
        self.broker = mqtt_cfg.get('broker', 'localhost')
        self.port = mqtt_cfg.get('port', 8883)
        self.device_id = mqtt_cfg.get('device_id', 'rpi_001')
        self.patient_id = config.get('patient', {}).get('id', 'P12345')
        
        # Authentication - load from environment variable if specified
        self.username = mqtt_cfg.get('username')
        password_env = mqtt_cfg.get('password_env')
        if password_env:
            # Load password from environment variable (e.g., MQTT_PASSWORD)
            self.password = os.getenv(password_env)
            if not self.password:
                self.logger.warning(
                    f"Environment variable '{password_env}' not set. "
                    f"Falling back to password from config."
                )
                self.password = mqtt_cfg.get('password')
        else:
            self.password = mqtt_cfg.get('password')
        
        # TLS/SSL
        self.use_tls = mqtt_cfg.get('use_tls', True)
        self.ca_cert = mqtt_cfg.get('ca_cert')
        self.cert_file = mqtt_cfg.get('cert_file')
        self.key_file = mqtt_cfg.get('key_file')
        
        # QoS levels
        self.qos_vitals = mqtt_cfg.get('qos', {}).get('vitals', 1)
        self.qos_alerts = mqtt_cfg.get('qos', {}).get('alerts', 2)
        self.qos_status = mqtt_cfg.get('qos', {}).get('status', 0)
        self.qos_commands = mqtt_cfg.get('qos', {}).get('commands', 2)
        
        # Connection settings
        self.keepalive = mqtt_cfg.get('keepalive', 60)
        self.reconnect_delay = mqtt_cfg.get('reconnect_delay', 5)
        self.max_retries = mqtt_cfg.get('max_reconnect_attempts', 10)
        
        # State tracking
        self.is_connected = False
        self.connection_lock = Lock()
        self.retry_count = 0
        self.base_retry_delay = 2.0
        self.message_handlers = {}
        
        # Statistics
        self.stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'connection_attempts': 0,
            'last_connect_time': None,
            'last_disconnect_time': None
        }
        
        # Initialize MQTT client
        self.client = mqtt.Client(client_id=self.device_id, clean_session=False)
        self.client.username_pw_set(self.username, self.password)
        
        # Setup callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_publish = self._on_publish
        self.client.on_subscribe = self._on_subscribe
        
        # Setup TLS if enabled
        if self.use_tls:
            try:
                # HiveMQ Cloud uses Let's Encrypt CA (trusted by system)
                # Use default system CA certificates
                self.client.tls_set(
                    ca_certs=None,  # Use system default CA bundle
                    certfile=None,
                    keyfile=None,
                    cert_reqs=ssl.CERT_REQUIRED,
                    tls_version=ssl.PROTOCOL_TLS,
                    ciphers=None
                )
                self.client.tls_insecure_set(False)  # Verify hostname
                self.logger.info("TLS/SSL enabled with system CA certificates")
            except Exception as e:
                self.logger.error(f"Failed to setup TLS: {e}")
        
        # Setup Last Will & Testament
        last_will = mqtt_cfg.get('last_will', {})
        if last_will:
            will_topic = last_will.get('topic', '').replace('{device_id}', self.device_id)
            will_message = last_will.get('message', '').replace('{device_id}', self.device_id)
            self.client.will_set(
                will_topic,
                will_message,
                qos=last_will.get('qos', 1),
                retain=last_will.get('retain', True)
            )
            self.logger.info(f"Last Will set: {will_topic}")
        
        self.logger.info(
            f"MQTT Client initialized: broker={self.broker}:{self.port}, "
            f"device_id={self.device_id}, patient_id={self.patient_id}"
        )
    
    def connect(self) -> bool:
        """
        Kết nối đến MQTT broker
        
        Returns:
            bool: True nếu kết nối thành công hoặc đang trong quá trình kết nối
        """
        try:
            with self.connection_lock:
                if self.is_connected:
                    self.logger.info("Already connected to MQTT broker")
                    return True
                
                self.stats['connection_attempts'] += 1
            
            self.logger.info(f"Connecting to MQTT broker: {self.broker}:{self.port}...")
            
            # Connect async (non-blocking)
            self.client.connect_async(
                self.broker,
                port=self.port,
                keepalive=self.keepalive
            )
            
            # Start network loop in background thread
            self.client.loop_start()
            
            return True
        
        except Exception as e:
            self.logger.error(f"Connection error: {e}")
            self._handle_connection_error(e)
            return False
    
    def disconnect(self) -> bool:
        """
        Ngắt kết nối khỏi MQTT broker
        
        Returns:
            bool: True nếu disconnect thành công
        """
        try:
            with self.connection_lock:
                if not self.is_connected:
                    self.logger.info("Already disconnected from MQTT broker")
                    return True
            
            self.logger.info("Disconnecting from MQTT broker...")
            
            # Stop network loop
            self.client.loop_stop()
            
            # Disconnect
            self.client.disconnect()
            
            with self.connection_lock:
                self.is_connected = False
            
            return True
        
        except Exception as e:
            self.logger.error(f"Disconnect error: {e}")
            return False
    
    def _reconnect_with_backoff(self):
        """
        Thử kết nối lại với exponential backoff
        """
        while self.retry_count < self.max_retries:
            with self.connection_lock:
                if self.is_connected:
                    return
                
                self.retry_count += 1
            
            # Calculate backoff delay
            delay = min(
                self.base_retry_delay * (2 ** (self.retry_count - 1)),
                60.0  # Max 60 seconds
            )
            
            self.logger.info(
                f"Reconnecting in {delay:.1f}s "
                f"(attempt {self.retry_count}/{self.max_retries})..."
            )
            time.sleep(delay)
            
            try:
                self.client.reconnect()
                return
            except Exception as e:
                self.logger.error(f"Reconnect failed: {e}")
        
        self.logger.error(f"Max reconnection attempts ({self.max_retries}) exceeded")
    
    def _handle_connection_error(self, error: Exception):
        """
        Xử lý connection errors và trigger retry logic
        
        Args:
            error: Connection error exception
        """
        self.logger.error(f"Connection error occurred: {error}")
        
        # Start reconnection thread
        Thread(target=self._reconnect_with_backoff, daemon=True).start()
    
    def publish_vitals(
        self,
        vitals_payload: VitalsPayload,
        qos: Optional[int] = None
    ) -> bool:
        """
        Publish comprehensive vitals data với HX710B raw metrics
        
        Args:
            vitals_payload: VitalsPayload dataclass instance
            qos: Quality of service (None = use default)
        
        Returns:
            bool: True if publish initiated successfully
        """
        try:
            if not self.is_connected:
                self.logger.warning("Cannot publish - not connected to broker")
                return False
            
            topic = f"iot_health/device/{self.device_id}/vitals"
            payload_dict = vitals_payload.to_dict()
            payload_json = json.dumps(payload_dict, indent=None)
            
            result = self.client.publish(
                topic,
                payload_json,
                qos=qos if qos is not None else self.qos_vitals,
                retain=False
            )
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.stats['messages_sent'] += 1
                self.logger.info(f"📤 Published vitals to '{topic}' (qos={qos or self.qos_vitals})")
                return True
            else:
                self.logger.error(f"Publish failed (rc={result.rc})")
                return False
        
        except Exception as e:
            self.logger.error(f"Error publishing vitals: {e}")
            return False
    
    def publish_alert(
        self,
        alert_payload: AlertPayload,
        qos: Optional[int] = None
    ) -> bool:
        """
        Publish alert với trend analysis và recommended actions
        
        Args:
            alert_payload: AlertPayload dataclass instance
            qos: Quality of service (None = use default QoS 2)
        
        Returns:
            bool: True if publish successful
        """
        try:
            if not self.is_connected:
                self.logger.warning("Cannot publish alert - not connected")
                return False
            
            topic = f"iot_health/device/{self.device_id}/alerts"
            payload_dict = alert_payload.to_dict()
            payload_json = json.dumps(payload_dict, indent=None)
            
            result = self.client.publish(
                topic,
                payload_json,
                qos=qos if qos is not None else self.qos_alerts,
                retain=True  # Retain alerts for offline clients
            )
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.stats['messages_sent'] += 1
                self.logger.warning(
                    f"🚨 Published alert: {alert_payload.alert_type} "
                    f"severity={alert_payload.severity} (qos={qos or self.qos_alerts})"
                )
                return True
            else:
                self.logger.error(f"Alert publish failed (rc={result.rc})")
                return False
        
        except Exception as e:
            self.logger.error(f"Error publishing alert: {e}")
            return False
    
    def publish_status(
        self,
        status_payload: DeviceStatusPayload,
        qos: Optional[int] = None
    ) -> bool:
        """
        Publish device status với sensors/actuators/system health
        
        Args:
            status_payload: DeviceStatusPayload dataclass instance
            qos: Quality of service (None = use default QoS 0)
        
        Returns:
            bool: True if publish successful
        """
        try:
            if not self.is_connected:
                self.logger.debug("Cannot publish status - not connected")
                return False
            
            topic = f"iot_health/device/{self.device_id}/status"
            payload_dict = status_payload.to_dict()
            payload_json = json.dumps(payload_dict, indent=None)
            
            result = self.client.publish(
                topic,
                payload_json,
                qos=qos if qos is not None else self.qos_status,
                retain=True  # Retain status for monitoring
            )
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.stats['messages_sent'] += 1
                self.logger.debug(f"📊 Published status to '{topic}'")
                return True
            else:
                self.logger.error(f"Status publish failed (rc={result.rc})")
                return False
        
        except Exception as e:
            self.logger.error(f"Error publishing status: {e}")
            return False
    
    def subscribe_to_commands(
        self,
        callback: Callable[[str, Dict[str, Any]], None],
        qos: Optional[int] = None
    ) -> bool:
        """
        Subscribe to remote commands (start_measurement, calibrate, emergency_deflate)
        
        Args:
            callback: Function to handle command messages (topic, data) → None
            qos: Quality of service (None = use default QoS 2)
        
        Returns:
            bool: True if subscription successful
        """
        try:
            if not self.is_connected:
                self.logger.warning("Cannot subscribe - not connected")
                return False
            
            topic = f"iot_health/patient/{self.patient_id}/commands"
            
            # Add custom handler
            self.add_message_handler(topic, callback)
            
            # Subscribe
            result = self.client.subscribe(
                topic,
                qos=qos if qos is not None else self.qos_commands
            )
            
            if result[0] == mqtt.MQTT_ERR_SUCCESS:
                self.logger.info(f"📡 Subscribed to commands: '{topic}'")
                return True
            else:
                self.logger.error(f"Subscription failed (rc={result[0]})")
                return False
        
        except Exception as e:
            self.logger.error(f"Error subscribing to commands: {e}")
            return False
    
    def subscribe_to_predictions(
        self,
        callback: Callable[[str, Dict[str, Any]], None],
        qos: Optional[int] = None
    ) -> bool:
        """
        Subscribe to AI predictions từ edge/cloud AI
        
        Args:
            callback: Function to handle prediction messages (topic, data) → None
            qos: Quality of service (None = use default QoS 1)
        
        Returns:
            bool: True if subscription successful
        """
        try:
            if not self.is_connected:
                self.logger.warning("Cannot subscribe - not connected")
                return False
            
            topic = f"iot_health/patient/{self.patient_id}/predictions"
            
            # Add custom handler
            self.add_message_handler(topic, callback)
            
            # Subscribe
            result = self.client.subscribe(topic, qos=qos if qos is not None else 1)
            
            if result[0] == mqtt.MQTT_ERR_SUCCESS:
                self.logger.info(f"📡 Subscribed to predictions: '{topic}'")
                return True
            else:
                self.logger.error(f"Subscription failed (rc={result[0]})")
                return False
        
        except Exception as e:
            self.logger.error(f"Error subscribing to predictions: {e}")
            return False
    
    def _handle_command_message(self, topic: str, data: Dict[str, Any]):
        """
        Xử lý command messages từ remote (web/app)
        
        Args:
            topic: MQTT topic
            data: Parsed command data (from CommandPayload)
        """
        try:
            cmd = data.get('command')
            params = data.get('parameters', {})
            
            self.logger.info(f"📥 Command received: {cmd} with params {params}")
            
            # Route to appropriate handler (sẽ được override bởi main_app)
            if cmd == 'start_measurement':
                self.logger.info("Trigger BP measurement from remote command")
                # Main app sẽ handle thông qua custom callback
            
            elif cmd == 'calibrate_sensor':
                sensor_type = params.get('sensor_type')
                self.logger.info(f"Calibration request for {sensor_type}")
            
            elif cmd == 'emergency_deflate':
                self.logger.warning("⚠️ EMERGENCY DEFLATE command received!")
            
            else:
                self.logger.warning(f"Unknown command: {cmd}")
        
        except Exception as e:
            self.logger.error(f"Error handling command: {e}")
    
    def _handle_prediction_message(self, topic: str, data: Dict[str, Any]):
        """
        Xử lý AI prediction messages
        
        Args:
            topic: MQTT topic
            data: Parsed prediction data
        """
        try:
            prediction_type = data.get('prediction_type')
            result = data.get('result')
            
            self.logger.info(f"🤖 AI Prediction: {prediction_type} → {result}")
            
            # Custom handlers sẽ xử lý chi tiết hơn
        
        except Exception as e:
            self.logger.error(f"Error handling prediction: {e}")
    
    def _setup_ssl_context(self) -> ssl.SSLContext:
        """
        Setup SSL context for secure MQTT connection
        
        Returns:
            ssl.SSLContext: Configured SSL context
        
        Raises:
            FileNotFoundError: If certificate files not found
            ssl.SSLError: If SSL setup fails
        """
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        
        # Load CA certificate
        if self.ca_cert and Path(self.ca_cert).exists():
            context.load_verify_locations(cafile=self.ca_cert)
        else:
            raise FileNotFoundError(f"CA certificate not found: {self.ca_cert}")
        
        # Load client certificates if provided
        if self.cert_file and self.key_file:
            if Path(self.cert_file).exists() and Path(self.key_file).exists():
                context.load_cert_chain(certfile=self.cert_file, keyfile=self.key_file)
                self.logger.info("Client certificates loaded for mutual TLS")
            else:
                raise FileNotFoundError("Client certificate or key file not found")
        
        return context
    
    def _on_connect(self, client, userdata, flags, rc):
        """
        Callback khi kết nối thành công/thất bại
        
        Args:
            client: MQTT client instance
            userdata: User data
            flags: Connection flags dict
            rc: Connection result code (0 = success)
        """
        if rc == 0:
            with self.connection_lock:
                self.is_connected = True
                self.retry_count = 0
                self.stats['last_connect_time'] = time.time()
            
            self.logger.info(f"✅ Connected to MQTT broker: {self.broker}:{self.port}")
            
            # Auto-subscribe to commands topic
            cmd_topic = f"iot_health/patient/{self.patient_id}/commands"
            result = client.subscribe(cmd_topic, qos=self.qos_commands)
            if result[0] == mqtt.MQTT_ERR_SUCCESS:
                self.logger.info(f"📡 Auto-subscribed to {cmd_topic}")
        else:
            error_messages = {
                1: "Connection refused - incorrect protocol version",
                2: "Connection refused - invalid client identifier",
                3: "Connection refused - server unavailable",
                4: "Connection refused - bad username or password",
                5: "Connection refused - not authorized"
            }
            error_msg = error_messages.get(rc, f"Unknown error code: {rc}")
            self.logger.error(f"❌ MQTT connection failed: {error_msg}")
            
            # Trigger reconnection with backoff
            Thread(target=self._reconnect_with_backoff, daemon=True).start()
    
    def _on_disconnect(self, client, userdata, rc):
        """
        Callback khi ngắt kết nối
        
        Args:
            client: MQTT client instance
            userdata: User data
            rc: Disconnect reason code (0 = normal disconnect)
        """
        with self.connection_lock:
            self.is_connected = False
            self.stats['last_disconnect_time'] = time.time()
        
        if rc == 0:
            self.logger.info("🔌 Disconnected from MQTT broker (clean disconnect)")
        else:
            self.logger.warning(f"⚠️ Unexpected disconnect from broker (rc={rc})")
            # Auto-reconnect on unexpected disconnect
            Thread(target=self._reconnect_with_backoff, daemon=True).start()
    
    def _on_message(self, client, userdata, msg):
        """
        Callback khi nhận message từ subscribed topics
        
        Args:
            client: MQTT client instance
            userdata: User data
            msg: Received MQTT message
        """
        try:
            self.stats['messages_received'] += 1
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            
            self.logger.debug(f"📥 Received message on '{topic}': {payload[:100]}...")
            
            # Parse JSON payload
            data = json.loads(payload)
            
            # Route to appropriate handler
            if '/commands' in topic:
                self._handle_command_message(topic, data)
            elif '/predictions' in topic:
                self._handle_prediction_message(topic, data)
            
            # Call custom handlers
            for pattern, handler in self.message_handlers.items():
                if pattern in topic or mqtt.topic_matches_sub(pattern, topic):
                    try:
                        handler(topic, data)
                    except Exception as e:
                        self.logger.error(f"Handler error for '{pattern}': {e}")
        
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON payload on '{msg.topic}': {e}")
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
    
    def _on_publish(self, client, userdata, mid):
        """
        Callback khi message được publish thành công
        
        Args:
            client: MQTT client instance
            userdata: User data
            mid: Message ID
        """
        self.logger.debug(f"✅ Message published (mid={mid})")
    
    def _on_subscribe(self, client, userdata, mid, granted_qos):
        """
        Callback khi subscription thành công
        
        Args:
            client: MQTT client instance
            userdata: User data
            mid: Message ID
            granted_qos: List of granted QoS levels
        """
        self.logger.info(f"✅ Subscription confirmed (mid={mid}, qos={granted_qos})")
    
    def add_message_handler(self, topic_pattern: str, handler: Callable):
        """
        Add custom message handler for specific topic pattern
        
        Args:
            topic_pattern: Topic pattern (hỗ trợ MQTT wildcards +/#)
            handler: Callback function (topic, data) → None
        """
        self.message_handlers[topic_pattern] = handler
        self.logger.info(f"Added message handler for '{topic_pattern}'")
    
    def remove_message_handler(self, topic_pattern: str):
        """
        Remove message handler for topic pattern
        
        Args:
            topic_pattern: Topic pattern to remove
        """
        if topic_pattern in self.message_handlers:
            del self.message_handlers[topic_pattern]
            self.logger.info(f"Removed message handler for '{topic_pattern}'")
    
    def get_connection_status(self) -> Dict[str, Any]:
        """
        Get connection status và statistics
        
        Returns:
            Dict chứa connection info và stats
        """
        with self.connection_lock:
            return {
                'is_connected': self.is_connected,
                'broker': f"{self.broker}:{self.port}",
                'device_id': self.device_id,
                'patient_id': self.patient_id,
                'retry_count': self.retry_count,
                'use_tls': self.use_tls,
                'stats': self.stats.copy()
            }
    
    def _build_topic(self, *topic_parts) -> str:
        """
        Build MQTT topic từ các parts
        
        Args:
            topic_parts: Topic components
        
        Returns:
            Complete topic string
        """
        return '/'.join(str(part) for part in topic_parts if part)