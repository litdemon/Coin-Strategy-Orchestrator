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
from src.position_manager import PositionEx, PositionManager
from src.stratege_manager import StrategyFactory
from src.order_manager import OrderInfoEx

# Import models
from models.trade import Trade
from models.orderInfo import OrderInfo
from models.my_asset import MyAsset
from strategy.base import SignalType, Signal
from tools.candle import Candle
from tools.ticker import TickerStr

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
        self.tickers = [ TickerStr(key).ticker for key in self.balance.assets.keys() if key != "KRW" ]
        self.upbit_websocket = UpbitWebSocket(codes=self.tickers, observer=self)
        self.upbit_asset = UpbitWebSocketPrivate(access_key=UPBIT_ACCESS_KEY, secret_key=UPBIT_SECRET_KEY, observer=self)
        self.current_price = CurrentPrice()
        # self.stratege = {ticker: [TrailingStopPolicy(0.05)] for ticker in self.tickers} # Obsolete
        self.position_manager = PositionManager(db_path=DB_PATH)
        self.orders: OrderManager = OrderManager(on_order_complete=self.on_my_order, db_path=DB_PATH)


    def init_position(self):
        # Delegate to PositionManager
        self.position_manager.register_positions_from_balance(balance_model=self.balance, tickers=self.tickers)
        
        # Log loaded positions
        for pos in self.position_manager.positions:
            self.dashboard.log(f"Loaded Position: {pos.ticker:<10} {pos.entry_price:<10,.0f} {pos.volume * pos.entry_price:,.0f}")
        
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
            
        for pos in self.position_manager.positions:
            if not pos.is_closed:
                if pos.ticker not in ticker_map:
                    ticker_map[pos.ticker] = []
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
        ask_bid = message['ask_bid']
        state = message['state']
        entry_price = message.get('price', 0)
        volume = message.get('volume', 0)
        
        krw_volume = volume * entry_price

        self.dashboard.log(f"Order detected {ticker}: {ask_bid}:{state}:{entry_price:.0f} {krw_volume:,.0f}won")
        
        # 새로운 position 생성
        self.position_manager.on_order_fill(message)


        
        if ask_bid == "bid" and state == "done":
            #계좌의 평균 매입 가격 업데이트
            
            # Logic moved to Manager, just refresh dashboard
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

        if not self.current_price.is_updated(ticker):
            return
        
        # Check orders
        self.orders.check_execution(self.current_price)

        # Update Dashboard Ticker Info
        candle = self.current_price.candles[ticker]
        candle_str = candle.render()
        self.dashboard.update_ticker(ticker, current_price, candle_str)
        
        # Delegate position updates to manager
        updated = self.position_manager.update_all(self.current_price, self.on_signal)
        
        if updated:
            self._update_all_positions_dashboard()
        
        # For responsiveness
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
    # sync_with_upbit() 
    # 
    manager = Manager()
    manager.run()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        manager.stop()


    