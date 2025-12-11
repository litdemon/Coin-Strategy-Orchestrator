import os
import time
import logging
import pyupbit
import sys
from decimal import Decimal

# Add project root to sys.path if not present
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List, Tuple
from dotenv import load_dotenv
from upbit.upbit_websocket import UpbitWebSocket, WebsocketObserver, UpbitWebSocketPrivate

import pyupbit

# Use Position instead of base Position
from src.position_manager import Position, PositionManager
from src.stratege_manager import StrategyFactory

# Import models
from models.trade import Trade
from models.orderInfo import OrderInfo
from models.my_asset import MyAsset
from strategy.base import SignalType, Signal
from tools.ticker import Ticker
from tools.counter import Counter
from account.account import Account
from queue import Queue

logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.expanduser("~"), ".config", "upbit.env"))   

UPBIT_ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY")
UPBIT_SECRET_KEY = os.getenv("UPBIT_SECRET_KEY")

DB_PATH = "account.db"

from src.dashboard import Dashboard
from src.current_price import CurrentPrice
from account.account import AccountUpbit, Account


class Manager(WebsocketObserver):
    def __init__(self, virtual: bool = False):
        self.dashboard = Dashboard() # Initialize Dashboard

        if virtual:
            self.account = Account(callback=self.on_ws_message)
        else:
            self.account = AccountUpbit(access_key=UPBIT_ACCESS_KEY, secret_key=UPBIT_SECRET_KEY)
        self.task_queue = Queue()
        self.counter = Counter()

    def init(self):
        balances = self.account.get_balances()
        tickers = [ Ticker(asset.get("currency")) for asset in balances if asset.get("currency") != "KRW" ]

        self.upbit_websocket = UpbitWebSocket(codes=[ticker.ticker for ticker in tickers], observer=self)
        self.upbit_asset = UpbitWebSocketPrivate(access_key=UPBIT_ACCESS_KEY, secret_key=UPBIT_SECRET_KEY, observer=self)
        self.price_ob = CurrentPrice()
        

        self.position_manager = PositionManager(db_path=DB_PATH)
        for balance in balances:
            ticker = Ticker(balance.get("currency"))
            self.dashboard.update_balance(balance)
            if ticker.currency == "KRW":
                continue

            # position이 없으면 default position 생성   
            if self.position_manager.get_positions(ticker.ticker, only_active=True):
                continue
            
            current_price = pyupbit.get_current_price(ticker.ticker)
            balance = Decimal(balance.get("balance")) * Decimal(0.25)
            pos = self.position_manager.create_position(
                                        ticker=ticker.ticker, 
                                        entry_price=current_price, 
                                        volume=balance)
            # position에 strategy 추가
            # pos.add_strategy(TrailingStopPolicy(0.05))
            

        # Log loaded positions
        for pos in self.position_manager.positions.values():
            # self.dashboard.update_positions(pos)
            self.dashboard.log(f"Loaded Position: {pos.ticker:<10} {pos.entry_price:<10,.0f} {pos.volume * pos.entry_price:,.0f}")
        
        

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
        self.dashboard.stop()

    # -- WebSocket Events -------------------------
    def on_ws_opened(self, cls):
        self.dashboard.log("WebSocket Opened")

    def on_ws_closed(self, cls):
        self.dashboard.log("WebSocket Closed")

    def on_ws_message(self, cls, message: dict):
        self.task_queue.put({"cls": cls, "message": message})   

    def on_task(self, cls, message: dict):
        
        if isinstance(cls, UpbitWebSocket):

            if message["type"] == "ticker":
                self.price_ob.update(message['code'], message['trade_price'])
                if self.price_ob.is_updated(message['code']):
                    self.on_ticker(message)
            elif message["type"] == "orderbook":
                self.on_orderbook(message)
            elif message["type"] == "trade":
                self.price_ob.update(message['code'], message['trade_price'])
                if self.price_ob.is_updated(message['code']):
                    self.on_trade(message)
            else:
                raise Exception(f"Unknown message type: {message['type']} from {cls}")
        elif isinstance(cls, UpbitWebSocketPrivate):

            if message["type"] == "myOrder":
                self.on_my_order(cls, message)
            elif message["type"] == "myAsset":
                self.on_my_asset(cls, message)
            else:
                raise Exception(f"Unknown message type: {message['type']} from {cls}")
        else:
            raise Exception(f"Unknown class: {cls}")
        
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
            self._update_all_positions_dashboard()
        elif ask_bid == "cancel":
            pass
        else:
            pass

    def on_my_asset(self, cls, message: dict):
        assets = message['assets']
        for asset in assets:
            ticker = asset['currency']
            balance = asset['balance']
            self.balance.set_balance(ticker, balance)
            self.dashboard.log(f"Asset Update: {ticker}: {balance:.0f}")
            

    def on_ticker(self, message: dict):
        ticker = message['code']
        current_price = message['trade_price']

        if not self.price_ob.is_updated(ticker):
            return
        
        # Update Dashboard Ticker Info
        self.dashboard.update_ticker(message=message)

    def on_orderbook(self, message: dict):
        tiker = Ticker(message.get('code', ''))
        orderbook = message.get('orderbook_units', [])

        self.account.check_order(tiker.ticker, orderbook)

    def on_trade(self, message: dict):
        pass

    def on_order(self, message: dict):
        pass

    def on_asset(self, message: dict):
        pass

    def on_signal(self, position: Position, signals: List[Signal]):
        for signal in signals:
            self.dashboard.log(f"SIGNAL {position.ticker}: {signal.type.value} - {signal.reason}")


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


    