import queue
import threading
import time
import os
import sys
from typing import Dict, Any, List
import logging  
from tools.candle import Candle
import pyupbit
from tools.ticker import Ticker

logger = logging.getLogger(__name__)

class LogWidget:
    def __init__(self):
        self.logs = []
        self.max_logs = 5
    
    def update_log(self, message: str):
        self.logs.append(message)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
    
    def render(self) -> List[str]:
        return self.logs

class StrategyWidget:
    def __init__(self, name: str, state: str):
        self.name = name
        self.state = state
    
    def render(self) -> str:
        if self.state:
            return f"{self.name}({self.state})"
        return f"{self.name}"

class PositionWidget:
    def __init__(self, pid: str, strategies: List[Dict[str, str]], entry_price: float, volume: float):
        self.id = pid
        self.strategies = [StrategyWidget(s.get('name', 'Unknown'), s.get('state', '')) for s in strategies]
        self.entry_price = entry_price
        self.volume = volume
    
    def render(self, current_price: float) -> str:
        # Strategy String
        strategy_str = ", ".join([s.render() for s in self.strategies])
        
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

        return f"   └── ID:{pid_short}.. | {strategy_str} | PnL: {profit_rate_str} | Vol: {volume_krw:,.0f}"


class TickerWidget:
    
    def __init__(self, ticker: str):
        self.coin = Ticker(ticker)
        self.positions = []
        self.amount = 0
        self.avg_buy_price = 0.0
        ohlcv = pyupbit.get_ohlcv(self.coin.ticker, interval="day")
        if ohlcv is not None and not ohlcv.empty:
            self.candle : Candle = Candle(self.coin.ticker, ohlcv['close'].iloc[-1])
            self.candle.reset(ohlcv)
        else:
            # Fallback if no data
            self.candle : Candle = Candle(self.coin.ticker, 0.0)

    def update_candle(self, price: float):
        self.candle.update(price)

    def update_ticker(self, price: float):
        self.candle.update(price)

    def update_positions(self, positions_data: List[Dict[str, Any]]):
        self.positions = [] 
        for p_data in positions_data:
            # p_data expects: id, entry_price, volume, strategies
            widget = PositionWidget(
                pid=p_data.get('id', '??'),
                strategies=p_data.get('strategies', []),
                entry_price=p_data.get('entry_price', 0),
                volume=p_data.get('volume', 0)
            )
            self.positions.append(widget)
    
    def update_balance(self, balance_info: Dict[str, Any]):
        """
        balance_info: dict containing 'balance', 'avg_buy_price', etc.
                      or float/int if just amount is passed (backward compatibility)
        """
        if isinstance(balance_info, (int, float)):
            self.amount = float(balance_info)
            self.avg_buy_price = 1
        elif isinstance(balance_info, dict):
            self.amount = float(balance_info.get('amount', 0))
            self.avg_buy_price = float(balance_info.get('avg_buy_price', 0))
            # Upbit sometimes returns avg_buy_price as string
        else:
            self.amount = 0.0
            self.avg_buy_price = 0.0

    def render(self) -> List[str]:
        output = []
        
        current_price = self.candle.current_price()
        
        # Calculate Amount (Invested KRW)
        amount = self.amount * self.avg_buy_price
        
        # Calculate Profit % (Evaluation profit based on avg buy price)
        if self.avg_buy_price > 0 and current_price > 0:
            profit_rate = (current_price - self.avg_buy_price) / self.avg_buy_price * 100
            if profit_rate < 0:
                profit_str = f"\033[34m{profit_rate:7.2f}%\033[0m"
            else:
                profit_str = f"\033[31m{profit_rate:7.2f}%\033[0m"
        else:
            profit_str = "0.00%"

        # Header with requested format: Amount | Profit % | Current Price | Candle
        # User requested: "amount(balance*buy_price)| profit persent | current_price | candle"
        
        header = f" {self.coin.ticker:<10} | {amount:>12,.0f} | {profit_str:>8} | {current_price:>12,.0f} | {self.candle.render()}"
        output.append(header)
        
        # Positions
        if self.positions:
            for pos_widget in self.positions:
                output.append(pos_widget.render(current_price))
        else:
            output.append(f"   └── No Active Positions")
        
        output.append("-" * 90)
        return output

