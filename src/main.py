import os
import time
import asyncio
import logging
import pyupbit
from typing import List, Tuple
from dotenv import load_dotenv
from upbit.upbit_websocket import UpbitWebSocket, WebsocketObserver
from account.models import Balance, Asset,initialize_db
import pyupbit
from models.position import Position
from models.trade import Trade
from models.orderInfo import OrderInfo
from models.my_asset import MyAsset

from stratege.tailingstop import TrailingStopPolicy

logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.expanduser("~"), ".config", "upbit.env"))   

UPBIT_ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY")
UPBIT_SECRET_KEY = os.getenv("UPBIT_SECRET_KEY")

DB_PATH = "assets.db"


class CurrentPrice:
    def __init__(self):
        self.current_price = {}
    
    def update(self, code: str, price: float):
        self.current_price[code] = price
    
    def get(self, code: str) -> float:
        return self.current_price.get(code, 0)
    
    def get_all(self) -> List[Tuple[str, float]]:
        return self.current_price.items()

class Manager(WebsocketObserver):
    def __init__(self):

        self.balance = Balance.load(DB_PATH)
        self.tickers = [ asset.ticker for asset in self.balance.assets if asset.currency != "KRW" ]
        self.upbit_websocket = UpbitWebSocket(codes=self.tickers, observer=self)
        self.current_price = CurrentPrice()
        self.stratege = {ticker: [TrailingStopPolicy(0.05)] for ticker in self.tickers}
        self.positions = []


    def init_position(self):
        rate_step = 0.2
        for ticker in self.tickers:
            balance = self.balance.get_balance(ticker)
            slice = int(1/rate_step)
            entry_price = pyupbit.get_current_price(ticker)
            for _ in range(slice):
                pos = Position(ticker=ticker, entry_price=entry_price, volume=balance/slice)
                self.positions.append(pos)
                logger.info(f"Add Position: {pos.ticker} {pos.volume * pos.entry_price:.0f}")

    def run(self):
        self.init_position()
        self.upbit_websocket.start()

    def stop(self):
        self.upbit_websocket.stop()

    # -- WebSocket Events -------------------------
    def on_ws_opened(self, cls):
        print("WebSocket Opened")

    def on_ws_message(self, cls, message: dict):
        line = ""
        if message["type"] == "ticker":
            self.current_price.update(message['code'], message['trade_price'])
            self.on_ticker(message)
        elif message["type"] == "orderbook":
            # print("Orderbook Message: ", message)
            pass
        elif message["type"] == "trade":
            self.current_price.update(message['code'], message['trade_price'])
            self.on_trade(message)
        elif message["type"] == "myOrder":
            # print("MyOrder Message: ", message)
            pass
        elif message["type"] == "myAsset":
            # self.balance = Balance.load(DB_PATH)
            # print("MyAsset Message: ", message)
            pass
        else:
             pass

        for code, price in self.current_price.get_all():
            line += f"[{code}:{price}]"
        
        if len(line) < 42:
            print(f"\r{line}{' '*80}", end='')
        else:
            print(f"\r{line}{' '*80}")
        
    def on_ws_closed(self, cls):
        print("WebSocket Closed")

    def on_my_order(self, cls, message: dict):
        pass

    def on_my_asset(self, cls, message: dict):
        pass

    def on_ticker(self, message: dict):
        pass

    def on_orderbook(self, message: dict):
        pass

    def on_trade(self, message: dict):
        pass

    def on_order(self, message: dict):
        pass

    def on_asset(self, message: dict):
        pass



def sync_with_upbit():
    
    balance = Balance.load(DB_PATH)
    upbit = pyupbit.Upbit(UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY)
    assets = upbit.get_balances()
    balance.assets = []
    for asset in assets:
        balance.assets.append(Asset(**asset))

    
    balance.save(DB_PATH)


    # -- Main -------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    initialize_db()
    # sync_with_upbit() 
    # 
    manager = Manager()
    manager.run()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        manager.stop()


    