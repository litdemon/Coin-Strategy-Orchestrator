import sys
import os
import time
import json
import logging

# Add project root to path
sys.path.append(os.getcwd())

from messaging.factory import MessagingFactory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestMessaging")

def test_mqtt():
    logger.info("--- Testing MQTT Adapter ---")
    
    config = {
        "broker_type": "mqtt",
        "mqtt": {
            "host": "mqtt.toybox7.net",
            "port": 1883
        }
    }
    
    client = MessagingFactory.create_client(config)
    
    if not client.connect():
        logger.error("Failed to connect to MQTT broker")
        return
    
    received_messages = []
    
    def on_message(topic, payload):
        logger.info(f"Callback[{topic}]: {payload}")
        received_messages.append((topic, payload))
        
    test_topic = "test/messaging/system"
    payload_data = {"status": "ok", "timestamp": time.time()}
    
    client.subscribe(test_topic, on_message)
    time.sleep(1)
    
    client.publish(test_topic, payload_data)
    time.sleep(2)  # Wait for message roundtrip
    
    if len(received_messages) > 0:
        logger.info("✅ MQTT Test Passed: Message received")
    else:
        logger.error("❌ MQTT Test Failed: No message received")
        
    client.disconnect()

def test_redis_stub():
    logger.info("--- Testing Redis Adapter (Stub) ---")
    
    config = {
        "broker_type": "redis"
    }
    
    client = MessagingFactory.create_client(config)
    client.connect()
    # Stub just logs, so we assume success if no error raised
    client.subscribe("test/topic", lambda t, p: None)
    client.publish("test/topic", {"msg": "hello"})
    client.disconnect()
    logger.info("✅ Redis Stub Test Passed")

    test_mqtt()
    test_redis_stub()
    test_socket()

def test_socket():
    logger.info("--- Testing Socket Adapter ---")
    
    config = {
        "broker_type": "socket",
        "socket": {
            "host": "localhost",
            "port": 9999
        }
    }
    
    client = MessagingFactory.create_client(config)
    
    # We assume 'verify/socket_broker.py' is running!
    # Without it, connect might fail.
    try:
        if not client.connect():
            logger.error("Failed to connect to Socket Broker (Is verify/socket_broker.py running?)")
            return
            
        received_messages = []
        def on_message(topic, payload):
            logger.info(f"Socket Callback[{topic}]: {payload}")
            received_messages.append((topic, payload))
            
        test_topic = "test/socket"
        client.subscribe(test_topic, on_message)
        time.sleep(0.5)
        
        client.publish(test_topic, {"msg": "hello socket"})
        time.sleep(1)
        
        if len(received_messages) > 0:
            logger.info("✅ Socket Test Passed")
        else:
            logger.error("❌ Socket Test Failed (No echo received)")
            
        client.disconnect()
    except ConnectionRefusedError:
        logger.error("Connection Refused. Start socket_broker.py first.")

if __name__ == "__main__":
    test_mqtt()
    test_redis_stub()
    test_socket()
