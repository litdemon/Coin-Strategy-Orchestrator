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
from tools.currency_print import WonColor, RateColor, Won, WonR, WonG, WonY, WonB
from decimal import Decimal
import traceback

logger = logging.getLogger(__name__)

MAX_WIDTH = 120


# widget의 계층 구조
# Dashboard
#   └── LogWidget
#   └── TickerWidget
#       └── CandleWidget
#       └── AssetWidget
#       └── OrderWidget x N
#       └── PositionsWidget x N
#           └── StrategyWidget x N
class Spinner:
    def __init__(self):
        self.spins = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.index = 0
        self._count = 0

    def next(self):
        self.index = (self.index + 1) % len(self.spins)
        self._count += 1
        return self.spins[self.index]
    
    def count(self):
        return self._count

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
        self.config = {}

    def update(self, data: Dict[str, Any]):
        logger.info(f"Strategy Update: {json.dumps(data, indent=4, default=str)}")
        # data is StrategyDTO or dict
        self.name = data.get('type', self.name)
        self.state = data.get('status', self.state)
        self.config = data.get('config', self.config)
        
        # Handle simple dict update too
        if 'strategy' in data: # legacy or simple dict
             self.name = data.get('strategy', self.name)
        if 'state' in data:
             self.state = data.get('state', self.state)

    def render(self, current_price: Decimal = Decimal("0")) -> str:
        # Format config for display
        config_str = ""
        if self.name == "trailing_stop":
            pct = self.config.get('trail_percent', 0)
            config_str = f" [{pct}%]"
        elif self.name == "take_profit":
             pct = self.config.get('target_percent', 0)
             config_str = f" [Take:{pct}%]"
        
        state_str = f"({self.state})" if self.state else ""
        return f"\033[96m{self.name}{config_str}\033[0m{state_str}"


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

        strategy_str = ", ".join([s.render() for s in self.children.values()])        

        return f"   └── Rot:  | Vol: {Won(volume_krw)}:{profit_rate_str} | {strategy_str}"
    
