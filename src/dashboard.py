import queue
import threading
import time
import os
import sys
from typing import Dict, Any, List

class Dashboard:
    def __init__(self):
        self.queue = queue.Queue()
        self.running = False
        self.data: Dict[str, Dict[str, Any]] = {} 
        # Structure: { ticker: { 'price': float, 'candle': str, 'positions': [ {str details} ] } }
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

    def update_ticker(self, ticker: str, price: float, candle_str: str):
        self.queue.put({
            'type': 'ticker',
            'ticker': ticker,
            'price': price,
            'candle': candle_str
        })

    def update_positions(self, ticker: str, positions_summary: List[str]):
        """
        positions_summary: List of strings, each describing a position.
        """
        self.queue.put({
            'type': 'positions',
            'ticker': ticker,
            'data': positions_summary
        })

    def log(self, message: str):
        self.queue.put({
            'type': 'log',
            'message': message
        })

    def _run_loop(self):
        # Clear screen initially
        os.system('clear')
        
        last_render = 0
        render_interval = 0.1 # 10 FPS max
        
        logs = []
        max_logs = 5

        while self.running:
            try:
                # Process all available items in queue
                while True:
                    try:
                        item = self.queue.get_nowait()
                        
                        if item['type'] == 'ticker':
                            ticker = item['ticker']
                            with self.lock:
                                if ticker not in self.data:
                                    self.data[ticker] = {'positions': []}
                                self.data[ticker]['price'] = item['price']
                                self.data[ticker]['candle'] = item['candle']
                                
                        elif item['type'] == 'positions':
                            ticker = item['ticker']
                            with self.lock:
                                if ticker not in self.data:
                                    self.data[ticker] = {}
                                self.data[ticker]['positions'] = item['data']

                        elif item['type'] == 'log':
                            logs.append(item['message'])
                            if len(logs) > max_logs:
                                logs.pop(0)

                    except queue.Empty:
                        break
                
                # Render if enough time passed
                now = time.time()
                if now - last_render > render_interval:
                    self._render(logs)
                    last_render = now

                time.sleep(0.01)
                
            except Exception as e:
                # Fallback log
                with open("dashboard_error.log", "a") as f:
                    f.write(f"{e}\n")

    def _render(self, logs: List[str]):
        # Move cursor to top-left
        sys.stdout.write("\033[H")
        
        output = []
        output.append("=" * 80)
        output.append(f" Coin Strategy Dashboard ({time.strftime('%H:%M:%S')})")
        output.append("=" * 80)
        
        with self.lock:
            tickers = sorted(self.data.keys())
            for ticker in tickers:
                info = self.data[ticker]
                price = info.get('price', 0)
                candle = info.get('candle', "")
                positions = info.get('positions', [])
                
                # Header Row
                output.append(f" {ticker:<10} | {price:>12,.0f} | {candle}")
                
                # Position Rows
                if positions:
                    for pos_str in positions:
                        output.append(f"   └── {pos_str}")
                else:
                    output.append(f"   └── No Active Positions")
                
                output.append("-" * 80)

        # Logs area
        output.append("")
        output.append("[Recent Logs]")
        for log in logs:
            output.append(f" > {log}")
            
        # Fill rest of screen to clear old content (optional/simple approach)
        # Using ANSI clear to end of screen might be better: \033[J
        sys.stdout.write("\n".join([line + "\033[K" for line in output]) + "\033[J")
        sys.stdout.flush()
