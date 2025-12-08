import asyncio
import logging
from upbit.upbit_websocket import UpbitWebSocket, WebsocketObserver
from abc import ABC, abstractmethod

# 로깅 설정
logging.basicConfig(level=logging.INFO)


class Observer(WebsocketObserver):

    def on_ws_opened(self, cls):
        print("WebSocket Opened")

    def on_ws_message(self, cls, message: dict):
        print("WebSocket Message: ", message)

    def on_ws_closed(self, cls):
        print("WebSocket Closed")

async def main():
    observer = Observer()
    upbit_websocket = UpbitWebSocket(codes=["KRW-BTC"], observer=observer)
    upbit_websocket.start()
    await asyncio.sleep(10)
    upbit_websocket.stop()

if __name__ == "__main__":
    asyncio.run(main())