class AssetWidget(Widget):
    def __init__(self, currency: str):
        super().__init__(currency, None) # Root widget
        self.ticker = Ticker(currency)
        self.balance = Decimal("0")
        self.avg_buy_price = Decimal("0")
        self.locked = Decimal("0")
        
    
    def update(self, data: Dict[str, Any]):
        self.balance = Decimal( data.get('balance', self.balance) )
        self.avg_buy_price = Decimal(data.get('avg_buy_price', self.avg_buy_price))
        self.locked = Decimal(data.get('locked', self.locked))
    
    def render(self, current_price: Decimal = Decimal("0")) -> str:
        
        if self.ticker.currency == "KRW":
            if self.locked > Decimal("0"):
                 return f"{WonY(self.balance)} (Lock: {WonR(self.locked)})"
            return f"{WonY(self.balance)}"

        profit_rate = Decimal("0")        
        if self.avg_buy_price > Decimal("0"):
            profit_rate = (current_price - self.avg_buy_price) / self.avg_buy_price * 100
            

        locked_str = ""
        if self.locked > Decimal("0"):
            won_locked = self.locked * current_price
            locked_str = f" (Lock: {WonR(won_locked)})"

        won_total = ( self.balance + self.locked ) * current_price
        
        profit_str = ""
        if self.balance > Decimal("0"):
            won_profit = ( current_price - self.avg_buy_price ) * self.balance
            profit_str = f" ({WonColor(won_profit)}:{RateColor(profit_rate)})"

        return f"{WonY(won_total)}{locked_str}{profit_str} "


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
        # Format: [ sell/buy, ticker, amount, fee, order_price ]
        sidestr = "BUY" if self.ask_bid == "bid" else "SELL"
        color = "\033[31m" if self.ask_bid == "bid" else "\033[34m" # Red for Buy, Blue for Sell
        
        # Fee calculation (estimation 0.05%)
        fee = total * Decimal("0.0005") 
        
        return f"   └── Order: {color}{sidestr:<4}\033[0m | {self.ticker.ticker:<10} | Vol: {self.volume:,.4f} | Fee: {fee:,.0f} | Price: {self.price:,.0f}"

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
        
        def with_space(line: str):
            space = ' ' * (MAX_WIDTH - len(line))
            return f"{line}{space}"

        current_price = self.candle.current_price()
        # Candle uses float, AssetWidget uses Decimal
        current_price_dec = Decimal(str(current_price))

        candle_str = f"{self.spinner()} {self.candle.render()} {Won(current_price_dec)}"
        output.append(with_space(f" {self.coin.ticker:11} | {candle_str}"))
        if self.asset.balance > Decimal("0"):
            output.append(with_space(f"   └── Asset | {self.asset.render(current_price_dec)} "))
        
        # Render child widgets (Positions and Strategies)
        if self.children:
            # Separate by type
            strategies = [w for w in self.children.values() if isinstance(w, StrategyWidget)]
            positions = [w for w in self.children.values() if isinstance(w, PositionWidget)]
            
            # Render Strategies first
            if strategies:
                strat_str = ", ".join([s.render(current_price_dec) for s in strategies])
                output.append(with_space(f"   └── Strategies: {strat_str}"))

            # Render Orders
            orders = [w for w in self.children.values() if isinstance(w, OrderWidget)]
            for order in orders:
                output.append(with_space(order.render(current_price_dec)))

            # Render Positions
            for pos in positions:
                output.append(with_space(pos.render(current_price_dec)))

        
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
        self.orderbook_spinner = Spinner()
        self.ticker_spinner = Spinner()
        self.position_spinner = Spinner()
        self.strategy_spinner = Spinner()
        self.order_spinner = Spinner()
        

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
                self.log_widget.update(payload)
                return
            elif 'asset' in mtype:
                target_id = Ticker(payload.get('currency')).ticker
                widget_type = 'ticker'
            elif 'orderbook' in mtype:
                self.orderbook_spinner.next()
                target_id = Ticker(payload.get('code')).ticker
                widget_type = 'ticker'
            elif 'position' in mtype:
                self.position_spinner.next()
                target_id = payload.get('id')
                widget_type = 'position'
            elif 'strategy' in mtype:
                self.strategy_spinner.next()
                target_id = payload.get('strategy_id')
                widget_type = 'strategy'
            elif 'order' in mtype:
                self.order_spinner.next()
                target_id = payload.get('uuid')
                widget_type = 'order'
            elif 'remove' in mtype:
                target_id = payload.get('id')
                if target_id and target_id in self.registry:
                    self.log(f"Removing widget: {target_id}")
                    # If it has a parent, remove from parent's children
                    widget = self.registry[target_id]
                    if widget.parent and hasattr(widget.parent, 'children'):
                         # Assuming parent has children dict or list
                         # TickerWidget has self.children = {} (OrderedDict or similar)
                         if target_id in widget.parent.children:
                             del widget.parent.children[target_id]
                             
                             # Check if parent (Ticker) needs to be removed now that child is gone?
                             self._check_and_remove_ticker(widget.parent.id)

                    del self.registry[target_id]
                return
            else:
                self.log(f"Unknown message type: {data}")
                return

            if not target_id:
                # Only log if it's not a log message itself (recursion risk?)
                # But we handled log above.
                self.log(f"Dashboard: Could not identify target ID for data: {data.keys()}")
                return

            # 2. Find or Create Widget
            # 2. Find or Create Widget
            if target_id not in self.registry:
                if 'ticker' in mtype or 'orderbook' in mtype:
                    return

                # Create if missing (for asset, order, position, strategy)
                self._create_widget(target_id, widget_type, payload)
            
            # 3. Update Widget
            if target_id in self.registry:
                widget = self.registry[target_id]
                widget.update(payload)
                
                # Check for Order Completion/Cancellation
                if widget_type == 'order':
                    if widget.state in ['done', 'cancel']:
                         self.log(f"Removing completed order: {target_id} ({widget.state})")
                         # Remove from parent
                         if widget.parent and hasattr(widget.parent, 'children'):
                             if target_id in widget.parent.children:
                                 del widget.parent.children[target_id]
                         
                         # Remove from registry
                         del self.registry[target_id]
                         
                         # Check cleanup for parent
                         if widget.parent:
                             self._check_and_remove_ticker(widget.parent.id)
                         return # Done with this item

                # 4. Cleanup Check (if Asset/Position update)
                # If TickerWidget is empty (Balance 0, Locked 0, No Children), remove it.
                if widget_type in ['asset', 'ticker', 'position']: # 'asset' handled as 'ticker' type but payload is from 'asset' msg
                    # If it was an asset update, target_id is Ticker.
                    # If it was a position update, target_id might be Position ID? 
                    # Wait, if position update, target_id is position ID.
                    # We need to find the parent ticker to check cleanup.
                    
                    cleanup_target_id = None
                    if target_id in self.registry and isinstance(self.registry[target_id], TickerWidget):
                        cleanup_target_id = target_id
                    elif target_id in self.registry and isinstance(self.registry[target_id], PositionWidget):
                        # Position widget, check parent
                        parent = self.registry[target_id].parent
                        if parent and isinstance(parent, TickerWidget):
                             cleanup_target_id = parent.id
                    
                    if cleanup_target_id:
                        self._check_and_remove_ticker(cleanup_target_id)
                
    def _check_and_remove_ticker(self, ticker_id: str):
        if ticker_id not in self.registry:
            return
            
        widget = self.registry[ticker_id]
        if not isinstance(widget, TickerWidget):
            return

        # Condition 1: Balance & Locked is 0
        if widget.asset.balance > 0 or widget.asset.locked > 0:
            return
            
        # Condition 2: No Children (Positions/Strategies)
        # Note: PositionWidget might be "closed" but still in children if not removed?
        # If we rely on PositionWidget removal elsewhere, this is fine.
        # But if PositionWidget is created, it stays in children.
        # So we only remove if children is empty.
        # Users might want to see closed positions for a while?
        # User request: "When sold all (balance 0), remove ticker". 
        # Usually implies all positions generate the Sell, so positions are closed.
        # If we have closed positions, should we remove the Ticker?
        # If Ticker is removed, Positions are gone too (from UI).
        # This seems to be what user wants ("Update dashboard to remove TickerWidget").
        
        # However, we must ensure we don't remove if there are ACTIVE positions.
        # PositionWidget doesn't interpret "active" vs "closed" state fully in property?
        # Let's check if any child is a PositionWidget.
        # Ideally, we should check if they are "active".
        # But PositionWidget structure implies existence = relevant.
        # If user sold all, typically positions are closed.
        # If we implement "Remove Ticker", we implicitly remove all children.
        
        # Safest check: If Balance is 0 and Locked is 0.
        # But what if I have a position but balance is 0? (Shorting? Not supported here).
        # Or partial fill?
        # User said "All sold, Balance 0".
        # So if Balance is 0 and Locked is 0, we can remove.
        # Wait, if I have an Open Order (Buy), Locked > 0. So it won't be removed. Correct.
        # If I have Open Order (Sell), Locked > 0. Won't be removed. Correct.
        # So checking Balance + Locked == 0 is consistent.
        # But what if I have an active position (Wait, Sell Limit not created yet)?
        # If I have active position, I likely have some balance (the coin).
        # So Balance > 0. 
        # So Balance == 0 and Locked == 0 implies no Coin holdings and no Active Sell Orders.
        # Does it imply no Buy Orders?
        # Buy Order locks KRW, not Coin.
        # So KRW-BTC TickerWidget might have Balance 0, Locked 0 (Coin), but user has Buy Order for BTC.
        # If we remove TickerWidget, we can't see the Buy Order execution on that Ticker?
        # OrderWidget is separate? No, OrderWidget is unrelated to TickerWidget in hierarchy?
        # Dashboard displays OrderWidgets separately in `_render`:
        # `orders = sorted([w for w in self.registry.values() if isinstance(w, OrderWidget)], ...)`
        # `TickerWidget` displays `Candle` and `Asset`.
        # If we remove TickerWidget, we lose Candle view and Asset view.
        # If I have a Buy Order, do I want to see the Ticker (Candle)? Probably yes.
        # So we should check if there are any Orders for this ticker?
        # `dashboard.registry` has `OrderWidget`s.
        
        # Strict Check: Balance 0, Locked 0, And No Children (Orders, Positions, Strategies)
        if not widget.children and widget.asset.balance <= 0 and widget.asset.locked <= 0:
             self.log(f"Removing empty ticker: {ticker_id}")
             del self.registry[ticker_id]
             return

        # Explicitly return if conditions not met (cleaning up previous logic)
        return

                
    def _create_widget(self, id: str, w_type: str, data: Dict[str, Any]):
        widget = None
        parent_id = None
        
        if w_type == 'ticker':
            widget = TickerWidget(id) # Parent None
            widget.avg_buy_price = data.get('avg_buy_price', 0)
        
        elif w_type == 'order':
            # Needs parent ticker
            t_code = Ticker(data.get('code', "") or data.get('market', "")).ticker
            if t_code not in self.registry:
                 self._create_widget(t_code, 'ticker', {'code': t_code})
            
            parent = self.registry[t_code]
            widget = OrderWidget(id, parent) 
            widget.update(data)
            parent.add_child(widget)
        
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
        info = f"OB:{self.orderbook_spinner.count()} | T:{self.ticker_spinner.count()} | P:{self.position_spinner.count()} | S:{self.strategy_spinner.count()} | O:{self.order_spinner.count()}"
        output.append(f" Coin Strategy Dashboard ({time.strftime('%H:%M:%S')}) {self.spinner.next()} {info}")
        output.append("=" * MAX_WIDTH)
        
        with self.lock:
            # Render TickerWidgets (Roots)
            # Filter registry for TickerWidgets
            tickers = sorted([w for w in self.registry.values() if isinstance(w, TickerWidget)], key=lambda x: x.id)
            for widget in tickers:
                line = widget.render()
                output.append(f"{line}")



        # Logs area
        output.append("")
        output.append("[Recent Logs]")
        output.append(self.log_widget.render()) # Already returns list of strings
            
        # Fill rest of screen
        sys.stdout.write("\n".join([line + "\033[K" for line in output]) + "\033[J")
        sys.stdout.flush()
