import os
import time
import logging
import pyupbit
import sys
import json
import traceback
import threading
import asyncio
from decimal import Decimal

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super(DecimalEncoder, self).default(obj)

# Add project root to sys.path if not present
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List, Tuple, Any
from dotenv import load_dotenv

import pyupbit
import pyupbit
from queue import Queue, Empty

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
from account.dbupbit import DBUpbit
from src.dashboard import Dashboard
from src.pocket_manager import Pocket, PocketManager, PocketObserver, PocketStateType
from src.current_price import CurrentPrice
from upbit.upbit_websocket import UpbitWebSocket, WebsocketObserver, UpbitWebSocketPrivate
from strategy.manager import StrategyManager, StrategyObserver, StrategyBase
from strategy.models import StrategyContext, StrategyConfig, StrategyDTO, StrategyStatus, Signal, SignalType, StrategyType
from strategy.buy_strategy import ScalpingStrategy, ScalpingStrategyConfig
from strategy.default_strategy import DefaultStrategy, DefaultStrategyConfig
from strategy.volume_strategy import VolumeSpikeStrategy, VolumeSpikeStrategyConfig
import uuid

logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.expanduser("~"), ".config", "upbit.env"))   

UPBIT_ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY")
UPBIT_SECRET_KEY = os.getenv("UPBIT_SECRET_KEY")

DB_PATH = "account.db"

class Task:
    def __init__(self, cls, message):
        self.cls = cls
        self.message = message

