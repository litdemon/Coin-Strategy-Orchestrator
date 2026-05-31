import logging
import os
import sys
import threading
import time
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict, Optional

from tools.candle import Candle
from tools.ticker import Ticker
from tools.currency_print import WonColor, RateColor, Won, WonR, WonG, WonY, WonB

logger = logging.getLogger(__name__)

MAX_WIDTH = 120


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
        self.spinner = Spinner()
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
            msg = data['message']
            space = MAX_WIDTH - len(msg)
            self.logs.append(msg + " " * max(0, space))
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
        self.display = ""

    def update(self, data: Dict[str, Any]):
        self.spinner.next()
        self.name = data.get('name', data.get('type', self.name))
        self.state = data.get('status', self.state)
        self.config = data.get('config', self.config)
        self.display = data.get('display', self.display)
        if 'strategy' in data:
            self.name = data.get('strategy', self.name)
        if 'state' in data:
            self.state = data.get('state', self.state)

    def render(self, current_price: Decimal = Decimal("0")) -> str:
        return f"\033[96m{self.spinner()} {self.name}[{self.display}]\033[0m"


class PocketWidget(Widget):
    def __init__(self, id: str, parent: 'Widget'):
        super().__init__(id, parent)
        self.entry_price = Decimal("0")
        self.close_price = Decimal("0")
        self.volume = Decimal("0")
        self.status = ""
        self.reason = ""

    def update(self, data: Dict[str, Any]):
        self.entry_price = Decimal(str(data.get('entry_price', self.entry_price)))
        self.close_price = Decimal(str(data.get('close_price'))) if data.get('close_price') else self.close_price
        self.volume = Decimal(str(data.get('volume', self.volume)))
        self.status = data.get('status', self.status)
        self.reason = data.get('reason', "")

    def render(self, current_price: Decimal = Decimal("0")) -> str:
        if self.entry_price == Decimal("0"):
            return "   └─ Pocket | No Data"
        profit_rate = (current_price - self.entry_price) / self.entry_price * 100
        volume_krw = self.volume * self.entry_price
        if self.status == 'closed':
            profit_rate = (self.close_price - self.entry_price) / self.close_price * 100
            profit = (self.close_price - self.entry_price) * self.volume
            reason_str = f"[{self.reason}] " if self.reason else ""
            return f"   └─ Pocket | ✖ Closed {WonColor(profit)}:{RateColor(profit_rate)} - {reason_str}"
        strategy_str = ", ".join([s.render() for s in self.children.values() if isinstance(s, StrategyWidget)])
        return f"   └─ Pocket | ▶ ⛁ {Won(volume_krw)}:{RateColor(profit_rate)} | {strategy_str}"


class AssetWidget(Widget):
    def __init__(self, currency: str):
        super().__init__(currency, None)
        self.ticker = Ticker(currency)
        self.balance = Decimal("0")
        self.avg_buy_price = Decimal("1")
        self.locked = Decimal("0")

    def update(self, data: Dict[str, Any]):
        self.balance = Decimal(data.get('balance', self.balance))
        self.avg_buy_price = Decimal(data.get('avg_buy_price', self.avg_buy_price))
        self.locked = Decimal(data.get('locked', self.locked))

    def won_total(self, current_price: Decimal = Decimal("0")) -> Decimal:
        if self.ticker.currency == "KRW":
            return self.balance + self.locked
        return (self.balance + self.locked) * current_price

    def render(self, current_price: Decimal = Decimal("0")) -> str:
        if self.ticker.currency == "KRW":
            if self.locked > Decimal("0"):
                return f"💰 {WonY(self.balance)} (Lock: {WonR(self.locked)})"
            return f"💰 {WonY(self.balance)}"
        profit_rate = Decimal("0")
        if self.avg_buy_price > Decimal("0"):
            profit_rate = (current_price - self.avg_buy_price) / self.avg_buy_price * 100
        locked_str = ""
        if self.locked > Decimal("0"):
            locked_str = f" (Lock: {WonR(self.locked * current_price)})"
        won_total = self.won_total(current_price)
        profit_str = ""
        if self.balance > Decimal("0"):
            won_profit = (current_price - self.avg_buy_price) * self.balance
            profit_str = f" ({WonColor(won_profit)}:{RateColor(profit_rate)})"
        return f"💰 {WonY(won_total)}{locked_str}{profit_str} "


