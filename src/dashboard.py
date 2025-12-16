import queue
import threading
import time
import json
import os
import sys
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
import logging  
from tools.candle import Candle
import pyupbit
from tools.ticker import Ticker
from tools.currency_print import WonColor, RateColor, Won
from decimal import Decimal
import traceback

logger = logging.getLogger(__name__)

MAX_WIDTH = 120


# widget의 계층 구조
# Dashboard
#   └── LogWidget
#   └── BalanceWidget
#   └── TickerWidget
#       └── CandleWidget
#       └── PositionsWidget x N
#           └── StrategyWidget x N
class Spinner:
    def __init__(self):
        self.spins = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.index = 0

    def next(self):
        self.index = (self.index + 1) % len(self.spins)
        return self.spins[self.index]
    
    def __call__(self):
        return self.spins[self.index]

class Widget(ABC):

    def __init__(self, id: str, parent: Optional['Widget'] = None):
        self.id = id
        self.parent = parent
        self.children: Dict[str, 'Widget'] = {}
    
    def add_child(self, widget: 'Widget'):
        self.children[widget.id] = widget

    @abstractmethod
    def update(self, data: Dict[str, Any]):
        pass
    
    @abstractmethod
    def render(self, current_price: Decimal = Decimal("0")) -> str:
        pass


class LogWidget(Widget):
    def __init__(self, parent: Optional['Widget'] = None):
        super().__init__("log", parent)
        self.logs = []
        self.max_logs = 8
    
    def update(self, data: Dict[str, Any]):
        if 'message' in data:
            self.update_log(data['message'])

    def update_log(self, message: str):
        space = MAX_WIDTH - len(message)
        self.logs.append(message + " " * space)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
    
    def render(self, current_price: Decimal = Decimal("0")) -> str:
        return "\n".join(self.logs)

class StrategyWidget(Widget):
    def __init__(self, id: str, parent: 'Widget'):
        super().__init__(id, parent)
        self.name = "Unknown"
        self.state = ""
    
    def update(self, data: Dict[str, Any]):
        # data is StrategyDTO or dict
        self.name = data.get('type', self.name)
        self.state = data.get('status', self.state)
        # Handle simple dict update too
        if 'strategy' in data: # legacy or simple dict
             self.name = data.get('strategy', self.name)
        if 'state' in data:
             self.state = data.get('state', self.state)

    def render(self, current_price: Decimal = Decimal("0")) -> str:
        if self.state:
            return f"{self.name}({self.state})"
        return f"{self.name}"

class PositionWidget(Widget):
    def __init__(self, id: str, parent: 'Widget'):
        super().__init__(id, parent)
        self.entry_price = Decimal("0")
        self.volume = Decimal("0")
        self.strategies: Dict[str, StrategyWidget] = {} # Map ID to Widget

    def update(self, data: Dict[str, Any]):
        # data is Position dict or dump
        self.entry_price = Decimal(str(data.get('entry_price', self.entry_price)))
        self.volume = Decimal(str(data.get('volume', self.volume)))
        
        # Strategies might be passed as list of dicts/DTOs?
        # If passed as 'strategies' list, we might need to update them here or let Dashboard route them?
        # For now, Dashboard routes by ID. But if Position dump contains strategies, we might need to process them.
        # But typically Position dump doesn't contain full Strategy objects? 
        # StrategyManager manages strategies. 
        # So Position update is mostly price/volume.
        pass

    def render(self, current_price: Decimal = Decimal("0")) -> str:
        # Render strategies
        strategy_str = ", ".join([s.render() for s in self.children.values()])
        
        # PnL
        if current_price and self.entry_price:
            profit_rate = (current_price - self.entry_price) / self.entry_price * 100
            if profit_rate < 0:
                profit_rate_str = f"\033[34m{profit_rate:.2f}%\033[0m"
            else:
                profit_rate_str = f"\033[31m+{profit_rate:.2f}%\033[0m"
        else:
            profit_rate_str = "0.00%"

        # Volume
        volume_krw = self.volume * self.entry_price
        pid_short = str(self.id)[:4]

        return f"   └── Rot:  | Vol: {Won(volume_krw)}:{profit_rate_str}"
    
