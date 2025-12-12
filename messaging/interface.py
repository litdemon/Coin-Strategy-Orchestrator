from abc import ABC, abstractmethod
from typing import Callable, Any, Dict

class MessagingClient(ABC):
    """Abstract Base Class for Messaging Infrastructure"""

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the messaging broker."""
        pass

    @abstractmethod
    def disconnect(self):
        """Disconnect from the messaging broker."""
        pass

    @abstractmethod
    def subscribe(self, topic: str, callback: Callable[[str, str], None], qos: int = 1):
        """
        Subscribe to a topic.
        
        Args:
            topic: The topic to subscribe to.
            callback: Function to be called when a message is received. 
                      Signature: (topic: str, payload: str)
            qos: Quality of Service level (default 1).
        """
        pass

    @abstractmethod
    def unsubscribe(self, topic: str):
        """Unsubscribe from a topic."""
        pass

    @abstractmethod
    def publish(self, topic: str, message: Dict[str, Any], qos: int = 1, retain: bool = False) -> bool:
        """
        Publish a message to a topic.
        
        Args:
            topic: The topic to publish to.
            message: A dictionary representing the message payload (will be JSON serialized).
            qos: Quality of Service level (default 1).
            retain: Whether to retain the message (default False).
            
        Returns:
            bool: True if published successfully, False otherwise.
        """
        pass
