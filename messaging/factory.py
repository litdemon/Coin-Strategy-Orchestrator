from typing import Dict, Any
from .interface import MessagingClient
from .adapters.mqtt_adapter import MqttAdapter
from .adapters.redis_adapter import RedisAdapter
from .adapters.socket_adapter import LocalSocketAdapter

class MessagingFactory:
    """Factory to create messaging clients based on configuration."""

    @staticmethod
    def create_client(config: Dict[str, Any]) -> MessagingClient:
        """
        Create a messaging client.
        
        Args:
            config: Configuration dictionary. 
                    Must contain 'broker_type' ('mqtt' or 'redis').
                    Other keys depend on the broker type.
        """
        broker_type = config.get("broker_type", "mqtt").lower()

        if broker_type == "mqtt":
            mqtt_config = config.get("mqtt", {})
            return MqttAdapter(
                host=mqtt_config.get("host", "localhost"),
                port=mqtt_config.get("port", 1883),
                username=mqtt_config.get("username"),
                password=mqtt_config.get("password"),
                client_id=config.get("client_id")
            )
        elif broker_type == "redis":
            redis_config = config.get("redis", {})
            return RedisAdapter(
                host=redis_config.get("host", "localhost"),
                port=redis_config.get("port", 6379),
                db=redis_config.get("db", 0)
            )
        elif broker_type == "socket":
            socket_config = config.get("socket", {})
            return LocalSocketAdapter(
                host=socket_config.get("host", "localhost"),
                port=socket_config.get("port", 9999),
                socket_path=socket_config.get("socket_path")
            )
        else:
            raise ValueError(f"Unsupported broker type: {broker_type}")