class AssetWidget(Widget):
    def __init__(self, currency: str):
        super().__init__(currency, None) # Root widget
        self.currency = currency
        self.balance = Decimal("0")
        self.avg_buy_price = Decimal("0")
        self.locked = Decimal("0")
        
    
    def update(self, data: Dict[str, Any]):
        self.balance = Decimal( data.get('balance', self.balance) )
        self.avg_buy_price = Decimal(data.get('avg_buy_price', self.avg_buy_price))
        self.locked = Decimal(data.get('locked', self.locked))
    
    def render(self, current_price: Decimal = Decimal("0")) -> str:
        
        if self.balance == 0 or self.currency == "KRW":
            if self.locked > 0:
                 return f"{WonColor(self.balance)} (Lock: {WonColor(self.locked)})"
            return f"{WonColor(self.balance)}"
        
        profit = (current_price - self.avg_buy_price) / self.avg_buy_price * 100
        profit_won = (current_price - self.avg_buy_price) * self.balance

        locked_str = ""
        if self.locked > 0:
            locked_str = f" (Lock: {self.locked})"

        return f" {self.balance * current_price:>10,.0f}원 ({WonColor(profit_won)}:{RateColor(profit)}){locked_str} | 현재가: {current_price:,.0f}"


class OrderWidget(Widget):
    def __init__(self, id: str, parent: 'Widget'=None):
        super().__init__(id, parent)
        self.uuid = id
        self.market = ""
        self.ask_bid = ""
        self.ord_type = ""
        self.price = Decimal("0")
        self.volume = Decimal("0")
        self.volume = Decimal("0")
        self.created_at = time.time()
        self.state = ""
        self.ticker = None

    def update(self, data: Dict[str, Any]):
        logger.info(f"Order Update: {json.dumps(data, indent=4, default=str)}")
        """
        Example:
            {
                "type": "myOrder",
                "code": "KRW-SOL",
                "uuid": "67fb54e1-2791-4024-a806-1c1a4908c745",
                "ask_bid": "bid",
                "order_type": "limit",
                "state": "wait",
                "price": 197200.0,
                "volume": 2.535496957403651,
                "created_at": "2025-12-15T13:44:42.997437+00:00"
            }
        """
        self.uuid = data.get('uuid', self.uuid)
        self.market = data.get('code', "") or data.get('market', "")
        
        # side/ask_bid mapping
        self.ask_bid = data.get('ask_bid', data.get('side', self.ask_bid))
        
        self.ord_type = data.get('order_type', data.get('ord_type', self.ord_type))
        
        # Safe Decimal conversion
        try:
            price_val = data.get('price')
            if price_val is None:
                self.price = Decimal("0")
            else:
                self.price = Decimal(str(price_val))
        except:
             self.price = Decimal("0")

        try:
            vol_val = data.get('volume')
            if vol_val is None:
                self.volume = Decimal("0")
            else:
                self.volume = Decimal(str(vol_val))
        except:
             self.volume = Decimal("0")

        self.state = data.get('state', self.state)
        self.ticker = Ticker(self.market)

    def render(self, current_price: Decimal = Decimal("0")) -> str:
        total = self.price * self.volume
        line = f"Order: {self.market} | {self.ask_bid} | {self.ord_type} | {self.ticker.volume(self.volume)} x {self.price:,.0f}원 | {total:,.0f}원 | {self.state}"
        space = ' ' * (MAX_WIDTH - len(line))
        return f"{line}{space}"

