import socket
import threading
import json
import logging
import time
from typing import Callable, Dict, Any, Optional
from ..interface import MessagingClient

logger = logging.getLogger(__name__)

class LocalSocketAdapter(MessagingClient):
    """
    Local Socket Adapter (TCP or Unix Domain Socket).
    Protocol: JSON lines.
    """

    def __init__(self, host: str = 'localhost', port: int = 9999, socket_path: str = None):
        self.host = host
        self.port = port
        self.socket_path = socket_path
        self.sock: Optional[socket.socket] = None
        self.is_connected = False
        self.message_callbacks: Dict[str, Callable] = {}
        self._listen_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def connect(self) -> bool:
        try:
            if self.socket_path:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.connect(self.socket_path)
            else:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((self.host, self.port))
            
            self.is_connected = True
            self._stop_event.clear()
            self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._listen_thread.start()
            logger.info("✅ Socket Connected")
            return True
        except Exception as e:
            logger.error(f"❌ Socket Connection Failed: {e}")
            self.is_connected = False
            return False

    def disconnect(self):
        self.is_connected = False
        self._stop_event.set()
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
            except:
                pass
            self.sock = None
        logger.info("Socket Disconnected")

    def _listen_loop(self):
        buffer = ""
        while not self._stop_event.is_set():
            try:
                if not self.sock:
                    break
                data = self.sock.recv(4096)
                if not data:
                    break
                buffer += data.decode('utf-8')
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if not line.strip():
                        continue
                    self._process_message(line)
            except Exception as e:
                if not self._stop_event.is_set():
                    logger.error(f"Socket receive error: {e}")
                break
        self.is_connected = False

    def _process_message(self, line: str):
        try:
            # Protocol: Broker sends {"topic": "...", "payload": ...}
            # Payload is a string (if it comes from MQTT originally) or dict/json? 
            # The interface says callback(topic, payload: str).
            # So we expect payload to be a string or we convert it.
            
            data = json.loads(line)
            topic = data.get("topic")
            payload = data.get("payload")
            
            if topic is not None and payload is not None:
                # Convert payload to str if it's dict (to match interface expectations if needed)
                # But interface type hint is str? 
                # MessagingClient.subscribe payload type is str based on MqttAdapter.
                if not isinstance(payload, str):
                    payload = json.dumps(payload)

                # Pattern matching
                for pattern, callback in self.message_callbacks.items():
                    if self._topic_matches(topic, pattern):
                        try:
                            callback(topic, payload)
                        except Exception as e:
                            logger.error(f"Callback error: {e}")
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {line}")

    def _topic_matches(self, topic: str, pattern: str) -> bool:
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

    def subscribe(self, topic: str, callback: Callable[[str, str], None], qos: int = 1):
        self.message_callbacks[topic] = callback
        # Send subscribe command to broker
        msg = {"action": "subscribe", "topic": topic}
        self._send(msg)
        logger.info(f"Subscribed to {topic}")

    def unsubscribe(self, topic: str):
        if topic in self.message_callbacks:
            del self.message_callbacks[topic]
        msg = {"action": "unsubscribe", "topic": topic}
        self._send(msg)
        logger.info(f"Unsubscribed from {topic}")

    def publish(self, topic: str, message: Dict[str, Any], qos: int = 1, retain: bool = False) -> bool:
        msg = {
            "action": "publish",
            "topic": topic,
            "payload": message,
            "retain": retain
        }
        return self._send(msg)

    def _send(self, data: dict) -> bool:
        if not self.sock:
            return False
        try:
            line = json.dumps(data) + "\n"
            self.sock.sendall(line.encode('utf-8'))
            return True
        except Exception as e:
            logger.error(f"Send error: {e}")
            return False
