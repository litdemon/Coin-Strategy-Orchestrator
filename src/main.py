import os
import time
import logging
import pyupbit
import sys
import json
import traceback
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
from tools.currency_print import Won
from account.manager import AccountDBManager, AccountUpbitManager
from src.dashboard import Dashboard
from src.position_manager import Position, PositionManager
from src.current_price import CurrentPrice
from upbit.upbit_websocket import UpbitWebSocket, WebsocketObserver, UpbitWebSocketPrivate
from strategy.manager import StrategyManager
from strategy.trailingstop import TrailingStopStrategy, TrailingStopConfig
from strategy.models import StrategyContext
import uuid

logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.expanduser("~"), ".config", "upbit.env"))   

UPBIT_ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY")
UPBIT_SECRET_KEY = os.getenv("UPBIT_SECRET_KEY")

DB_PATH = "account.db"

class Manager(WebsocketObserver):
    def __init__(self, virtual: bool = False):

        self.task_queue = Queue()
        self.counter = Counter()
        self.virtual = virtual

    def init(self, config: dict = None):

        self.dashboard = Dashboard() # Initialize Dashboard

        if self.virtual:
            account_config = config.get("account", {}) if config else {}
            self.account_manager = AccountDBManager(callback=self.on_ws_message, config=account_config)
            self.upbit_asset = None
            
            # Initial Funding for Virtual Account
            initial_balance = 0
            if config and "account" in config and "initial_balance" in config["account"]:
                initial_balance = config["account"]["initial_balance"]
                
            if initial_balance > 0:
                # Check current KRW balance
                current_balance = self.account_manager.get_balance("KRW")
                if current_balance == 0:
                    logger.info(f"Initializing Virtual Account with {initial_balance:,.0f} KRW")
                    self.dashboard.log(f"Init Virtual Account: {initial_balance:,.0f} KRW")
                    self.account_manager.manager.add_balance("KRW", Decimal(str(initial_balance)))
        else:
            self.account_manager = AccountUpbitManager(access_key=UPBIT_ACCESS_KEY, secret_key=UPBIT_SECRET_KEY)
            self.upbit_asset = UpbitWebSocketPrivate(access_key=UPBIT_ACCESS_KEY, secret_key=UPBIT_SECRET_KEY, observer=self)

        balances = self.account_manager.get_balances()
        all_tickers = [ Ticker(asset.get("currency")).ticker for asset in balances if asset.get("currency") != "KRW" ]

        # Also get tickers from active orders (Limit/Market orders waiting for execution)
        orders = self.account_manager.get_orders()
        for order in orders :
            self.dashboard.update({'order': order})
            t_code = order.get('market', "") or order.get('code', "")
            ticker = Ticker(t_code)
            if ticker.ticker not in all_tickers:
                all_tickers.append(ticker.ticker)

        self.upbit_websocket = UpbitWebSocket(codes=all_tickers, observer=self)
        
        self.price_ob = CurrentPrice()
        
        # Initialize Messaging System
        # Default Config
        mqtt_config = {
            "broker_type": "mqtt",
            "mqtt": {
                "host": "mqtt.toybox7.net",
                "port": 1883,
                "client_id": f"strategy_manager_{int(time.time())}"
            }
        }
        
        # Override with provided config if available
        if config and "messaging" in config:
             mqtt_config = config["messaging"]
             
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
            self.dashboard.update({'asset': balance})
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
                
                # Create Strategy Context & Config
                context = StrategyContext(
                    strategy_id=str(uuid.uuid4()),
                    ticker=ticker.ticker,
                    budget=balance, 
                    position_id=pos.id
                )
                config = TrailingStopConfig(
                    entry_price=current_price,
                    trail_percent=Decimal("0.02") # Default 2% trailing stop
                )
                
                strategy = TrailingStopStrategy(context=context, config=config)
                self.strategy_manager.add_strategy(strategy)

        # Log loaded positions
        for pos in self.position_manager.positions.values():
            self.dashboard.log(f"Loaded Position: {pos.ticker:<10} {pos.entry_price:<10,.0f} {pos.volume * pos.entry_price:,.0f}")
            self.dashboard.update({'position': pos.model_dump()})
        

    def run(self):
        self.dashboard.start() # Start Dashboard
        self.upbit_websocket.start()
        if self.upbit_asset:
            self.upbit_asset.start()

        logger.info("Manager started")
        is_stop = False
        while not is_stop:
            try:
                task = self.task_queue.get()
                is_stop = self.on_task(**task)
            except Exception as e:
                logger.error(f"Error processing task: {e}")
                # traceback
                
                logger.error(traceback.format_exc())
        logger.info("Task queue is empty")

    def stop(self):
        self.upbit_websocket.stop()
        if self.upbit_asset:
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
            logger.error(f"Invalid message: {payload}")
            logger.error(traceback.format_exc())

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
                serializable_balances = Decimal2float(balances)
                self.messaging.publish(f"trading/response/{uuid}/account", serializable_balances)
                self.dashboard.log(f"Account: {serializable_balances}")
                
            elif action == "buy":
                # Implement Buy Logic or delegate
                ticker = Ticker(data.get("ticker"))
                volume = Decimal(data.get("volume") or Decimal("0"))
                price = Decimal(data.get("price") or Decimal("0"))
                won = Decimal(data.get("won") or Decimal("0"))
                
                # Dynamic Subscription: If new ticker, subscribe to orderbook/ticker updates
                if ticker and ticker.ticker not in self.upbit_websocket.codes:
                    self.dashboard.log(f"Subscribing to new ticker: {ticker.ticker}")
                    self.upbit_websocket.add_subscription([ticker.ticker])
                
                is_market = False
                if price <= 0:
                    is_market = True
                    price = None

                if price is None and not is_market:
                     price = pyupbit.get_current_price(ticker.ticker)
                     self.dashboard.log(f"Buy Price not specified. Using Current Price: {price}")

                if won > 0 and volume <= 0:
                    price = Decimal( pyupbit.get_current_price(ticker.ticker) )
                    fee = Decimal('0.005')
                    volume = (won - won * fee) / price
                
                # Validation: Price and Volume must be positive
                if volume <= 0:
                     self.dashboard.log(f"Invalid Buy Volume: {volume}. Must be positive.")
                     return
                if price <= 0 and not is_market:
                     self.dashboard.log(f"Invalid Buy Price: {price}. Must be positive for Limit Order.")
                     return

                self.dashboard.log(f"CMD BUY: {ticker.ticker} {volume} @ {'Market' if is_market else price}")
                
                # Trigger buy via account_manager
                if is_market:
                    order = self.account_manager.buy_market_order(ticker.ticker, volume)
                else:
                    order = self.account_manager.buy_limit_order(ticker.ticker, price, volume)
                
                self.dashboard.log(f"Order Placed: {order}")
                
            elif action == "sell":
                # Implement Sell Logic or delegate
                ticker = Ticker(data.get("ticker"))
                volume = Decimal(data.get("volume") or Decimal("0"))
                price = Decimal(data.get("price") or Decimal("0"))
                won = Decimal(data.get("won") or Decimal("0"))
                
                is_market = False
                if price <= 0:
                    is_market = True
                    price = None
                
                if price is None and not is_market:
                    price = pyupbit.get_current_price(ticker.ticker)
                     
                if won > 0 and volume <= 0:
                    price = Decimal( pyupbit.get_current_price(ticker.ticker) )
                    fee = Decimal(0.005)
                    volume = (won - won * fee) / price
                
                # Check for "Sell All" (Volume = -1)
                is_sell_all = False
                if volume is not None and float(volume) == -1:
                    is_sell_all = True
                    balance = self.account_manager.get_balance(ticker.ticker)
                    self.dashboard.log(f"Sell All requested. Avail Balance: {balance}")
                    volume = balance
                
                # Validation: Price and Volume must be positive (except Sell All handled above)
                if volume is not None and float(volume) <= 0 and not is_sell_all:
                     self.dashboard.log(f"Invalid Sell Volume: {volume}. Must be positive.")
                     return
                if price is not None and float(price) <= 0 and not is_market:
                     self.dashboard.log(f"Invalid Sell Price: {price}. Must be positive for Limit Order.")
                     return

                self.dashboard.log(f"CMD SELL: {ticker} {volume} @ {'Market' if is_market else price}")
                
                # Trigger sell via account_manager
                if is_market:
                    self.account_manager.sell_market_order(ticker.ticker, volume)
                else:
                    self.account_manager.sell_limit_order(ticker.ticker, price, volume)
                
                if is_sell_all and self.virtual:
                    # Clean up Virtual Account Artifacts
                    self.dashboard.log(f"Cleaning up artifacts for {ticker}...")
                    
                    # 1. Archive Positions
                    positions = self.position_manager.get_positions(ticker)
                    for pos in positions:
                        self.position_manager.archive_position(pos.id)
                        self.dashboard.update({'remove': {'id': pos.id}})
                        self.dashboard.log(f"Archived Position: {pos.id}")
                        
                    # 2. Archive Strategies
                    # Find strategies for this ticker
                    # StrategyManager doesn't have get_strategies_by_ticker method directly exposed cleanly?
                    # iterating self.strategy_manager.strategies
                    to_archive = []
                    for sid, strategy in self.strategy_manager.strategies.items():
                        if strategy.context.ticker == ticker:
                            to_archive.append(sid)
                    
                    for sid in to_archive:
                        self.strategy_manager.archive_strategy(sid)
                        self.dashboard.log(f"Archived Strategy: {sid}")
                        
                    self.dashboard.log(f"Cleanup complete for {ticker}")

            elif action == "cancel":
                uuid = data.get("uuid")
                ticker_str = data.get("ticker")
                
                if ticker_str:
                    # Generic Cancel by Ticker
                    t = Ticker(ticker_str)
                    self.dashboard.log(f"CMD CANCEL ALL: {t.ticker}")
                    # Fetch open orders for this ticker
                    # AccountManager.get_order(ticker) returns list of orders (dict or DTO)
                    orders = self.account_manager.get_order(t.ticker)
                    if not orders:
                         self.dashboard.log(f"No open orders found for {t.ticker}")
                    
                    for order in orders:
                         # Handle Dict vs DTO
                         oid = order.get('uuid') if isinstance(order, dict) else getattr(order, 'uuid', None)
                         if oid:
                             self.account_manager.cancel_order(oid)
                             self.dashboard.log(f"Cancelled {oid}")
                
                elif uuid:
                    self.dashboard.log(f"CMD CANCEL: {uuid}")
                    result = self.account_manager.cancel_order(uuid)
                    if hasattr(result, 'model_dump'):
                         res = result.model_dump()
                    elif isinstance(result, dict):
                         res = result
                    else:
                         res = {}
                         
                    if result:
                        self.dashboard.log(f"Order Cancelled: {res.get('market')} {res.get('side')} {res.get('state')} {res.get('locked')}")
                    else:
                        self.dashboard.log(f"Order Cancel Failed or Not Found: {uuid}")
                 
            else:
                self.dashboard.log(f"Unknown Action: {action}")
                
        except Exception as e:
            logger.error(f"Error processing command: {e}")
            self.dashboard.log(f"CMD Error: {e}")
        
    def on_my_order(self, cls, message: dict):
        ticker = message['code']
        ask_bid = message['ask_bid']
        state = message['state']
        entry_price = Decimal(message.get('price', 0))
        volume = Decimal(message.get('volume', 0))
        
        krw_volume = volume * entry_price

        self.dashboard.log(f"Order🧾 detected {ticker}: {ask_bid}:{state} {Won(entry_price)} {Won(krw_volume)}")
        self.dashboard.update({'order': message})
        
        if ask_bid == "bid" and state == "done":
            # 새로운 position 생성
            pos = self.position_manager.on_order_fill(message)
            if pos:
                self.dashboard.update({'position': pos.model_dump()})
                self.dashboard.log(f"New Position: {pos.ticker} ({pos.id[:8]})")
                
        elif ask_bid == "ask" and state == "done":
            pos = self.position_manager.on_order_fill(message)
            if pos:
                self.dashboard.update({'position': pos.model_dump()})
                self.dashboard.log(f"Position Closed: {pos.ticker} ({pos.id[:8]})")
                
        elif ask_bid == "cancel":
            pass
        else:
            pass
        
        # Sync Asset Dashboard if order done
        if state == 'done':
            # Fetch latest asset info including avg_buy_price
            asset_info = self.account_manager.get_asset_balance(ticker)
            if asset_info and asset_info.get('balance'):
                 self.dashboard.update({'asset': asset_info})
                 self.dashboard.log(f"Synced Asset for {ticker}: {asset_info['balance']} @ {asset_info['avg_buy_price']}")
            elif asset_info: # Balance 0 case
                 self.dashboard.update({'asset': asset_info})
                 self.dashboard.log(f"Synced Asset for {ticker}: Balance Zero")
                 
                 # Cleanup Logic: If balance is 0, archive all positions and remove from dashboard
                 balance = Decimal(str(asset_info.get('balance', 0)))
                 if balance <= 0:
                      self.dashboard.log(f"Balance Zero for {ticker}. Cleaning up all positions.")
                      positions = self.position_manager.get_positions(ticker, only_active=False)
                      for pos in positions:
                           self.position_manager.archive_position(pos.id)
                           self.dashboard.update({'remove': {'id': pos.id}})
                           self.dashboard.log(f"Archived & Removed Position: {pos.id}")

    def on_my_asset(self, cls, message: dict):
        logger.info(f"Asset Update: {json.dumps(message, indent=4, default=str)}")

        # Order 정보를 보고 asset을 업데이트 할 예정
        assets = message['assets']
        for asset in assets:
            ticker = Ticker(asset['currency'])
            balance = asset['balance']
            if ticker == "KRW":
                self.dashboard.update({'asset': asset})
            else:
                 self.dashboard.update({'asset': asset})
            self.dashboard.log(f"Asset Update: {ticker.amount(balance)} by myAsset")
            

    def on_ticker(self, message: dict):
        ticker = message['code']
        current_price = message['trade_price']

        if not self.price_ob.is_updated(ticker):
            return
        
        # Update Dashboard Ticker Info
        self.dashboard.update({'ticker': message})
        # TODO: Strategy Manager
        # if self.strategy_manager:
        #     self.strategy_manager.on_ticker(ticker, current_price)

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

    # -- Main -------------------------------------
if __name__ == "__main__":
    time_format = "%m-%d %H:%M:%S"
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=logging.INFO, filename="logs/coin-stratege.log", filemode="w", format=log_format, datefmt=time_format)

    manager = Manager(virtual=True)
    
    # Default Configuration
    config = {
        "messaging": {
            "broker_type": "mqtt",
            "mqtt": {
                "host": "mqtt.toybox7.net",
                "port": 1883,
                "client_id": f"strategy_manager_{int(time.time())}"
            }
        },
        "account": {
            "initial_balance": 10000000,
            "fees": {
                "KRW": 0.0005  # 0.05%
            }
        }
    }
    
    manager.init(config=config)
    try:
        while True:
            manager.run()
    except KeyboardInterrupt:
        manager.stop()