class TickerWidget(Widget):
    
    def __init__(self, ticker: str):
        super().__init__(ticker, None) # Root widget
        self.coin = Ticker(ticker)
        
        self.asset : AssetWidget = AssetWidget(ticker)
        # Candle initialization (could be async or deferred)
        self.candle : Candle = Candle(self.coin.ticker, Decimal("0"))
        self.spinner = Spinner()
        try:
             ohlcv = pyupbit.get_ohlcv(self.coin.ticker, interval="day")
             if ohlcv is not None and not ohlcv.empty:
                 self.candle.reset(ohlcv)
        except:
             pass

    def update(self, data: Dict[str, Any]):
        # Check if balance update or ticker update
        if 'balance' in data:
            self.asset.update(data)
        
        if 'trade_price' in data: # Ticker update
             self.candle.update(data['trade_price'])
        
        if 'price' in data and 'ticker' in data: # Generic update format
             self.candle.update(data['price'])
        
        self.spinner.next()
        
        
    def render(self, current_price: Decimal = Decimal("0")) -> str:
        output = []
        
        current_price = self.candle.current_price()
        # Candle uses float, AssetWidget uses Decimal
        current_price_dec = Decimal(str(current_price))

        output.append(f"{self.spinner()} {self.coin.ticker:<10} |  {self.candle.render()}")
        output.append(f"   └── Asset | {self.asset.render(current_price_dec)} ")
        
        # Render child widgets (Positions and Strategies)
        if self.children:
            # Separate by type
            strategies = [w for w in self.children.values() if isinstance(w, StrategyWidget)]
            positions = [w for w in self.children.values() if isinstance(w, PositionWidget)]
            
            # Render Strategies first
            if strategies:
                strat_str = ", ".join([s.render(current_price_dec) for s in strategies])
                output.append(f"   └── Strategies: {strat_str}")

            # Render Positions
            for pos in positions:
                output.append(pos.render(current_price_dec))
        else:
            output.append(f"   └── No Active Positions")
        
        output.append("-" * MAX_WIDTH)
        return "\n".join(output)

