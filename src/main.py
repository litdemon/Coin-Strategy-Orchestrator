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
from src.order_manager import OrderInfoEx

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



from src.dashboard import Dashboard
from src.current_price import CurrentPrice
from src.order_manager import OrderManager

class Manager(WebsocketObserver):
    def __init__(self):
        self.dashboard = Dashboard() # Initialize Dashboard

        self.balance = Balance.load(DB_PATH)
        self.tickers = [ asset.ticker for asset in self.balance.assets if asset.currency != "KRW" ]
        self.upbit_websocket = UpbitWebSocket(codes=self.tickers, observer=self)
        self.upbit_asset = UpbitWebSocketPrivate(access_key=UPBIT_ACCESS_KEY, secret_key=UPBIT_SECRET_KEY, observer=self)
        self.current_price = CurrentPrice()
        # self.stratege = {ticker: [TrailingStopPolicy(0.05)] for ticker in self.tickers} # Obsolete
        self.positions: List[PositionEx] = []
        self.orders: OrderManager = OrderManager(on_order_complete=self.on_my_order, db_path=DB_PATH)


    def init_position(self):
        positions = PositionEx.load_all(DB_PATH)
        for pos in positions:
            self.positions.append(pos)
            self.dashboard.log(f"Loaded Position: {pos.ticker:<10} {pos.entry_price:<10,.0f} {pos.volume * pos.entry_price:,.0f}")
        
        default_rate = 0.25  # 25%

        # self.positions 에 없는 것만 추가
        for ticker in self.tickers:
            # Check if active position exists for this ticker
            if any(pos.ticker == ticker and not pos.is_closed for pos in self.positions):
                continue
                
            balance = self.balance.get_balance(ticker)
            if balance <= 0:
                continue

            entry_price = pyupbit.get_current_price(ticker)
            
            volume = float(balance) * default_rate
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
            self.dashboard.log(f"Add Position: {pos.ticker} {pos.volume * pos.entry_price:,.0f} with TrailingStop")
        
        self._update_all_positions_dashboard()

    def run(self):
        self.dashboard.start() # Start Dashboard
        self.init_position()
        self.upbit_websocket.start()
        self.upbit_asset.start()

    def stop(self):
        self.upbit_websocket.stop()
        self.upbit_asset.stop()
        self.dashboard.stop()

    def _update_all_positions_dashboard(self):
        # Group positions by ticker
        ticker_map = {}
        for ticker in self.tickers:
            ticker_map[ticker] = []
            
        for pos in self.positions:
            if not pos.is_closed:
                ticker_map[pos.ticker].append(pos)
        
        for ticker, positions in ticker_map.items():
            summaries = []
            for pos in positions:
                # Format: "StrategyType(Status) | Vol: ..."
                strategies = []
                for s in pos.strategy_manager.strategies:
                    strategies.append(f"{s.config.strategy_type}")
                
                strategy_str = ", ".join(strategies)
                profit_rate = (self.current_price.get(ticker) - pos.entry_price) / pos.entry_price * 100
                if profit_rate < 0:
                    profit_rate_str = f"\033[34m{profit_rate:.2f}%\033[0m"
                else:
                    profit_rate_str = f"\033[31m+{profit_rate:.2f}%\033[0m"

                volume = pos.volume * pos.entry_price
                summaries.append(f"ID:{pos.id[:4]}.. | {strategy_str} | PnL: {profit_rate_str} | Vol: {volume:,.0f}")
            
            self.dashboard.update_positions(ticker, summaries)

    # -- WebSocket Events -------------------------
    def on_ws_opened(self, cls):
        self.dashboard.log("WebSocket Opened")

    def on_ws_closed(self, cls):
        self.dashboard.log("WebSocket Closed")

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
        
    def on_my_order(self, cls, message: dict):
        ticker = message['code']
        order_type = message['order_type']
        ask_bid = message['ask_bid']
        state = message['state']
        volume = message['volume']
        entry_price = message['price']

        krw_volume = volume * entry_price

        self.dashboard.log(f"Order detected {ticker}: {ask_bid}:{state}:{entry_price:.0f} {krw_volume:,.0f}won")
        
        if ask_bid == "bid" and state == "done":
            pos = PositionEx(ticker=ticker, entry_price=entry_price, volume=volume)    
            pos.add_strategy("trailing_stop", {
                "trail_percent": 0.05,        # 5% trailing
                "activation_percent": 0.01    # Activate after 1% profit
            })
            self.positions.append(pos)
            pos.save(DB_PATH)
            self.dashboard.log(f"Add Position: {pos.ticker}")
            self._update_all_positions_dashboard()
        elif ask_bid == "cancel":
            pass
        else:
            pass

    def on_my_asset(self, cls, message: dict):
        assets = message['assets']
        for asset in assets:
            ticker = asset['code']
            balance = asset['balance']
            self.balance.set_balance(ticker, balance)
            self.dashboard.log(f"Asset Update: {ticker}: {balance:.0f}")

    def on_ticker(self, message: dict):
        ticker = message['code']
        current_price = message['trade_price']

        if not self.current_price.is_updated(ticker):
            return
        
        # Check orders
        self.orders.check_execution(self.current_price)

        # Update Dashboard Ticker Info
        candle = self.current_price.candles[ticker]
        candle_str = candle.render()
        self.dashboard.update_ticker(ticker, current_price, candle_str)
        
        # Check positions for this ticker
        active_positions_count = 0
        updated = False
        
        for pos in self.positions:
            if pos.ticker == ticker and not pos.is_closed:
                active_positions_count += 1
                # Update position price and check mechanisms
                signals = pos.update_price(current_price)
                if signals:
                    self.on_signal(pos, signals)
                    updated = True
        
        # If signals occurred, refresh positions list on dashboard
        if updated:
            self._update_all_positions_dashboard()
        
        # Optimization: We could update PnL on every ticker, 
        # but maybe throttle it or do it every X seconds.
        # For now, let's update position PnL on every ticker tick for responsiveness
        self._update_all_positions_dashboard()
                    

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
            self.dashboard.log(f"SIGNAL {position.ticker}: {signal.type.value} - {signal.reason}")
            
            if signal.type.value == "close":
                position.close(self.current_price.get(position.ticker))
                position.save(DB_PATH)
                position.archive(DB_PATH) # Move to history
                self.dashboard.log(f"Executed CLOSE. Position archived.")
                
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
    Asset.initialize_db()
    OrderInfoEx.initialize_db()
    sync_with_upbit() 
    # 
    manager = Manager()
    manager.run()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        manager.stop()


    