class OrderWidget(Widget):
    def __init__(self, id: str, parent: 'Widget' = None):
        super().__init__(id, parent)
        self.uuid = id
        self.market = ""
        self.ask_bid = ""
        self.ord_type = ""
        self.price = Decimal("0")
        self.volume = Decimal("0")
        self.state = ""
        self.ticker = None

    def update(self, data: Dict[str, Any]):
        self.uuid = data.get('uuid', self.uuid)
        self.market = data.get('code', "") or data.get('market', "")
        self.ask_bid = data.get('ask_bid', data.get('side', self.ask_bid))
        self.ord_type = data.get('order_type', data.get('ord_type', self.ord_type))
        try:
            pv = data.get('price')
            self.price = Decimal(str(pv)) if pv is not None else Decimal("0")
        except Exception:
            self.price = Decimal("0")
        try:
            vv = data.get('volume')
            self.volume = Decimal(str(vv)) if vv is not None else Decimal("0")
        except Exception:
            self.volume = Decimal("0")
        self.state = data.get('state', self.state)
        self.ticker = Ticker(self.market)

    def render(self, current_price: Decimal = Decimal("0")) -> str:
        total = self.price * self.volume
        sidestr = "BUY" if self.ask_bid == "bid" else "SELL"
        color = "\033[31m" if self.ask_bid == "bid" else "\033[34m"
        fee = total * Decimal("0.0005")
        return f"   └─ Order: {color}{sidestr:<4}\033[0m | {self.ticker.ticker:<10} | Vol: {self.volume:,.4f} | Fee: {fee:,.0f} | Price: {self.price:,.0f}"


class TickerWidget(Widget):
    def __init__(self, ticker: str):
        super().__init__(ticker, None)
        self.coin = Ticker(ticker)
        self.asset = AssetWidget(ticker)
        self.candle = Candle(self.coin.ticker, Decimal("0"))
        self.spinner = Spinner()

    def update(self, data: Dict[str, Any]):
        if 'balance' in data:
            self.asset.update(data)
        if 'trade_price' in data:
            self.candle.update(data['trade_price'])
        if 'price' in data and 'ticker' in data:
            self.candle.update(data['price'])
        self.spinner.next()

    def render(self, current_price: Decimal = Decimal("0")) -> str:
        output = []

        def with_space(line: str) -> str:
            return line + ' ' * max(0, MAX_WIDTH - len(line))

        current_price = self.candle.current_price()
        current_price_dec = Decimal(str(current_price))
        candle_str = f"{self.spinner()} {self.candle.render()} {Won(current_price_dec)}"
        output.append(with_space(f" {self.coin.ticker:11} | {candle_str}"))

        if self.asset.balance > Decimal("0"):
            output.append(with_space(f"   └─ Asset | {self.asset.render(current_price_dec)} "))

        if self.children:
            strategies = [w for w in self.children.values() if isinstance(w, StrategyWidget)]
            orders = [w for w in self.children.values() if isinstance(w, OrderWidget)]
            pockets = [w for w in self.children.values() if isinstance(w, PocketWidget)]
            if strategies:
                strat_str = ", ".join([s.render(current_price_dec) for s in strategies])
                output.append(with_space(f"   └── Strategies: {strat_str}"))
            for order in orders:
                output.append(with_space(order.render(current_price_dec)))
            for pos in pockets:
                output.append(with_space(pos.render(current_price_dec)))

        output.append("-" * MAX_WIDTH)
        return "\n".join(output)


