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
from upbit.upbit_websocket import UpbitWebSocket, WebsocketObserver, UpbitWebSocketPrivate
from account.models import Balance, Asset
import pyupbit

# Use PositionEx instead of base Position
from src.position_manager import PositionEx
from src.stratege_manager import StrategyFactory

# Import models
from models.trade import Trade
from models.orderInfo import OrderInfo
from models.my_asset import MyAsset
from strategy.base import SignalType, Signal
from tools.candle import Candle

logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.expanduser("~"), ".config", "upbit.env"))   

UPBIT_ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY")
UPBIT_SECRET_KEY = os.getenv("UPBIT_SECRET_KEY")

DB_PATH = "account.db"


class CurrentPrice:
    def __init__(self):
        self.candles = {}
        self.previous_line= ""

    def update(self, code: str, price: float):
        if code not in self.candles:
             self.candles[code] = Candle(code, price)
        else:
             self.candles[code].update(price)

    def get(self, code: str) -> float:
        if code in self.candles:
            return self.candles[code].close
        return 0.0
    
    def is_updated(self, code: str) -> bool:
        return code in self.candles
    
    def get_all(self) -> List[Tuple[str, float]]:
        # Return (code, latest_price) to maintain compatibility
        return [(code, candle.close) for code, candle in self.candles.items()]
    
    def print_all(self):
        line = ""
        # Sort or fixed order might be better, but dict iteration fine for now
        # Format: [CODE: PRICE CANDLE]
        
        for code, candle in self.candles.items():
            candle_str = candle.render(width=15)
            line += f"[{code}: {candle.close:.0f} {candle_str}] "
        
        # Clear line padding
        padding = max(0, 160 - len(line)) # arbitrary wide buffer
        
        if self.previous_line != line:
            self.previous_line = line
            # \r to overwrite line
            # Need to handle terminal width if too long, but simple for now
            # ANSI codes count in len(line) but don't show, so visual length is shorter.
            # Just print raw.
            print(f"\r{line}", end="")
            
        return



class Manager(WebsocketObserver):
    def __init__(self):

        self.balance = Balance.load(DB_PATH)
        self.tickers = [ asset.ticker for asset in self.balance.assets if asset.currency != "KRW" ]
        self.upbit_websocket = UpbitWebSocket(codes=self.tickers, observer=self)
        self.upbit_asset = UpbitWebSocketPrivate(access_key=UPBIT_ACCESS_KEY, secret_key=UPBIT_SECRET_KEY, observer=self)
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

            entry_price = pyupbit.get_current_price(ticker)
            
            volume = float(balance) / rate_step
            if volume * entry_price < 5000: # Min order amount check roughly
                continue

            pos = PositionEx(ticker=ticker, entry_price=entry_price, volume=volume)
            
            # Add default strategy: Trailing Stop
            pos.add_strategy("trailing_stop", {
                "trail_percent": 0.05,        # 5% trailing
                "activation_percent": 0.01    # Activate after 1% profit
            })
            
            self.positions.append(pos)
            pos.save(DB_PATH)
            logger.info(f"Add Position: {pos.ticker} {pos.volume * pos.entry_price:.0f} with TrailingStop")

    def run(self):
        self.init_position()
        self.upbit_websocket.start()
        self.upbit_asset.start()

    def stop(self):
        self.upbit_websocket.stop()

    # -- WebSocket Events -------------------------
    def on_ws_opened(self, cls):
        logger.info("WebSocket Opened")

    def on_ws_closed(self, cls):
        logger.info("WebSocket Closed")

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
            self.on_my_order(cls, message)
        elif message["type"] == "myAsset":
            self.on_my_asset(cls, message)
        else:
            pass

        self.current_price.print_all()
        
    def on_my_order(self, cls, message: dict):
        ticker = message['code']
        order_type = message['order_type']
        ask_bid = message['ask_bid']
        state = message['state']
        volume = message['volume']
        entry_price = message['price']

        krw_volume = volume * entry_price

        print(f"\n👩 Order detected {ticker}: {ask_bid}:{state}:{entry_price:.0f} {krw_volume:.0f}won ")
        if ask_bid == "ask":
            if state == "done":
                pass
        elif ask_bid == "bid":
            if state == "done":
                pos = PositionEx(ticker=ticker, entry_price=entry_price, volume=volume)    
                pos.add_strategy("trailing_stop", {
                    "trail_percent": 0.05,        # 5% trailing
                    "activation_percent": 0.01    # Activate after 1% profit
                })
                self.positions.append(pos)
                pos.save(DB_PATH)
                logger.info(f"Add Position: {pos.ticker} {pos.volume * pos.entry_price:.0f} with TrailingStop")
        elif ask_bid == "cancel":
            pass
        else:
            pass

    def on_my_asset(self, cls, message: dict):
        ticker = message['code']
        balance = message['balance']
        print(f"\n👩‍💻 Asset Update: {ticker}: {balance:.0f}")

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
                    self.on_signal(pos, signals)
                    

    def on_orderbook(self, message: dict):
        pass

    def on_trade(self, message: dict):
        pass

    def on_order(self, message: dict):
        pass

    def on_asset(self, message: dict):
        pass

    def on_signal(self, position: PositionEx, signals: List[Signal]):
        for signal in signals:
            print(f"\n🚨 SIGNAL for {position.ticker}: {signal.type.value} - {signal.reason}")
            logger.info(f"\n🚨 SIGNAL for {position.ticker}: {signal.type.value} - {signal.reason}")
            
            if signal.type.value == "close":
                position.close(self.current_price.get_price(position.ticker))
                position.save(DB_PATH)
                position.archive(DB_PATH) # Move to history
                logger.info(f"   Executed CLOSE. Position archived.")
                
            elif signal.type.value == "partial_close":
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
    logging.basicConfig(level=logging.DEBUG, filename="logs/coin-stratege.log", filemode="w", format=log_format, datefmt=time_format)
    PositionEx.initialize_db()
    # sync_with_upbit() 
    # 
    manager = Manager()
    manager.run()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        manager.stop()


    