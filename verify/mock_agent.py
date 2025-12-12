import time
import json
import uuid
import sys
import os
import threading

# Add project root to sys.path
sys.path.append(os.getcwd())

from messaging.factory import MessagingFactory

def mock_agent():
    print("🤖 Mock Agent Starting...")
    config = {
        "broker_type": "mqtt",
        "mqtt": {
            "host": "mqtt.toybox7.net",
            "port": 1883,
            "client_id": f"mock_agent_{int(time.time())}"
        }
    }
    client = MessagingFactory.create_client(config)
    
    if not client.connect():
        print("❌ Mock Agent failed to connect")
        return

    def on_message(topic, payload):
        print(f"🤖 Mock Agent Received: {payload}")
        try:
            data = json.loads(payload)
            action = data.get("action")
            
            if action == "status":
                response = {
                    "running": True,
                    "agent": "MockAgent",
                    "timestamp": time.time()
                }
                client.publish("trading/response/status", response)
                print("🤖 Sent Status Response")
        except:
            pass

    client.subscribe("trading/command/#", on_message)
    print("🤖 Mock Agent Listening...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        client.disconnect()

if __name__ == "__main__":
    mock_agent()