class Dashboard:
    def __init__(self):
        self.queue = queue.Queue()
        self.running = False
        self.widgets: Dict[str, TickerWidget] = {}
        self.log_widget = LogWidget()
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

    def update_ticker(self, message: dict):
        if message.get('code', '') == 'KRW':
            raise ValueError("Invalid message: KRW")
        if message.get('type', '') != 'ticker':
            raise ValueError(f"Invalid message type: {message['type']}")
        
        t = Ticker(message.get('code', ''))
        self.queue.put({
            'type': 'ticker',
            'ticker': t.ticker,
            'price': message.get('trade_price', 0)
        })

    def update_balance(self, balance: dict):
        t = Ticker(balance['currency'])
        self.queue.put({
            'type': 'balance',
            'ticker': t.ticker,
            'amount': balance['balance'],
            'avg_buy_price': balance['avg_buy_price']
        })

    def log(self, message: str):
        self.queue.put({
            'type': 'log',
            'message': message
        })
        logger.info(message)


    def on_ticker(self, message: dict):
        ticker = message.get('ticker', '')
        price = message.get('price', 0)
        with self.lock:
            if ticker not in self.widgets.keys():
                return
                
            self.widgets[ticker].update_ticker(price)

    def on_balance(self, item: dict):
        ticker = item.get('ticker', '')
        with self.lock:
            if ticker not in self.widgets.keys():
                self.widgets[ticker] = TickerWidget(ticker)
            self.widgets[ticker].update_balance(item)

    def on_log(self, item: dict):
        self.log_widget.update_log(item['message'])

    def on_positions(self, item: dict):
        ticker = item.get('ticker', '')
        with self.lock:
            if ticker not in self.widgets:
                return
            self.widgets[ticker].update_positions(item['data'])


    def _run_loop(self):
        # Clear screen initially
        os.system('clear')
        
        last_render = 0
        render_interval = 0.1 # 10 FPS max
        
        message_count = {"ticker":0, "positions":0, "balance":0, "log":0, "loop":0}
        
        while self.running:
            try:
                # Process all available items in queue
                while True:
                    try:
                        item = self.queue.get_nowait()
                        
                        if item['type'] == 'ticker':
                            self.on_ticker(item)
                            message_count['ticker'] += 1
                        elif item['type'] == 'positions':
                            self.on_positions(item)
                            message_count['positions'] += 1
                        elif item['type'] == 'balance':
                            self.on_balance(item)
                            message_count['balance'] += 1
                        elif item['type'] == 'log':
                            self.on_log(item)
                            message_count['log'] += 1
                        else:
                            logger.error(f"Unknown queue item type: {item['type']}")

                    except queue.Empty:
                        break
                    except Exception as e:
                        logger.error(f"Error processing queue item: {e}")
                

                if message_count['loop'] % 100 == 0:
                    logger.info(f"Message Count: {message_count}")
                # Render if enough time passed
                now = time.time()
                if now - last_render > render_interval:
                    self._render(self.log_widget.render())
                    last_render = now

                time.sleep(0.1)
                message_count['loop'] += 1
                
            except Exception as e:
                # Fallback log
                with open("dashboard_error.log", "a") as f:
                    f.write(f"ERROR: {e}\n")

    def _render(self, logs: List[str]):
        # Move cursor to top-left
        sys.stdout.write("\033[H")
        
        output = []
        output.append("=" * 80)
        output.append(f" Coin Strategy Dashboard ({time.strftime('%H:%M:%S')})")
        output.append("=" * 80)
        
        with self.lock:
            # Sort tickers for consistent display
            sorted_tickers = sorted(self.widgets.keys())
            for ticker in sorted_tickers:
                widget = self.widgets[ticker]
                output.extend(widget.render())

        # Logs area
        output.append("")
        output.append("[Recent Logs]")
        for log in logs:
            output.append(f" > {log}")
            
        # Fill rest of screen
        sys.stdout.write("\n".join([line + "\033[K" for line in output]) + "\033[J")
        sys.stdout.flush()
