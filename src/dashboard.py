import queue
import threading
import time
import os
import sys
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
import logging  
from tools.candle import Candle
import pyupbit
from tools.ticker import Ticker


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
    def render(self) -> List[str]:
        pass


class LogWidget(Widget):
    def __init__(self, parent: Optional['Widget'] = None):
        super().__init__("log", parent)
        self.logs = []
        self.max_logs = 5
    
    def update(self, data: Dict[str, Any]):
        if 'message' in data:
            self.update_log(data['message'])

    def update_log(self, message: str):
        self.logs.append(message)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
    
    def render(self) -> List[str]:
        return self.logs

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

    def render(self) -> str:
        if self.state:
            return f"{self.name}({self.state})"
        return f"{self.name}"

class PositionWidget(Widget):
    def __init__(self, id: str, parent: 'Widget'):
        super().__init__(id, parent)
        self.entry_price = 0.0
        self.volume = 0.0
        self.strategies: Dict[str, StrategyWidget] = {} # Map ID to Widget

    def update(self, data: Dict[str, Any]):
        # data is Position dict or dump
        self.entry_price = float(data.get('entry_price', self.entry_price))
        self.volume = float(data.get('volume', self.volume))
        
        # Strategies might be passed as list of dicts/DTOs?
        # If passed as 'strategies' list, we might need to update them here or let Dashboard route them?
        # For now, Dashboard routes by ID. But if Position dump contains strategies, we might need to process them.
        # But typically Position dump doesn't contain full Strategy objects? 
        # StrategyManager manages strategies. 
        # So Position update is mostly price/volume.
        pass

    def render(self, current_price: float) -> str:
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

        return f"   └── Rot: {strategy_str} | PnL: {profit_rate_str} | Vol: {volume_krw:,.0f}"


class TickerWidget(Widget):
    
    def __init__(self, ticker: str):
        super().__init__(ticker, None) # Root widget
        self.coin = Ticker(ticker)
        self.amount = 0
        self.avg_buy_price = 0.0
        # Candle initialization (could be async or deferred)
        self.candle : Candle = Candle(self.coin.ticker, 0.0)
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
            self.amount = float(data.get('balance', 0))
            if 'avg_buy_price' in data:
                self.avg_buy_price = float(data.get('avg_buy_price', 0))
        
        if 'trade_price' in data: # Ticker update
             self.candle.update(data['trade_price'])
        
        if 'price' in data and 'ticker' in data: # Generic update format
             self.candle.update(data['price'])
        
        self.spinner.next()
        
        
    def render(self) -> List[str]:
        output = []
        
        current_price = self.candle.current_price()
        
        # Calculate Amount (Invested KRW)
        amount = self.amount * self.avg_buy_price
        now_amount = self.amount * current_price
        
        # Calculate Profit % (Evaluation profit based on avg buy price)
        if self.avg_buy_price > 0 and current_price > 0:
            profit_rate = (current_price - self.avg_buy_price) / self.avg_buy_price * 100
            if profit_rate < 0:
                profit_str = f"\033[34m{now_amount - amount:,.0f}({profit_rate:.2f}%)\033[0m"
            else:
                profit_str = f"\033[31m{now_amount - amount:,.0f}({profit_rate:.2f}%)\033[0m"
        else:
            profit_str = f"{now_amount - amount:,.0f}(0.0%)"

        header = f" {self.coin.ticker:<10} | {amount:>12,.0f} | {profit_str:12} | {current_price:>12,.0f} {self.spinner()} | {self.candle.render()}"
        output.append(header)
        
        # Render child widgets (Positions and Strategies)
        if self.children:
            # Separate by type
            strategies = [w for w in self.children.values() if isinstance(w, StrategyWidget)]
            positions = [w for w in self.children.values() if isinstance(w, PositionWidget)]
            
            # Render Strategies first
            if strategies:
                strat_str = ", ".join([s.render() for s in strategies])
                output.append(f"   └── Strategies: {strat_str}")

            # Render Positions
            for pos in positions:
                output.append(pos.render(current_price))
        else:
            output.append(f"   └── No Active Positions")
        
        output.append("-" * MAX_WIDTH)
        return output

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
        self.update({'type': 'log', 'message': message})
        logger.info(message)
        
    # -- Internal Processing --
    def _process_item(self, data: Dict[str, Any]):
        with self.lock:
            # 1. Identify Target Widget ID
            target_id = None
            widget_type = None
            
            # Heuristic to determine type and ID
            if 'type' in data and data.get('type') == 'myOrder':
                 target_id = data['code']
                 widget_type = 'ticker'
            elif 'message' in data and data.get('type') == 'log':
                 target_id = 'log'
            elif 'strategy_id' in data: # Strategy
                 target_id = data['strategy_id']
                 widget_type = 'strategy'
            elif 'id' in data: # Position (has 'id') - careful, check context
                 # Position dump has 'id', 'ticker'
                 if 'ticker' in data and 'entry_price' in data:
                     target_id = data['id']
                     widget_type = 'position'
            elif 'currency' in data: # Balance
                 target_id = Ticker(data['currency']).ticker # e.g. KRW-BTC
                 widget_type = 'ticker'
            elif 'code' in data: # Ticker update (Upbit websocket)
                 target_id = Ticker(data['code']).ticker
                 widget_type = 'ticker'
            elif 'ticker' in data: 
                 if 'price' in data: # Simple ticker update
                     target_id = Ticker(data['ticker']).ticker
                     widget_type = 'ticker'

            if not target_id:
                logger.debug(f"Dashboard: Could not identify target ID for data: {data.keys()}")
                return

            # 2. Find or Create Widget
            if target_id not in self.registry:
                # Create if missing
                self._create_widget(target_id, widget_type, data)
            
            # 3. Update Widget
            if target_id in self.registry:
                self.registry[target_id].update(data)
                
    def _create_widget(self, id: str, w_type: str, data: Dict[str, Any]):
        widget = None
        parent_id = None
        
        if w_type == 'ticker':
            widget = TickerWidget(id) # Parent None
            widget.avg_buy_price = data.get('avg_buy_price', 0)
            
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
                        logger.error(f"Error processing item: {e}")

                # Render
                now = time.time()
                if now - last_render > render_interval:
                    self._render()
                    last_render = now

                time.sleep(0.1)
                
            except Exception as e:
                with open("dashboard_error.log", "a") as f:
                    f.write(f"ERROR: {e}\n")

    def _render(self):
        # Move cursor to top-left
        sys.stdout.write("\033[H")
        
        output = []
        output.append("=" * MAX_WIDTH)
        output.append(f" Coin Strategy Dashboard ({time.strftime('%H:%M:%S')})")
        output.append("=" * MAX_WIDTH)
        
        with self.lock:
            # Render TickerWidgets (Roots)
            # Filter registry for TickerWidgets
            tickers = sorted([w for w in self.registry.values() if isinstance(w, TickerWidget)], key=lambda x: x.id)
            for widget in tickers:
                output.extend(widget.render())

        # Logs area
        output.append("")
        output.append("[Recent Logs]")
        output.extend(self.log_widget.render()) # Already returns list of strings
            
        # Fill rest of screen
        sys.stdout.write("\n".join([line + "\033[K" for line in output]) + "\033[J")
        sys.stdout.flush()
