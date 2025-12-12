import socket
import threading
import json
import time

def handle_client(conn, addr):
    print(f"New connection from {addr}")
    # Subscriptions for this client
    subscriptions = set()
    
    with conn:
        buffer = ""
        while True:
            try:
                data = conn.recv(1024)
                if not data:
                    break
                buffer += data.decode()
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if not line: continue
                    print(f"Received from {addr}: {line}")
                    
                    try:
                        msg = json.loads(line)
                        action = msg.get("action")
                        
                        if action == "subscribe":
                            topic = msg.get("topic")
                            subscriptions.add(topic)
                            # Echo back optional check?
                            
                        elif action == "publish":
                            topic = msg.get("topic")
                            payload = msg.get("payload")
                            # In a real broker, distribute to other clients.
                            # Here we just echo it back if subscribed for testing roundtrip
                            # Or we can just send it back immediately
                            
                            response = {
                                "topic": topic,
                                "payload": payload
                            }
                            resp_line = json.dumps(response) + "\n"
                            conn.sendall(resp_line.encode())
                            
                    except json.JSONDecodeError:
                        print("Invalid JSON")
            except Exception as e:
                print(f"Error: {e}")
                break
    print(f"Connection closed {addr}")

def main():
    host = 'localhost'
    port = 9999
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen()
    print(f"Socket Broker listening on {host}:{port}")
    
    try:
        while True:
            conn, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr))
            t.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()

if __name__ == "__main__":
    main()
