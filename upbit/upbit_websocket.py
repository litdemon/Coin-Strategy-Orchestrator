import websocket
import json
import uuid
import jwt
import time
import threading
import logging
from abc import ABC, abstractmethod
from typing import Optional, List 

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

class UpbitWebSocketBase(ABC):
    def __init__(self, observer: WebsocketObserver):
        self.observer = observer
        self.ws: Optional[websocket.WebSocketApp] = None
        self.is_running = False
        self.thread = None
        self.reconnect_delay = 3
        self.uri = None
        self.headers = None
        self.request = None

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

    def start(self):
        logger.info(f"{self.__class__.__name__} started")
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._run_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_running = False
        if self.ws:
            self.ws.close()
        if self.thread:
            self.thread.join(timeout=1)
        logger.info(f"{self.__class__.__name__} stopped")

class UpbitWebSocket(UpbitWebSocketBase):
    def __init__(self, codes: List[str] = None, observer: WebsocketObserver = None):
        super().__init__(observer=observer)
        self.uri = "wss://api.upbit.com/websocket/v1"
        self.codes = codes or []
        self._update_request()

    def _update_request(self):
        req = [{"ticket": str(uuid.uuid4())[:6]}]
        if self.codes:
            req.append({"type": "ticker", "codes": self.codes})
            req.append({"type": "trade", "codes": self.codes})
            req.append({"type": "orderbook", "codes": self.codes})
        self.request = req

    def add_subscription(self, codes: List[str]):
        self.codes.extend(codes)
        self._update_request()
        if self.ws and self.ws.keep_running:
            self.ws.send(json.dumps(self.request))

    def remove_subscription(self, codes: List[str]):
        self.codes = [code for code in self.codes if code not in codes]
        self._update_request()
        if self.ws and self.ws.keep_running:
            self.ws.send(json.dumps(self.request))

class UpbitWebSocketPrivate(UpbitWebSocketBase):
    def __init__(self, access_key: str = None, secret_key: str = None, observer: WebsocketObserver = None):
        super().__init__(observer=observer)
        self.access_key = access_key
        self.secret_key = secret_key
        self.uri = "wss://api.upbit.com/websocket/v1/private"
        self.headers = {
            "Authorization": f"Bearer {self._make_jwt()}"
        }
        self.request = [
            {"ticket": str(uuid.uuid4())},
            {"type": "myOrder", "codes": []},
            {"type": "myAsset"}
        ]

    def _make_jwt(self):
        payload = {"access_key": self.access_key, "nonce": str(uuid.uuid4())}
        return jwt.encode(payload, self.secret_key, algorithm="HS256")