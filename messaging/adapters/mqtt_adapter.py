import json
import logging
import uuid
from typing import Callable, Any, Dict, List
import paho.mqtt.client as mqtt
from ..interface import MessagingClient

logger = logging.getLogger(__name__)

class MqttAdapter(MessagingClient):
    """
    MQTT Adapter implementation using paho-mqtt.
    """

    def __init__(self, host: str, port: int = 1883, username: str = None, password: str = None, client_id: str = None):
        self.host = host
        self.port = port
        self.client_id = client_id or f"trading_client_{uuid.uuid4().hex[:8]}"
        
        self.client = mqtt.Client(client_id=self.client_id)
        
        if username and password:
            self.client.username_pw_set(username, password)
            
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        
        self.message_callbacks: Dict[str, Callable] = {}
        self.is_connected = False
        
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"✅ MQTT Connected: {self.client_id}")
            self.is_connected = True
            # Resubscribe to existing topics connection is re-established
            for topic, _ in self.message_callbacks.items():
                self.client.subscribe(topic)
        else:
            logger.error(f"❌ MQTT Connection failed with code {rc}")
            self.is_connected = False

    def _on_disconnect(self, client, userdata, rc):
        logger.warning(f"⚠️  MQTT Disconnected: {self.client_id}")
        self.is_connected = False

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = msg.payload.decode()
        except UnicodeDecodeError:
            logger.warning(f"Could not decode payload from {topic}")
            return

        logger.info(f"📨 Received message on {topic}")
        
        # Pattern matching for callbacks
        for pattern, callback in self.message_callbacks.items():
            if self._topic_matches(topic, pattern):
                try:
                    callback(topic, payload)
                except Exception as e:
                    logger.error(f"❌ Callback error for {topic}: {e}")

    def _topic_matches(self, topic: str, pattern: str) -> bool:
        """Check if topic matches the MQTT subscription pattern."""
        if pattern == "#":
            return True
            
        topic_parts = topic.split('/')
        pattern_parts = pattern.split('/')
        
        if len(pattern_parts) > len(topic_parts):
            return False
            
        for i, pattern_part in enumerate(pattern_parts):
            if pattern_part == '#':
                return True
            if i >= len(topic_parts):
                return False
            if pattern_part != '+' and pattern_part != topic_parts[i]:
                return False
                
        return len(pattern_parts) == len(topic_parts)

    def connect(self) -> bool:
        try:
            self.client.connect(self.host, self.port, 60)
            self.client.loop_start()
            
            # Wait for connection
            import time
            timeout = 5
            while not self.is_connected and timeout > 0:
                time.sleep(0.1)
                timeout -= 0.1
                
            return self.is_connected
        except Exception as e:
            logger.error(f"❌ Connection error: {e}")
            return False

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()

    def subscribe(self, topic: str, callback: Callable[[str, str], None], qos: int = 1):
        self.message_callbacks[topic] = callback
        self.client.subscribe(topic, qos=qos)
        logger.info(f"📥 Subscribed to {topic}")

    def unsubscribe(self, topic: str):
        if topic in self.message_callbacks:
            del self.message_callbacks[topic]
        self.client.unsubscribe(topic)
        logger.info(f"🔕 Unsubscribed from {topic}")

    def publish(self, topic: str, message: Dict[str, Any], qos: int = 1, retain: bool = False) -> bool:
        try:
            payload = json.dumps(message)
            result = self.client.publish(topic, payload, qos=qos, retain=retain)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug(f"📤 Published to {topic}")
                return True
            else:
                logger.error(f"❌ Publish failed: {result.rc}")
                return False
        except Exception as e:
            logger.error(f"❌ Publish error: {e}")
            return False