class Manager(WebsocketObserver, StrategyObserver, PocketObserver):
    def __init__(self, virtual: bool = False):

        self.task_queue = Queue()
        self.counter = Counter()
        self.virtual = virtual
        self.orders = {}
        self.current_prices = CurrentPrice()

    def init_strategy(self):
        self.strategy_manager = StrategyManager(db_path=DB_PATH, observer=self)
        self.strategy_manager.register_strategy("default", DefaultStrategy)
        self.strategy_manager.register_strategy("scalping_strategy", ScalpingStrategy)
        self.strategy_manager.register_strategy("volume_spike_strategy", VolumeSpikeStrategy)

        self.strategy_manager.load_strategies()

    def init_pockets(self):
        self.pocket_manager = PocketManager(db_path=DB_PATH, observer=self)
        self.pocket_manager.init()
                
    def init_account(self, config: dict = None):
        if self.virtual:
            account_config = config.get("account", {}) if config else {}
            self.account_manager = AccountDBManager(callback=self.on_ws_message, config=account_config)
            self.upbit_asset = None
            
        else:
            self.account_manager = AccountUpbitManager(access_key=UPBIT_ACCESS_KEY, secret_key=UPBIT_SECRET_KEY)
            self.upbit_asset = UpbitWebSocketPrivate(access_key=UPBIT_ACCESS_KEY, secret_key=UPBIT_SECRET_KEY, observer=self)
        self.account_manager.init()

        tickers = []
        balances = self.account_manager.get_balances()
        for asset in balances :
            if asset['currency'] != 'KRW' :
                tickers.append(Ticker(asset['currency']).ticker)
            self.on_asset_created(asset)
        
        # Also get tickers from active orders (Limit/Market orders waiting for execution)
        orders = self.account_manager.get_orders()
        for order in orders :
            if order['market'] != 'KRW' :
                tickers.append(order['market'])
                self.on_order_created(order)
        return tickers

    def init(self, config: dict = None):

        self.dashboard = Dashboard() # Initialize Dashboard

        tickers = self.init_account(config)
            
        self.upbit_websocket = UpbitWebSocket(codes=list(set(tickers)), observer=self)
        
        # Override with provided config if available
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
        self.init_strategy()

        # Initialize Pocket Manager - Pocket needs to be initialized after strategy
        self.init_pockets()

        for strategy in self.strategy_manager.strategies.values():
            if strategy.context.pocket_id:
                if strategy.context.pocket_id in self.pocket_manager.pockets:
                     logger.debug(f"Strategy {strategy.context.strategy_id} is active (Pocket {strategy.context.pocket_id})")
                     self.dashboard.update({'strategy': strategy.summary()})
            else:
                 # Independent Strategy (e.g. Buy Strategy)
                 logger.debug(f"Strategy {strategy.context.strategy_id} is active (Independent)")
                 self.dashboard.update({'strategy': strategy.summary()})

    def _run_scheduler_loop(self):
        """Thread loop for checking strategy schedules."""
        logger.info("Scheduler thread started")
        while not self.stop_event.is_set():
            try:
                if self.strategy_manager:
                    # Strategy Manager iteration is now thread-safe (iterates copy)
                    self.strategy_manager.on_schedule()
                    logger.info("Scheduler thread running")
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                logger.error(traceback.format_exc())
            
            # Wait for 60 seconds or until stopped
            if self.stop_event.wait(60):
                break
        logger.info("Scheduler thread stopped")

    def run(self):
        self.dashboard.start() # Start Dashboard
        self.upbit_websocket.start()
        if self.upbit_asset:
            self.upbit_asset.start()
        
        # Initialize Stop Event
        self.stop_event = threading.Event()
        
        # Start Pipeline Thread
        if hasattr(self, '_run_pipeline_loop'):
            self.pipeline_thread = threading.Thread(target=self._run_pipeline_loop, daemon=True)
            self.pipeline_thread.start()
        
        # Start Scheduler Thread
        self.scheduler_thread = threading.Thread(target=self._run_scheduler_loop, daemon=True)
        self.scheduler_thread.start()

        logger.info("Manager started")
        
        # Main Loop - Process Tasks
        is_stop = False
        while not is_stop:
            try:
                # Block until task available (no timeout needed if we have separate scheduler)
                # But keep timeout=1 to allow checking 'is_stop' or handling interrupts if needed?
                # Actually, if we use stop_event, we can just block?
                # 'task_queue.get()' blocks indefinitely.
                # If we want to exit loop on stop(), we need to unblock get().
                # Typically we put a sentinel 'EXIT' task or use timeout.
                # Using timeout=1 is safer to check 'self.stop_event' periodically if logic changes.
                task = self.task_queue.get(timeout=1)
                is_stop = self.on_task(task)
            except Empty:
                pass # Just continue loop
            except Exception as e:
                logger.error(f"Error processing task: {e}")
                logging.error(traceback.format_exc())
                
        logger.debug("Task queue loop finished")
        
        # If loop finished via is_stop (Task), make sure to stop everything
        if is_stop:
             self.stop()

    def stop(self):
        logger.info("Stopping Manager...")
        if hasattr(self, 'stop_event'):
            self.stop_event.set()
            
        self.upbit_websocket.stop()
        if self.upbit_asset:
            self.upbit_asset.stop()
        if self.messaging:
            self.messaging.disconnect()
        self.dashboard.stop()
        
        # Stop Pipeline (Async)
        if hasattr(self, 'pipeline_manager') and hasattr(self, '_pipeline_loop'):
            asyncio.run_coroutine_threadsafe(self.pipeline_manager.stop(), self._pipeline_loop)
            if hasattr(self, 'pipeline_thread'):
                self.pipeline_thread.join(timeout=1)
        
        # Stop Scheduler
        if hasattr(self, 'scheduler_thread'):
            self.scheduler_thread.join(timeout=1)
            
        logger.info("Manager stopped")

    # -- Pocket Events -------------------------
    def on_pocket_loaded(self, pocket: Pocket):
        self.dashboard.log(f"Loaded Pocket: {pocket.ticker:<10} {pocket.entry_price:<10,.0f} {pocket.volume * pocket.entry_price:,.0f}")
        self.dashboard.update({'pocket': pocket.model_dump()})
    
    def on_pocket_created(self, pocket: Pocket):
        self.dashboard.log(f"Created Pocket: {pocket.ticker:<10} {pocket.entry_price:<10,.0f} {pocket.volume * pocket.entry_price:,.0f}")
        self.dashboard.update({'pocket': pocket.model_dump()})

        # Default Strategy Creation
        context = StrategyContext(
            strategy_id=str(uuid.uuid4()),
            ticker=pocket.ticker,
            budget=pocket.volume, 
            pocket_id=pocket.id
        )
        config = DefaultStrategyConfig(
            entry_price=pocket.entry_price,
            trail_percent=Decimal("0.02"),
            stop_loss_percent=Decimal("0.02"),
            take_profit_percent=Decimal("0.05")
        )
        
        strategy = DefaultStrategy(context=context, config=config)
        self.strategy_manager.add_strategy(strategy)

    def on_pocket_updated(self, pocket: Pocket):
        ticker = Ticker(pocket.ticker)
        self.dashboard.update({'pocket': pocket.model_dump()})

        if pocket.status == PocketStateType.CLOSING:
            self.dashboard.log(f"Pocket Closing: {pocket.ticker} ({pocket.id[:8]})")
            
            if not pocket.close_order_id:
                # 1. Create Order
                order = self.account_manager.sell_market_order(ticker.market, pocket.volume)
                # 2. Persist Order ID to Pocket
                pocket.close_order_id = order.get('uuid')
                pocket.save(self.pocket_manager.db_path) # Save persistence
                self.dashboard.log(f" -> Sell Order Created: {pocket.close_order_id}")
            else:
                self.dashboard.log(f" -> Waiting for Close Order: {pocket.close_order_id}")

        elif pocket.status == PocketStateType.ACTIVE:
            self.dashboard.log(f"Pocket Updated: {pocket.ticker} ({pocket.id[:8]})")
        else:
            self.dashboard.log(f"Pocket {pocket.ticker} ({pocket.id[:8]}) is {pocket.status}")

        # Check for CLOSED status to cleanup strategies
        if pocket.status == PocketStateType.CLOSED:
             self.strategy_manager.delete_strategies_by_pocket_id(pocket.id)
             self.dashboard.log(f" -> Strategies cleaned up for Closed Pocket {pocket.id[:8]}")

    def on_pocket_deleted(self, pocket: Pocket):
        self.dashboard.update({'pocket': pocket.model_dump()})
        self.dashboard.log(f"Pocket Deleted: {pocket.ticker} ({pocket.id[:8]})")
        
        # Cleanup associated strategies
        self.strategy_manager.delete_strategies_by_pocket_id(pocket.id)

    # -- strategy events -------------------------
    def on_strategy_created(self, strategy: StrategyBase):
        self.dashboard.update({'strategy': strategy.summary()})

    def on_strategy_signal(self, strategy: StrategyBase, signal: Signal):
        self.dashboard.update({'strategy': strategy.summary()})
        # Queuing task for strategy
        self.task_queue.put(Task(cls=strategy, message=signal.model_dump()))

    def on_strategy_updated(self, strategy: StrategyBase):
        self.dashboard.update({'strategy': strategy.summary()})

    def on_strategy_deleted(self, strategy: StrategyBase):
        self.dashboard.update({'remove': {'id': strategy.strategy_id}})

    # -- WebSocket Events -------------------------
    def on_ws_opened(self, cls):
        self.dashboard.log("WebSocket Opened")

    def on_ws_closed(self, cls):
        self.dashboard.log("WebSocket Closed")

    def on_ws_message(self, cls, message: dict):
        self.task_queue.put(Task(cls=cls, message=message))   

    # -- message events -------------------------    
    def on_mqtt_message(self, topic: str, payload: str):
        """Callback for MQTT messages."""
        try:
            data = json.loads(payload)
            self.task_queue.put(Task(cls=self.messaging, message={
                "type": "command", 
                "topic": topic, 
                "data": data
            }))
        except json.JSONDecodeError:
            self.dashboard.log(f"Invalid JSON from {topic}")
            logger.debug(f"Invalid message: {payload}")
            logger.error(traceback.format_exc())

    def on_task(self, task: Task):
        
        if isinstance(task.cls, UpbitWebSocket):

            if task.message["type"] == "ticker":
                market = task.message['code']
                price = task.message['trade_price']
                self.current_prices.update(market, price)
                
                if self.current_prices.is_updated(market):
                    self.on_ticker(task.message)

            elif task.message["type"] == "orderbook":
                self.on_orderbook(task.message)
            elif task.message["type"] == "trade":
                market = task.message['code']
                price = task.message['trade_price']
                self.current_prices.update(market, price)
                if self.current_prices.is_updated(market):
                    self.on_trade(task.message)
                    
            else:
                raise Exception(f"Unknown message type: {task.message['type']} from {task.cls}")
        elif isinstance(task.cls, UpbitWebSocketPrivate) or isinstance(task.cls, DBUpbit):

            if task.message["type"] == "myOrder":
                self.on_my_order(task.cls, task.message)
            elif task.message["type"] == "myAsset":
                self.on_my_asset(task.cls, task.message)
            else:
                raise Exception(f"Unknown message type: {task.message['type']} from {task.cls}")
        elif isinstance(task.cls, MessagingClient):
            if task.message["type"] == "command":
                self.process_command(task.message["topic"], task.message["data"])
            else:
                self.dashboard.log(f"Unknown msg type from Messaging: {task.message['type']}")
        elif isinstance(task.cls, StrategyBase):
            self.on_signal_processing(task.cls, task.message)
        else:
            raise Exception(f"Unknown class: {task.message['type']} from {task.cls}")

    def on_signal_processing(self, strategy: StrategyBase, signal: dict):
        '''
        StrategyManager calls this when a signal is processed.
        '''
        pocket = None
        ticker = signal['ticker']
        volume = signal['amount']
        data = signal['data']
        

        if signal['type'] == SignalType.BUY:
            order = self.account_manager.buy_market_order(ticker, volume)

        elif signal['type'] == SignalType.SELL:
            if data and data.get("pocket_id") and signal.get("reason"):
                self.pocket_manager.set_reason(data.get("pocket_id"), signal.get("reason"))
            order = self.account_manager.sell_market_order(ticker, volume)
        
        elif signal['type'] == SignalType.CLOSE_POCKET:
            if data and data.get("pocket_id"):
                if signal.get("reason"):
                    self.pocket_manager.set_reason(data.get("pocket_id"), signal.get("reason"))
                self.pocket_manager.close_pocket(data.get("pocket_id"))
            else:
                raise Exception("Pocket ID is required for Pocket Close")
        else:
            raise Exception(f"Unknown signal type: {signal['type']}")

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
                    "pockets": len(self.pocket_manager.pockets),
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
                    try:
                        price = pyupbit.get_current_price(ticker.ticker)
                        if price is None:
                            self.dashboard.log(f"Error: Price not found for {ticker.ticker}")
                            return
                        self.dashboard.log(f"Buy Price not specified. Using Current Price: {price}")
                    except Exception as e:
                        self.dashboard.log(f"Error checking price for {ticker.ticker}: {e}")
                        return

                if won > 0 and volume <= 0:
                    # Calculate volume based on won amount
                    if price is None or (price and price <= 0):
                         # Market Order estimation or Limit calculation using current price if not provided (though limit requires price)
                         # If price not provided, we fetched it at line 325 
                         pass
                    
                    try:
                        calc_price = price if (price and price > 0) else Decimal(pyupbit.get_current_price(ticker.ticker))
                        if calc_price is None:
                            self.dashboard.log(f"Error: Price not found for {ticker.ticker}")
                            return
                    except Exception as e:
                        self.dashboard.log(f"Error checking price for {ticker.ticker}: {e}")
                        return
                    
                    # Update price only if it was not provided (and thus is market order logic?) 
                    # Actually if user gave price, we shouldn't overwrite 'price' variable if it's a Limit Order.
                    # But we need a price to calc volume.
                    
                    fee = Decimal('0.0005')
                    volume = (won - won * fee) / calc_price
                    
                    # If user provided price, keep it. If not, price might have been set to current_price at line 325.
                    # The issue was line 329: price = Decimal(...) overwrote the user's limit price.
                    # We should NOT overwrite 'price' if it was already valid.
                
                # Validation: Price and Volume must be positive
                if volume <= 0:
                     self.dashboard.log(f"Invalid Buy Volume: {volume}. Must be positive.")
                     return
                if not is_market and (price is None or price <= 0):
                     self.dashboard.log(f"Invalid Buy Price: {price}. Must be positive for Limit Order.")
                     return

                self.dashboard.log(f"CMD BUY: {ticker.currency} {ticker.volume(volume)} @ {'Market' if is_market else price}")
                
                # Trigger buy via account_manager
                if is_market:
                    order = self.account_manager.buy_market_order(ticker.ticker, volume)
                else:
                    order = self.account_manager.buy_limit_order(ticker.ticker, price, volume)

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

                try:
                    current_price = pyupbit.get_current_price(ticker.ticker)
                    if current_price is None:
                        self.dashboard.log(f"Error: Price not found for {ticker.ticker}")
                        return

                    if price is None and not is_market:
                        price = Decimal(current_price)

                    if won > 0 and volume <= 0:
                        price = Decimal(current_price)
                        fee = Decimal(0.005)
                        volume = (won - won * fee) / price
                except Exception as e:
                    self.dashboard.log(f"Error checking price for {ticker.ticker}: {e}")
                    return
                
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
                    
                    # 1. Archive Pockets
                    pockets = self.pocket_manager.get_pockets(ticker)
                    for pocket in pockets:
                        self.pocket_manager.archive_pocket(pocket.id)
                        
                    # 2. Archive Strategies
                    # Find strategies for this ticker
                    to_archive = []
                    for sid, strategy in self.strategy_manager.strategies.items():
                         if hasattr(strategy, 'context') and strategy.context.ticker == ticker:
                            to_archive.append(sid)
                    
                    for sid in to_archive:
                        self.strategy_manager.archive_strategy(sid)
                        self.dashboard.log(f"Archived Strategy: {sid}")
                        
                    self.dashboard.log(f"Cleanup complete for {ticker}")

            elif action == "cancel":
                uuid_arg = data.get("uuid")
                ticker_str = data.get("ticker")
                
                if ticker_str:
                    # Generic Cancel by Ticker
                    t = Ticker(ticker_str)
                    self.dashboard.log(f"CMD CANCEL ALL: {t.ticker}")
                    orders = self.account_manager.get_order(t.ticker)
                    if not orders:
                         self.dashboard.log(f"No open orders found for {t.ticker}")
                    
                    for order in orders:
                         oid = order.get('uuid') if isinstance(order, dict) else getattr(order, 'uuid', None)
                         if oid:
                             self.account_manager.cancel_order(oid)
                             self.dashboard.log(f"Cancelled {oid}")
                
                elif uuid_arg:
                    # Handle Partial UUID (6 chars)
                    target_uuid = uuid_arg
                    if len(uuid_arg) < 36: # Full UUID is 36 chars
                        all_orders = self.account_manager.get_orders() # Fetch all wait orders
                        matches = []
                        for order in all_orders:
                            oid = order.get('uuid') if isinstance(order, dict) else getattr(order, 'uuid', None)
                            if oid and oid.startswith(uuid_arg):
                                matches.append(oid)
                        
                        if len(matches) == 1:
                            target_uuid = matches[0]
                            self.dashboard.log(f"Partial UUID '{uuid_arg}' resolved to {target_uuid}")
                        elif len(matches) > 1:
                            self.dashboard.log(f"Ambiguous partial UUID '{uuid_arg}'. Matches: {matches}")
                            return # Safety abort
                        else:
                            self.dashboard.log(f"No order found matching partial UUID '{uuid_arg}'")
                            return

                    self.dashboard.log(f"CMD CANCEL: {target_uuid}")
                    result = self.account_manager.cancel_order(target_uuid)
                    if hasattr(result, 'model_dump'):
                         res = result.model_dump()
                    elif isinstance(result, dict):
                         res = result
                    else:
                         res = {}
                         
                    if result:
                        self.dashboard.log(f"Order Cancelled: {res.get('market')} {res.get('side')} {res.get('state')} {res.get('locked')}")
                    else:
                        self.dashboard.log(f"Order Cancel Failed or Not Found: {target_uuid}")

            elif action == "pockets":
                self.dashboard.log("CMD POCKETS Request")
                reply_to = data.get("reply_to")
                
                # Gather pockets handled by PocketManager? Or Account Assets?
                # User asked for "pocket list". Usually means active pockets tracking profits.
                # StrategyManager / PocketManager has them.
                # Let's list PocketManager active pockets.
                
                lines = []
                lines.append(f"{'UUID':<8} | {'Ticker':<10} | {'ROI':<8} | {'Vol':<12}")
                lines.append("-" * 50)
                
                count = 0 
                for pos in self.pocket_manager.pockets.values():
                   ticker = Ticker(pos.ticker)
                   profit_rate = (self.current_prices.get(ticker.ticker) / pos.entry_price) -1
                   uuid_short = pos.id[:6]
                   roi = f"{profit_rate * 100:.2f}%"
                   lines.append(f"{uuid_short:<8} | {ticker.ticker:<10} | {roi:<8} | {pos.volume}")
                   count += 1
                
                if count == 0:
                    lines.append("No active pockets.")
                    
                response_text = "\n".join(lines)
                
                if reply_to:
                    self.messaging.publish(reply_to, {"text": response_text})
                else:
                    self.dashboard.log(response_text) # Log local if no reply address
            elif action == "orders":
                 self.dashboard.log("CMD ORDERS Request")
                 reply_to = data.get("reply_to")
                 
                 # AccountManager.get_orders() returns list of open orders
                 orders = self.account_manager.get_orders()
                 
                 lines = []
                 lines.append(f"{'UUID':<8} | {'Ticker':<10} | {'Side':<4} | {'Price':<12} | {'Vol'}")
                 lines.append("-" * 65)
                 
                 count = 0
                 for o in orders:
                     # Handle Dict vs Object
                     oid = o.get('uuid') if isinstance(o, dict) else getattr(o, 'uuid', "")
                     mkt = o.get('market') if isinstance(o, dict) else getattr(o, 'market', "")
                     side = o.get('side') if isinstance(o, dict) else getattr(o, 'side', "")
                     price = o.get('price') if isinstance(o, dict) else getattr(o, 'price', 0)
                     vol = o.get('remaining_volume') if isinstance(o, dict) else getattr(o, 'remaining_volume', 0)
                     
                     uuid_short = oid[:6]
                     lines.append(f"{uuid_short:<8} | {mkt:<10} | {side:<4} | {price:<12} | {vol}")
                     count += 1
                     
                 if count == 0:
                     lines.append("No open orders.")
                     
                 response_text = "\n".join(lines)
                 
                 if reply_to:
                     self.messaging.publish(reply_to, {"text": response_text})
                 else:
                     self.dashboard.log(response_text)

            elif action == "strategy":
                sub_action = data.get("sub_action")
                strategy_type_str = data.get("type") # "buy" or "sell"
                
                if sub_action == "create":
                    if strategy_type_str == "buy":
                        ticker_str = data.get("ticker")
                        budget = Decimal(str(data.get("budget", "0")))
                        name = data.get("name", "scalping_strategy")
                        
                        if not ticker_str or budget <= 0:
                            self.dashboard.log("Invalid Strategy Creation Params")
                            return

                        # Subscribe to ticker if needed
                        ticker = Ticker(ticker_str)
                        if ticker.ticker not in self.upbit_websocket.codes:
                             self.upbit_websocket.add_subscription([ticker.ticker])
                        
                        # Create config
                        # We need to map 'name' to the correct Config class or generic dict
                        
                        # Calculate Volume from Budget (KRW)
                        current_price = self.current_prices.get(ticker.ticker)
                        if not current_price:
                            try:
                                current_price = pyupbit.get_current_price(ticker.ticker)
                            except:
                                pass
                        
                        calc_volume = Decimal("0")
                        if current_price:
                            cp = Decimal(str(current_price))
                            fee_rate = Decimal("0.0005")
                            # Volume = Budget / (Price * (1 + Fee))
                            if cp > 0:
                                calc_volume = budget / (cp * (1 + fee_rate))
                                self.dashboard.log(f"Calc Volume: {calc_volume:.8f} (Budget: {budget}, Price: {cp})")
                        else:
                             self.dashboard.log(f"Warning: Could not fetch price for {ticker.ticker}. Using Budget as raw volume (dangerous if not intended).")
                             calc_volume = budget

                        config = {
                            "name": name,
                            "type": StrategyType.BUY.value,
                            "buy_amount": calc_volume 
                        }
                        
                        if name == "volume_spike_strategy":
                             # Default config for volume spike
                             config["execution_interval"] = 60
                             config["period"] = 20
                             config["multiplier"] = 1.5

                        try:
                            sid = self.strategy_manager.create_strategy(
                                name=name,
                                type=StrategyType.BUY,
                                ticker=ticker.ticker,
                                budget=budget,
                                config=config
                            )
                            self.dashboard.log(f"CMD STRATEGY: Created {name} ({sid}) for {ticker.ticker}")
                            
                            reply_to = data.get("reply_to")
                            if reply_to:
                                self.messaging.publish(reply_to, {"text": f"Strategy Created: {sid}"})
                                
                        except Exception as e:
                            self.dashboard.log(f"Failed to create strategy: {e}")
                            logger.error(f"Failed to create strategy: {e}")
                    else:
                        self.dashboard.log(f"Unknown strategy type: {strategy_type_str}")
                elif sub_action == "list":
                     strategies = self.strategy_manager.strategies
                     
                     if not strategies:
                         response_text = "No active strategies."
                     else:
                         lines = []
                         lines.append(f"{'ID':<8} | {'Name':<20} | {'Ticker':<10} | {'Type':<6}")
                         lines.append("-" * 60)
                         
                         for sid, strategy in strategies.items():
                             s_name = strategy.config.name[:20]
                             s_ticker = strategy.context.ticker
                             s_type = strategy.config.type
                             lines.append(f"{sid[:8]:<8} | {s_name:<20} | {s_ticker:<10} | {s_type:<6}")
                         
                         response_text = "\n".join(lines)
                     
                     reply_to = data.get("reply_to")
                     if reply_to:
                         self.messaging.publish(reply_to, {"text": response_text})
                     else:
                         self.dashboard.log(response_text)

                elif sub_action == "delete":
                    strategy_id = data.get("strategy_id")
                    if not strategy_id:
                        self.dashboard.log("Delete command requires strategy_id")
                        return

                    # Support short ID
                    target_id = strategy_id
                    if len(strategy_id) < 36:
                         # Find full ID
                         found = False
                         for sid in self.strategy_manager.strategies.keys():
                             if sid.startswith(strategy_id):
                                 target_id = sid
                                 found = True
                                 break
                         if not found:
                             self.dashboard.log(f"Strategy ID not found: {strategy_id}")
                             return

                    try:
                        self.strategy_manager.stop_strategy(target_id)
                        self.strategy_manager.archive_strategy(target_id)
                        msg = f"Strategy Deleted: {target_id}"
                        self.dashboard.log(msg)
                        
                        reply_to = data.get("reply_to")
                        if reply_to:
                            self.messaging.publish(reply_to, {"text": msg})
                    except Exception as e:
                        err_msg = f"Failed to delete strategy: {e}"
                        self.dashboard.log(err_msg)
                        logger.error(err_msg)

                else:
                    self.dashboard.log(f"Unknown strategy sub-action: {sub_action}")

            else:
                self.dashboard.log(f"Unknown Action: {action}")
                
        except Exception as e:
            logger.error(f"Error processing command: {e}")
            logger.error(traceback.format_exc())

        
    # -- order events ------------------------
    def on_order_created(self, order: dict):
        self.dashboard.update({'order': order})
        self.orders[order['uuid']] = order
    
    def on_order_updated(self, order: dict):
        self.dashboard.update({'order': order})
        self.orders[order['uuid']] = order
    
    def on_order_completed(self, order: dict):
        self.dashboard.update({'order': order})

        ticker = Ticker(order['code'])
        price = Decimal(str(order['price']))
        volume = Decimal(str(order['volume']))

        ask_bid = order['ask_bid']
        # 매도 체결 완료
        if ask_bid == "ask":
            # Check if this order is linked to a closing pocket
            pocket = self.pocket_manager.get_pocket_by_order_id(order['uuid'])
            if pocket:
                self.pocket_manager.closed_pocket(pocket.id, price)
                self.dashboard.log(f"Pocket Closed by Order {order['uuid']}")
            else:
                # Fallback / Direct Sell (e.g. from CLI or Strategy without pocket link?) 
                # Or old behavior: close by ticker matching (heuristic)
                self.pocket_manager.close_pockets_by_ticker(ticker.ticker, price, volume)
                
        # 매수 체결 완료
        elif ask_bid == "bid":
            self.pocket_manager.create_pocket(ticker.ticker, price, volume)
        else:
            self.dashboard.log(f"Unknown ask_bid: {ask_bid}")
   
    def on_order_deleted(self, order: dict):
        self.dashboard.update({'order': order})
        

    def on_my_order(self, cls, message: dict):

        state = message['state']
        uuid = message['uuid']

        if state == "wait":
            if uuid not in self.orders:
                self.on_order_created(message)
            else:
                self.on_order_updated(message)
        elif state == "done":
            self.on_order_completed(message)
        elif state == "cancel":
            self.on_order_deleted(message)
            if uuid in self.orders:
                del self.orders[uuid]
        else:
            self.on_order_updated(message)

    # -- asset events ------------------------
    def on_asset_created(self, asset: dict):
        self.dashboard.update({'asset': asset})
    
    def on_asset_updated(self, asset: dict):
        self.dashboard.update({'asset': asset})
    
    def on_asset_deleted(self, asset: dict):
        self.dashboard.update({'asset': asset})

    def on_my_asset(self, cls, message: dict):
        assets = message['assets']
        for asset in assets:
            ticker = Ticker(asset['currency'])
            dbasset = self.account_manager.get_asset_balance(ticker.ticker)
            
            self.dashboard.update({'asset': dbasset})
            self.dashboard.log(f"Asset Update: {ticker.amount(dbasset['balance'])} by myAsset")
          

    def on_ticker(self, message: dict):
        ticker = message['code']
        current_price = message['trade_price']

        # logger.info(f"Ticker Update: {ticker} {current_price}")
        
        # Update Dashboard Ticker Info
        self.dashboard.update({'ticker': message})
        
        # TODO: Strategy Manager
        if self.strategy_manager:
            self.strategy_manager.on_tick(ticker, current_price)

    def on_orderbook(self, message: dict):
        tiker = Ticker(message.get('code', ''))
        orderbook = message.get('orderbook_units', [])

        self.account_manager.check_order(tiker.ticker, orderbook)

        if self.strategy_manager:
            self.strategy_manager.on_orderbook(tiker.ticker, orderbook)

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
