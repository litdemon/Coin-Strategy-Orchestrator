import websocket
import json
import uuid
import jwt
import time
import threading
import logging
from abc import ABC, abstractmethod
from typing import Optional, List 
from messages.myOrder import MyOrder

logger = logging.getLogger("UpbitWebSocket")

class WebsocketObserver(ABC):
    @abstractmethod
    def on_ws_opened(self, cls):
        pass

    @abstractmethod
    def on_ws_message(self, cls, message: dict):
        pass

    @abstractmethod
    def on_ws_closed(self, cls):
        pass

class UpbitWebSocket:
    def __init__(self, observer: WebsocketObserver):
        self.observer = observer
        self.ws: Optional[websocket.WebSocketApp] = None
        self.is_running = False
        self.thread = None
        self.reconnect_delay = 3
        
        self.uri = "wss://api.upbit.com/websocket/v1"
        self.request = None
        self.headers = None

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            self.observer.on_ws_message(self, data)
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    def _on_error(self, ws, error):
        logger.error(f"WebSocket Error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        logger.info("WebSocket Closed")
        self.observer.on_ws_closed(self)

    def _on_open(self, ws):

        logger.info(f"WebSocket Opened {self.request}")
        self.observer.on_ws_opened(self)
        if self.request:
            ws.send(json.dumps(self.request))

    def _run_forever(self):
        while self.is_running:
            try:
                self.ws = websocket.WebSocketApp(
                    self.uri,
                    header=self.headers,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                    on_open=self._on_open
                )
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                logger.error(f"WebSocket connection failed: {e}")
            
            if self.is_running:
                logger.info(f"Reconnecting in {self.reconnect_delay} seconds...")
                time.sleep(self.reconnect_delay)

    def update_subscription(self, codes: List[str]):
        if not self.ws:
            return
        req = []
        req.append({"ticket": str(uuid.uuid4())[:6]})
        if codes:
            req.append({"type": "trade", "codes": codes, "isOnlyRealtime": True})
            req.append({"type": "orderbook", "codes": codes, "isOnlyRealtime": True})
        self.ws.send(json.dumps(req))

    def start(self):
        logger.info("UpbitWebSocketPrivate started")
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._run_forever, daemon=True)
        self.thread.start()
        logger.info("UpbitWebSocketPrivate started")

    def stop(self):
        self.is_running = False
        if self.ws:
            self.ws.close()
        if self.thread:
            self.thread.join(timeout=1)
        logger.info("UpbitWebSocket stopped")


class UpbitWebSocketPrivate(UpbitWebSocket):
    def __init__(self, access_key: str = None, secret_key: str = None, observer: WebsocketObserver = None):
        super().__init__(observer=observer)
        self.access_key = access_key
        self.secret_key = secret_key
        self.uri = "wss://api.upbit.com/websocket/v1/private"
        self.request = [
            {"ticket": str(uuid.uuid4())},
            {"type": "myOrder", "codes": []},
            {"type": "myAsset"}
        ]
        self.headers = {
            "Authorization": f"Bearer {self._make_jwt()}"
        }

    def _make_jwt(self):
        payload = {"access_key": self.access_key, "nonce": str(uuid.uuid4())}
        return jwt.encode(payload, self.secret_key, algorithm="HS256")
    