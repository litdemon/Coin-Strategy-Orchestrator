import os
import time
import logging
import pyupbit
import sys
import json
from decimal import Decimal



# Add project root to sys.path if not present
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List, Tuple, Any
from dotenv import load_dotenv

import pyupbit
from queue import Queue

# Import models
# Messaging
from messaging.factory import MessagingFactory
from messaging.interface import MessagingClient
from models.trade import Trade
from models.orderInfo import OrderInfo
from models.my_asset import MyAsset
from tools.ticker import Ticker
from tools.converter import Decimal2float
from tools.counter import Counter
from account.manager import AccountDBManager, AccountUpbitManager
from src.dashboard import Dashboard
from src.position_manager import Position, PositionManager
from src.current_price import CurrentPrice
from upbit.upbit_websocket import UpbitWebSocket, WebsocketObserver, UpbitWebSocketPrivate
from strategy.manager import StrategyManager

logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.expanduser("~"), ".config", "upbit.env"))   

UPBIT_ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY")
UPBIT_SECRET_KEY = os.getenv("UPBIT_SECRET_KEY")

DB_PATH = "account.db"





class Manager(WebsocketObserver):
    def __init__(self, virtual: bool = False):
        self.dashboard = Dashboard() # Initialize Dashboard

        if virtual:
            self.account_manager = AccountDBManager(callback=self.on_ws_message)
        else:
            self.account_manager = AccountUpbitManager(access_key=UPBIT_ACCESS_KEY, secret_key=UPBIT_SECRET_KEY)
        self.task_queue = Queue()
        self.counter = Counter()

    def init(self):
        balances = self.account_manager.get_balances()
        tickers = [ Ticker(asset.get("currency")) for asset in balances if asset.get("currency") != "KRW" ]

        self.upbit_websocket = UpbitWebSocket(codes=[ticker.ticker for ticker in tickers], observer=self)
        self.upbit_asset = UpbitWebSocketPrivate(access_key=UPBIT_ACCESS_KEY, secret_key=UPBIT_SECRET_KEY, observer=self)
        self.price_ob = CurrentPrice()
        
        # Initialize Messaging System
        mqtt_config = {
            "broker_type": "mqtt",
            "mqtt": {
                "host": "mqtt.toybox7.net",
                "port": 1883,
                "client_id": f"strategy_manager_{int(time.time())}"
            }
        }
        self.messaging = MessagingFactory.create_client(mqtt_config)
        if self.messaging.connect():
            self.dashboard.log("Messaging Connected")
            self.messaging.subscribe("trading/command/#", self.on_mqtt_message)
        else:
            self.dashboard.log("Messaging Connection Failed")

        # Initialize Strategy Manager
        self.strategy_manager = StrategyManager(db_path=DB_PATH, account_manager=self.account_manager)

        # Initialize Position Manager
        self.position_manager = PositionManager(db_path=DB_PATH)
        for balance in balances:
            ticker = Ticker(balance.get("currency"))
            self.dashboard.update_balance(balance)
            if ticker.currency == "KRW":
                continue

            # position이 없으면 default position 생성   
            if not self.position_manager.get_positions(ticker.ticker, only_active=True):
                current_price = pyupbit.get_current_price(ticker.ticker)
                # 총 balance의 25%를 position으로 사용
                balance = Decimal(balance.get("balance")) * Decimal(0.25)
                pos = self.position_manager.create_position(
                                            ticker=ticker.ticker, 
                                            entry_price=current_price, 
                                            volume=balance)
                self.strategy_manager.create_strategy(
                    type_name='tailingstop',
                    ticker=ticker.ticker,
                    budget=pos.volume,
                    config={
                        "trailing_stop": 0.05,
                        "take_profit": 0.1,
                        "stop_loss": 0.05
                    },
                    position_id = pos.id
                )
            
            

        # Log loaded positions
        for pos in self.position_manager.positions.values():
            self.dashboard.log(f"Loaded Position: {pos.ticker:<10} {pos.entry_price:<10,.0f} {pos.volume * pos.entry_price:,.0f}")
        
        # Update dashboard with loaded positions
        loaded_tickers = set(pos.ticker for pos in self.position_manager.positions.values())
        for ticker in loaded_tickers:
            self._update_positions_dashboard(ticker)
        
        

    def run(self):
        self.dashboard.start() # Start Dashboard
        self.upbit_websocket.start()
        self.upbit_asset.start()

        logger.info("Manager started")
        is_stop = False
        while not is_stop:
            try:
                task = self.task_queue.get()
                is_stop = self.on_task(**task)
            except Exception as e:
                logger.error(f"Error processing task: {e}")
        logger.info("Task queue is empty")

    def stop(self):
        self.upbit_websocket.stop()
        self.upbit_asset.stop()
        if self.messaging:
            self.messaging.disconnect()
        self.dashboard.stop()

    # -- WebSocket Events -------------------------
    def on_ws_opened(self, cls):
        self.dashboard.log("WebSocket Opened")

    def on_ws_closed(self, cls):
        self.dashboard.log("WebSocket Closed")

    def on_mqtt_message(self, topic: str, payload: str):
        """Callback for MQTT messages."""
        try:
            data = json.loads(payload)
            self.task_queue.put({
                "cls": self.messaging, 
                "message": {
                    "type": "command", 
                    "topic": topic, 
                    "data": data
                }
            })
        except json.JSONDecodeError:
            self.dashboard.log(f"Invalid JSON from {topic}")

    def on_ws_message(self, cls, message: dict):
        self.task_queue.put({"cls": cls, "message": message})   

    def on_task(self, cls, message: dict):
        
        # Check for AccountManager (virtual account updates)
        # We check class name or instance because direct import might lead to circular dependency if not careful,
        # but importing AccountManager is fine here.
        # Check if cls has 'process_order_complete' or similar unique method, or just import it.
        # Let's use string check or import.
        
        is_virtual_manager = hasattr(cls, 'process_order_complete') # Duck typing for AccountManager

        if isinstance(cls, UpbitWebSocket):

            if message["type"] == "ticker":
                market = message['code']
                price = message['trade_price']
                self.price_ob.update(market, price)
                if self.price_ob.is_updated(market):
                    self.on_ticker(message)
                    

            elif message["type"] == "orderbook":
                self.on_orderbook(message)
            elif message["type"] == "trade":
                market = message['code']
                price = message['trade_price']
                self.price_ob.update(market, price)
                if self.price_ob.is_updated(market):
                    self.on_trade(message)
                    
            else:
                raise Exception(f"Unknown message type: {message['type']} from {cls}")
        elif isinstance(cls, UpbitWebSocketPrivate) or is_virtual_manager:

            if message["type"] == "myOrder":
                self.on_my_order(cls, message)
            elif message["type"] == "myAsset":
                self.on_my_asset(cls, message)
            else:
                if is_virtual_manager:
                    # Virtual manager might send other types? For now only myAsset.
                    pass
                else:
                    raise Exception(f"Unknown message type: {message['type']} from {cls}")
        elif isinstance(cls, MessagingClient):
            if message["type"] == "command":
                self.process_command(message["topic"], message["data"])
            else:
                self.dashboard.log(f"Unknown msg type from Messaging: {message['type']}")

        else:
            raise Exception(f"Unknown class: {cls}")

    def process_command(self, topic: str, data: dict):
        """Process commands from Messaging System."""
        try:
            topic = topic.split("/")
            uuid = topic[2]
            action = data.get("action")
            self.dashboard.log(f"Command Received: {action}")
            
            if action == "status":
                # Reply with status
                status = {
                    "running": True,
                    "positions": len(self.position_manager.positions),
                    "timestamp": time.time()
                }
                self.messaging.publish(f"trading/response/{uuid}/status", status)

            elif action == "account":
                # Reply with account balances
                balances = self.account_manager.get_balances()
                # Convert Decimals to serializable format
                serializable_balances = self.Decimal2float(balances)
                self.messaging.publish(f"trading/response/{uuid}/account", serializable_balances)
                self.dashboard.log(f"Account: {serializable_balances}")
                
            elif action == "buy":
                # Implement Buy Logic or delegate
                ticker = data.get("ticker")
                volume = data.get("volume")
                price = data.get("price")
                won = data.get("won")
                
                if price is None:
                     price = self.price_ob.get(ticker)
                     self.dashboard.log(f"Buy Price not specified. Using Current Price: {price}")

                if won and price:
                    volume = Decimal(str(won)) / Decimal(str(price))
                
                self.dashboard.log(f"CMD BUY: {ticker} {volume} @ {price}")
                # TODO: Trigger buy via account/position_manager
                
            elif action == "sell":
                # Implement Sell Logic or delegate
                ticker = data.get("ticker")
                volume = data.get("volume")
                price = data.get("price")
                won = data.get("won")
                
                if price is None:
                     price = self.price_ob.get(ticker)
                     self.dashboard.log(f"Sell Price not specified. Using Current Price: {price}")
                     
                if won and price:
                    volume = Decimal(str(won)) / Decimal(str(price))
                
                self.dashboard.log(f"CMD SELL: {ticker} {volume} @ {price}")
                 # TODO: Trigger sell via account/position_manager
                 
            else:
                self.dashboard.log(f"Unknown Action: {action}")
                
        except Exception as e:
            logger.error(f"Error processing command: {e}")
            self.dashboard.log(f"CMD Error: {e}")
        
    def on_my_order(self, cls, message: dict):
        ticker = message['code']
        ask_bid = message['ask_bid']
        state = message['state']
        entry_price = message.get('price', 0)
        volume = message.get('volume', 0)
        
        krw_volume = volume * entry_price

        self.dashboard.log(f"Order detected {ticker}: {ask_bid}:{state}:{entry_price:.0f} {krw_volume:,.0f}won")
        
        # 새로운 position 생성
        self.position_manager.on_order_fill(message)

        if ask_bid == "bid" and state == "done":
            self._update_positions_dashboard(ticker)
        elif ask_bid == "cancel":
            pass
        else:
            pass

    def on_my_asset(self, cls, message: dict):
        assets = message['assets']
        for asset in assets:
            ticker = asset['currency']
            balance = asset['balance']
            # self.balance is undefined in Manager. Update dashboard instead.
            # Assuming update_balance takes the asset dict.
            self.dashboard.update_balance(asset)
            self.dashboard.log(f"Asset Update: {ticker}: {balance:.4f}")
            

    def on_ticker(self, message: dict):
        ticker = message['code']
        current_price = message['trade_price']

        if not self.price_ob.is_updated(ticker):
            return
        
        # Update Dashboard Ticker Info
        self.dashboard.update_ticker(message=message)
        if self.strategy_manager:
            self.strategy_manager.on_ticker(ticker, current_price)

    def on_orderbook(self, message: dict):
        tiker = Ticker(message.get('code', ''))
        orderbook = message.get('orderbook_units', [])

        self.account_manager.check_order(tiker.ticker, orderbook)

    def on_trade(self, message: dict):
        pass

    def on_order(self, message: dict):
        pass

    def on_asset(self, message: dict):
        pass

    def on_signal(self, position: Position=None, signals: Any=None):
        pass

    def _update_positions_dashboard(self, ticker: str):
        """Update dashboard with current positions for the ticker."""
        positions = self.position_manager.get_positions(ticker, only_active=True)
        pos_data = []
        for p in positions:
            pos_data.append({
                'id': p.id,
                'entry_price': p.entry_price,
                'volume': p.volume,
                'strategies': [] # TODO: Add strategies when available in Position model
            })
        self.dashboard.update_positions(ticker, pos_data)

    # -- Main -------------------------------------
if __name__ == "__main__":
    time_format = "%m-%d %H:%M:%S"
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=logging.DEBUG, filename="logs/coin-stratege.log", filemode="w", format=log_format, datefmt=time_format)

    manager = Manager(virtual=True)
    manager.init()
    try:
        while True:
            manager.run()
    except KeyboardInterrupt:
        manager.stop()


    