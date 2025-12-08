import os
import time
import asyncio
import logging
import pyupbit
import sys

# Add project root to sys.path if not present
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List, Tuple
from dotenv import load_dotenv
from upbit.upbit_websocket import UpbitWebSocket, WebsocketObserver
from account.models import Balance, Asset,initialize_db
import pyupbit

# Use PositionEx instead of base Position
from src.position_manager import PositionEx
from src.stratege_manager import StrategyFactory

# Import models
from models.trade import Trade
from models.orderInfo import OrderInfo
from models.my_asset import MyAsset


logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.expanduser("~"), ".config", "upbit.env"))   

UPBIT_ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY")
UPBIT_SECRET_KEY = os.getenv("UPBIT_SECRET_KEY")

DB_PATH = "account.db"


from collections import deque

class CurrentPrice:
    def __init__(self):
        self.current_price = {}
        self.previous_line= ""
    def update(self, code: str, price: float):
        if code not in self.current_price:
            self.current_price[code] = deque(maxlen=5)
        self.current_price[code].append(price)
    
    def get(self, code: str) -> float:
        if code in self.current_price and self.current_price[code]:
            return self.current_price[code][-1]
        return 0.0
    
    def is_updated(self, code: str) -> bool:
        if code in self.current_price and self.current_price[code]:
            return True
        return False
    
    def get_all(self) -> List[Tuple[str, float]]:
        # Return (code, latest_price) to maintain compatibility
        return [(code, prices[-1]) for code, prices in self.current_price.items() if prices]
    
    def print_all(self):
        line = ""
        for code, prices in self.current_price.items():
            line += f"[{code}:{prices[-1]}]"
        
        for i in range(160 - len(line)):
            line += " "
        
        if self.previous_line != line:
            self.previous_line = line
            print(f"\r{line}", end="")
        
        return



class Manager(WebsocketObserver):
    def __init__(self):

        self.balance = Balance.load(DB_PATH)
        self.tickers = [ asset.ticker for asset in self.balance.assets if asset.currency != "KRW" ]
        self.upbit_websocket = UpbitWebSocket(codes=self.tickers, observer=self)
        self.current_price = CurrentPrice()
        # self.stratege = {ticker: [TrailingStopPolicy(0.05)] for ticker in self.tickers} # Obsolete
        self.positions: List[PositionEx] = []


    def init_position(self):
        # Load existing positions as PositionEx
        # Note: PositionEx.load_all calls Position.load_all logic but instantiates PositionEx
        positions = PositionEx.load_all(DB_PATH)
        for pos in positions:
            self.positions.append(pos)
            logger.info(f"Loaded Position: {pos.ticker} {pos.volume * pos.entry_price:.0f} (Strategies: {len(pos.strategy_manager.strategies)})")
        
        rate_step = 0.25

        # self.positions 에 없는 것만 추가
        for ticker in self.tickers:
            # Check if active position exists for this ticker
            if any(pos.ticker == ticker and not pos.is_closed for pos in self.positions):
                continue
                
            balance = self.balance.get_balance(ticker)
            if balance <= 0:
                continue

            slice = int(1/rate_step)
            entry_price = pyupbit.get_current_price(ticker)
            
            # Divide balance into slices to create multiple positions (simulated)
            for _ in range(slice):
                volume = balance / slice
                if float(volume) * entry_price < 5000: # Min order amount check roughly
                    continue

                pos = PositionEx(ticker=ticker, entry_price=entry_price, volume=volume)
                
                # Add default strategy: Trailing Stop
                pos.add_strategy("trailing_stop", {
                    "trail_percent": 0.05,        # 5% trailing
                    "activation_percent": 0.03    # Activate after 3% profit
                })
                
                self.positions.append(pos)
                pos.save(DB_PATH)
                logger.info(f"Add Position: {pos.ticker} {pos.volume * pos.entry_price:.0f} with TrailingStop")

    def run(self):
        self.init_position()
        self.upbit_websocket.start()

    def stop(self):
        self.upbit_websocket.stop()

    # -- WebSocket Events -------------------------
    def on_ws_opened(self, cls):
        logger.info("WebSocket Opened")

    def on_ws_message(self, cls, message: dict):
        line = ""
        if message["type"] == "ticker":
            self.current_price.update(message['code'], message['trade_price'])
            self.on_ticker(message)
        elif message["type"] == "orderbook":
            
            pass
        elif message["type"] == "trade":
            self.current_price.update(message['code'], message['trade_price'])
            self.on_trade(message)
        elif message["type"] == "myOrder":
            pass
        elif message["type"] == "myAsset":
            pass
        else:
            pass

        self.current_price.print_all()
        
        
        
    def on_ws_closed(self, cls):
        logger.info("WebSocket Closed")

    def on_my_order(self, cls, message: dict):
        pass

    def on_my_asset(self, cls, message: dict):
        pass

    def on_ticker(self, message: dict):
        ticker = message['code']
        current_price = message['trade_price']

        if not self.current_price.is_updated(ticker):
            return
        
        # Check positions for this ticker
        for pos in self.positions:
            if pos.ticker == ticker and not pos.is_closed:
                # Update position price and check mechanisms
                signals = pos.update_price(current_price)
                if signals:
                    for signal in signals:
                        print(f"\n🚨 SIGNAL for {ticker}: {signal.type.value} - {signal.reason}")
                        logger.info(f"\n🚨 SIGNAL for {ticker}: {signal.type.value} - {signal.reason}")
                        # Here you would typically execute the signal (close order etc.)
                        # For now, we just print and maybe close the position object if it's a CLOSE signal
                        
                        if signal.type.value == "close":
                             pos.close(current_price)
                             pos.save(DB_PATH)
                             pos.archive(DB_PATH) # Move to history
                             logger.info(f"   Executed CLOSE. Position archived.")
                             
                        elif signal.type.value == "partial_close":
                            # Handle partial close logic if needed
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
    time_format = "%m-%d %H:%M:%S"
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=logging.DEBUG, filename="coin-stratege.log", filemode="w", format=log_format, datefmt=time_format)
    initialize_db()
    sync_with_upbit() 
    # 
    manager = Manager()
    manager.run()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        manager.stop()


    