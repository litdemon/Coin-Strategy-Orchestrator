import os
import asyncio
from dotenv import load_dotenv
from upbit.upbit_websocket import UpbitWebSocket, WebsocketObserver
load_dotenv(os.path.join(os.path.expanduser("~"), ".config", "upbit.env"))   

UPBIT_ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY")
UPBIT_SECRET_KEY = os.getenv("UPBIT_SECRET_KEY")

DB_PATH = "assets.db"


class Manager(WebsocketObserver):
    def __init__(self):
        self.upbit_websocket = UpbitWebSocket(codes=["KRW-BTC"], observer=self)

    def run(self):
        self.upbit_websocket.start()

    def stop(self):
        self.upbit_websocket.stop()

    def on_ws_opened(self, cls):
        print("WebSocket Opened")

    def on_ws_message(self, cls, message: dict):
        print("WebSocket Message: ", message)

    def on_ws_closed(self, cls):
        print("WebSocket Closed")

async def main():
    manager = Manager()
    manager.run()
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        manager.stop()

if __name__ == "__main__":
    asyncio.run(main())