class TUIConsumer:
    """Subscribes to DashboardStateStore and renders ANSI TUI."""

    def __init__(self, state_store):
        self._state_store = state_store
        self.registry: Dict[str, Widget] = {}
        self.log_widget = LogWidget()
        self.registry['log'] = self.log_widget
        self.lock = threading.Lock()
        self._thread = None
        self._running = False
        self.spinner = Spinner()
        self.orderbook_spinner = Spinner()
        self.ticker_spinner = Spinner()
        self.pocket_spinner = Spinner()
        self.strategy_spinner = Spinner()
        self.order_spinner = Spinner()
        state_store.subscribe(self._on_event)

    def start(self):
        self._running = True
        os.system('clear')
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def _on_event(self, event_type: str, payload: dict) -> None:
        with self.lock:
            target_id = None
            widget_type = None

            if event_type == 'ticker.update':
                target_id = Ticker(payload.get('code')).ticker
                widget_type = 'ticker'
            elif event_type == 'log.append':
                self.log_widget.update(payload)
                return
            elif event_type == 'asset.update':
                target_id = Ticker(payload.get('currency')).ticker
                widget_type = 'ticker'
            elif event_type == 'orderbook.update':
                self.orderbook_spinner.next()
                target_id = Ticker(payload.get('code')).ticker
                widget_type = 'ticker'
            elif event_type == 'pocket.update':
                self.pocket_spinner.next()
                target_id = payload.get('id')
                widget_type = 'pocket'
            elif event_type == 'strategy.update':
                self.strategy_spinner.next()
                target_id = payload.get('strategy_id')
                widget_type = 'strategy'
            elif event_type == 'order.update':
                self.order_spinner.next()
                target_id = payload.get('uuid')
                widget_type = 'order'
            elif event_type == 'entity.remove':
                target_id = payload.get('id')
                if target_id and target_id in self.registry:
                    widget = self.registry[target_id]
                    if widget.parent and hasattr(widget.parent, 'children'):
                        if target_id in widget.parent.children:
                            del widget.parent.children[target_id]
                            self._check_and_remove_ticker(widget.parent.id)
                    del self.registry[target_id]
                return

            if not target_id:
                return

            if target_id not in self.registry:
                if event_type in ('ticker.update', 'orderbook.update'):
                    return
                self._create_widget(target_id, widget_type, payload)

            if target_id in self.registry:
                widget = self.registry[target_id]
                widget.update(payload)

                if widget_type == 'order' and widget.state in ['done', 'cancel']:
                    if widget.parent and hasattr(widget.parent, 'children'):
                        widget.parent.children.pop(target_id, None)
                    del self.registry[target_id]
                    if widget.parent:
                        self._check_and_remove_ticker(widget.parent.id)
                    return

                if widget_type in ['asset', 'ticker', 'pocket']:
                    cleanup_id = None
                    if target_id in self.registry and isinstance(self.registry[target_id], TickerWidget):
                        cleanup_id = target_id
                    elif target_id in self.registry and isinstance(self.registry[target_id], PocketWidget):
                        parent = self.registry[target_id].parent
                        if parent and isinstance(parent, TickerWidget):
                            cleanup_id = parent.id
                    if cleanup_id:
                        self._check_and_remove_ticker(cleanup_id)

    def _check_and_remove_ticker(self, ticker_id: str):
        if ticker_id not in self.registry:
            return
        widget = self.registry[ticker_id]
        if not isinstance(widget, TickerWidget):
            return
        if widget.asset.balance > 0 or widget.asset.locked > 0:
            return
        if not widget.children and widget.asset.balance <= 0 and widget.asset.locked <= 0:
            del self.registry[ticker_id]

    def _create_widget(self, id: str, w_type: str, data: Dict[str, Any]):
        widget = None
        if w_type == 'ticker':
            widget = TickerWidget(id)
        elif w_type == 'order':
            t_code = Ticker(data.get('code', "") or data.get('market', "")).ticker
            if t_code not in self.registry:
                self._create_widget(t_code, 'ticker', {'code': t_code})
            parent = self.registry[t_code]
            widget = OrderWidget(id, parent)
            widget.update(data)
            parent.add_child(widget)
        elif w_type == 'pocket':
            ticker = Ticker(data.get('ticker')).ticker
            if ticker not in self.registry:
                self._create_widget(ticker, 'ticker', {'code': ticker})
            parent = self.registry[ticker]
            widget = PocketWidget(id, parent)
            parent.add_child(widget)
        elif w_type == 'strategy':
            pos_id = data.get('pocket_id')
            ticker_code = data.get('ticker')
            if pos_id and pos_id in self.registry:
                parent = self.registry[pos_id]
                widget = StrategyWidget(id, parent)
                parent.add_child(widget)
            elif ticker_code:
                t_code = Ticker(ticker_code).ticker
                if t_code not in self.registry:
                    self._create_widget(t_code, 'ticker', {'code': t_code})
                parent = self.registry[t_code]
                widget = StrategyWidget(id, parent)
                parent.add_child(widget)
            else:
                logger.warning(f"TUI: Strategy {id} has no pocket_id or ticker.")
                return
        if widget and w_type not in ('order', 'pocket', 'strategy'):
            self.registry[id] = widget
        elif widget and id not in self.registry:
            self.registry[id] = widget

    def _total_balance(self) -> Decimal:
        total = Decimal("0")
        for coin in self.registry.values():
            if isinstance(coin, TickerWidget):
                total += coin.asset.won_total(Decimal(str(coin.candle.current_price())))
        return total

    def _run_loop(self):
        last_render = 0
        render_interval = 0.1
        while self._running:
            now = time.time()
            if now - last_render > render_interval:
                self._render()
                last_render = now
            time.sleep(0.05)

    def _render(self):
        snap = self._state_store.snapshot()
        recent_logs = snap['logs'][-self.log_widget.max_logs:]
        self.log_widget.logs = [l + " " * max(0, MAX_WIDTH - len(l)) for l in recent_logs]

        sys.stdout.write("\033[H")
        output = []
        output.append("=" * MAX_WIDTH)
        info = (f"OB:{self.orderbook_spinner.count()} | T:{self.ticker_spinner.count()} | "
                f"P:{self.pocket_spinner.count()} | S:{self.strategy_spinner.count()} | "
                f"O:{self.order_spinner.count()}")
        output.append(f" Coin Strategy Dashboard ({time.strftime('%H:%M:%S')}) {self.spinner()} {info}")
        output.append(f"    Total Asset: 🏦 {WonY(self._total_balance())}")
        output.append("=" * MAX_WIDTH)

        with self.lock:
            tickers = sorted(
                [w for w in self.registry.values() if isinstance(w, TickerWidget)],
                key=lambda x: x.id,
            )
            for widget in tickers:
                output.append(widget.render())

        output.append("")
        output.append("[Recent Logs]")
        output.append(self.log_widget.render())

        sys.stdout.write("\n".join([line + "\033[K" for line in output]) + "\033[J")
        sys.stdout.flush()