class Dashboard:
    def __init__(self):
        self.queue = queue.Queue()
        self.running = False
        
        # Registry: global map of ID -> Widget
        self.registry: Dict[str, Widget] = {}
        
        # Ticker Widgets are roots, store them in registry using ticker symbol
        
        self.log_widget = LogWidget()
        self.registry['log'] = self.log_widget
        
        self.lock = threading.Lock()
        self._thread = None
        self.spinner = Spinner()

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    # -- Public API: Generic Update --
    def update(self, data: Dict[str, Any]):
        """
        Generic update method.
        Queues data for processing on main thread.
        """
        self.queue.put(data)

    def log(self, message: str):
        self.update({'log': {'message': message}})
        logger.info(message)
        
    # -- Internal Processing --
    def _process_item(self, data: Dict[str, Any]):
        with self.lock:
            # 1. Identify Target Widget ID
            target_id = None
            widget_type = None
            payload = None
            
            try:
                mtype = next(iter(data))
                payload = data[mtype]
            except StopIteration:
                self.log(f"Received empty data: {data}")
                return

            if 'ticker' in mtype:
                target_id = Ticker(payload.get('code')).ticker
                widget_type = 'ticker'
            elif 'log' in mtype:
                # Log handles its own update structure usually, or just string?
                # LogWidget.update expects dict with 'message'.
                # payload is {'message': '...'} usually from self.log()
                self.log_widget.update(payload)
                return
            elif 'asset' in mtype:
                target_id = Ticker(payload.get('currency')).ticker
                widget_type = 'ticker'
            elif 'orderbook' in mtype:
                target_id = Ticker(payload.get('code')).ticker
                widget_type = 'ticker'
            elif 'position' in mtype:
                target_id = payload.get('id')
                widget_type = 'position'
            elif 'strategy' in mtype:
                target_id = payload.get('strategy_id')
                widget_type = 'strategy'
            elif 'order' in mtype:
                target_id = payload.get('uuid')
                widget_type = 'order'
            else:
                self.log(f"Unknown message type: {data}")
                return

            if not target_id:
                # Only log if it's not a log message itself (recursion risk?)
                # But we handled log above.
                self.log(f"Dashboard: Could not identify target ID for data: {data.keys()}")
                return

            # 2. Find or Create Widget
            if target_id not in self.registry:
                # Create if missing
                self._create_widget(target_id, widget_type, payload)
            
            # 3. Update Widget
            if target_id in self.registry:
                self.registry[target_id].update(payload)
                
    def _create_widget(self, id: str, w_type: str, data: Dict[str, Any]):
        widget = None
        parent_id = None
        
        if w_type == 'ticker':
            widget = TickerWidget(id) # Parent None
            widget.avg_buy_price = data.get('avg_buy_price', 0)
        
        elif w_type == 'order':
            widget = OrderWidget(id) # Parent None
            widget.update(data)
            self.registry[id] = widget
        
        elif w_type == 'position':
            # Needs parent ticker
            ticker = Ticker(data.get('ticker')).ticker
            if ticker not in self.registry:
                 # Create TickerWidget first
                 self._create_widget(ticker, 'ticker', {'code': ticker})
            
            parent = self.registry[ticker]
            widget = PositionWidget(id, parent)
            parent.add_child(widget)
            
        elif w_type == 'strategy':
            # Needs parent position OR ticker
            # StrategyDTO has 'position_id' (optional) or 'ticker'
            pos_id = data.get('position_id')
            ticker_code = data.get('ticker')
            
            # 1. Try Position Parent
            if pos_id and pos_id in self.registry:
                parent = self.registry[pos_id]
                widget = StrategyWidget(id, parent)
                parent.add_child(widget)
            
            # 2. Try Ticker Parent (Orphan Strategy)
            elif ticker_code:
                t_code = Ticker(ticker_code).ticker
                if t_code not in self.registry:
                     self._create_widget(t_code, 'ticker', {'code': t_code})
                
                parent = self.registry[t_code]
                widget = StrategyWidget(id, parent)
                parent.add_child(widget)
            else:
                # Strategy without position or ticker? Impossible to place.
                logger.warning(f"Dashboard: Strategy {id} has no position_id or ticker. Cannot create widget.")
                return

        if widget:
            self.registry[id] = widget


    def _run_loop(self):
        # Clear screen initially
        os.system('clear')
        last_render = 0
        render_interval = 0.1 
        
        while self.running:
            try:
                # Process queue
                while True:
                    try:
                        data = self.queue.get_nowait()
                        self._process_item(data)
                    except queue.Empty:
                        break
                    except Exception as e:
                        logger.error(f"Error processing item: {traceback.print_exc()}")
                        logger.error(f"Error processing item: {e}")
                        break

                # Render
                now = time.time()
                if now - last_render > render_interval:
                    self._render()
                    last_render = now

                time.sleep(0.1)
                
            except Exception as e:
                print(traceback.print_exc())
                logger.error(f"Error in run loop: {e}")
                self.running = False

    def _render(self):
        # Move cursor to top-left
        sys.stdout.write("\033[H")
        
        output = []
        output.append("=" * MAX_WIDTH)
        output.append(f" Coin Strategy Dashboard ({time.strftime('%H:%M:%S')}) {self.spinner.next()}")
        output.append("=" * MAX_WIDTH)
        
        with self.lock:
            # Render TickerWidgets (Roots)
            # Filter registry for TickerWidgets
            tickers = sorted([w for w in self.registry.values() if isinstance(w, TickerWidget)], key=lambda x: x.id)
            for widget in tickers:
                line = widget.render()
                output.append(f"{line}")

            orders = sorted([w for w in self.registry.values() if isinstance(w, OrderWidget)], key=lambda x: x.id)
            for widget in orders:
                line = widget.render()
                output.append(f"{line}")

        # Logs area
        output.append("")
        output.append("[Recent Logs]")
        output.append(self.log_widget.render()) # Already returns list of strings
            
        # Fill rest of screen
        sys.stdout.write("\n".join([line + "\033[K" for line in output]) + "\033[J")
        sys.stdout.flush()
