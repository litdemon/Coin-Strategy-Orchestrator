
import unittest
from unittest.mock import MagicMock
import sys
import os
import shutil
import time
from decimal import Decimal

# Add project root to sys.path
sys.path.append(os.getcwd())

from src.main import Manager
from account.manager import AccountDBManager
from account.dbupbit import DBUpbit

class TestTradingSystem(unittest.TestCase):
    def setUp(self):
        self.test_db_path = "verify_system.db"
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
            
        # Initialize Manager with virtual mode
        self.manager = Manager(virtual=True)
        
        # Inject Dependencies Mocks
        self.manager.dashboard = MagicMock()
        self.manager.messaging = MagicMock()
        self.manager.upbit_websocket = MagicMock()
        self.manager.upbit_websocket.codes = []

        # -- Critical: Hijack AccountDBManager to use TEST DB --
        # We need to recreate the account manager with our test DB path.
        # AccountDBManager doesn't accept db_path in init, it uses DBUpbit internally.
        # We can substitute the internal manager.
        self.db_upbit = DBUpbit(db_path=self.test_db_path, callback=self.manager.on_ws_message)
        
        # Manually initialize account_manager since we didn't call manager.init()
        self.manager.account_manager = AccountDBManager(callback=self.manager.on_ws_message)
        
        # Mocking AccountDBManager to use our db_upbit instance
        # Since AccountDBManager creates its own DBUpbit, we must replace it.
        self.manager.account_manager.manager = self.db_upbit
        # Also need to update the repository ref if AccountDBManager exposes them?
        # AccountDBManager delegates most calls.
        
        # -- Critical: Hijack PositionManager to use TEST DB --
        from src.position_manager import PositionManager
        self.manager.position_manager = PositionManager(self.test_db_path)
        
        # -- Critical: Hijack StrategyManager to use TEST DB --
        from strategy.manager import StrategyManager
        self.manager.strategy_manager = StrategyManager(self.test_db_path, self.manager.account_manager)

        # Initial Funds
        self.db_upbit.add_balance("KRW", Decimal("100000000")) # 100M KRW
        
        # Flush queue
        while not self.manager.task_queue.empty():
            self.manager.task_queue.get()

    def tearDown(self):
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)

    def consume_event(self, event_type, state=None, timeout_cycles=10):
        """Helper to find specific event in queue."""
        for _ in range(timeout_cycles):
            if self.manager.task_queue.empty():
                return None
            task = self.manager.task_queue.get()
            msg = task.get("message", {})
            
            if msg.get("type") == event_type:
                if state and msg.get("state") != state:
                    continue
                return task
        return None

    def test_full_system_flow(self):
        print("\n[VERIFY] Starting Full System Flow Verification...")
        
        # 1. Buy Command (Limit)
        ticker = "KRW-BTC"
        price = 50000000.0
        volume = 0.01 # 500,000 KRW
        
        print(f"[1] Placing Buy Limit Order: {ticker} {volume} @ {price}")
        order = self.manager.account_manager.buy_limit_order(ticker, price, volume)
        
        # Check 'wait' event
        task = self.consume_event("myOrder", state="wait")
        self.assertIsNotNone(task, "Failed to receive Order (wait) event")
        print(f" -> Order Created: {task['message']['uuid']}")
        
        # 2. Market Execution (Simulate Orderbook)
        print(f"[2] Simulating Market Price Movement (Orderbook matching)...")
        # Ask price drops to 49M -> Buy limit 50M should execute
        orderbook = [{"ask_price": 49000000.0, "bid_price": 48000000.0}] 
        
        # Trigger check_order manually (in real app, on_orderbook calls this)
        self.manager.account_manager.check_order(ticker, orderbook)
        
        # Check 'done' event
        task = self.consume_event("myOrder", state="done")
        self.assertIsNotNone(task, "Failed to receive Order (done) event")
        print(f" -> Order Executed: {task['message']['uuid']}")
        
        # Process event -> Creates Position
        self.manager.on_task(task["cls"], task["message"])
        
        # Verify Position
        pos = self.manager.position_manager.get_positions(ticker)[0]
        self.assertEqual(pos.volume, volume)
        self.assertEqual(pos.entry_price, 49000000.0) # Executed at best ask? 
        # Check implementation: check_order uses order price or market price?
        # DBUpbit.check_order uses min(order.price, ask_price) for buy? 
        # Actually it usually executes at order price unless logic is refined.
        # Let's trust the logic for now.
        print(f" -> Position Created: {pos.id} Vol:{pos.volume}")
        
        # 3. Dynamic Subscription Check
        # Manager should have subscribed to KRW-BTC upon buy order?
        # Wait, the logic is in process_command. We called buy_limit_order directly.
        # If we use process_command, we can verify that too.
        
        # 4. Sell Command (Market Sell All)
        print(f"[3] Selling All (Market Order)...")
        # Direct call to sell_market_order with full volume
        self.manager.account_manager.sell_market_order(ticker, volume)
        
        # Check 'done' event (Market order executes immediately if implemented that way, 
        # or it creates a market order entry that needs checking?
        # AccountDBManager.sell_market_order usually executes immediately if price passed? 
        # Or creates order with price=0?
        # Check DBUpbit implementation of sell_market_order.
        
        # Assuming it simulates immediate execution or waits for next tick.
        # Let's check logic: DBUpbit.create_order(ord_type='market', price=0) -> executes at 'current_price' passed?
        # Manager.buy_market_order passes price.
        # AccountDBManager.sell_market_order? 
        # It calls create_order(price=0).
        # DBUpbit needs 'current_price' to execute immediately? 
        # Or it waits for 'check_order'.
        
        # If it waits:
        task = self.consume_event("myOrder", state="wait")
        if task:
             print(" -> Market Sell Order Placed (wait)")
             # Execute it with new price
             orderbook_sell = [{"ask_price": 60000000.0, "bid_price": 60000000.0}]
             self.manager.account_manager.check_order(ticker, orderbook_sell)
             task = self.consume_event("myOrder", state="done")
        
        self.assertIsNotNone(task, "Failed to receive Sell Order (done) event")
        print(f" -> Sell Executed")
        
        # Process event -> Closes Position
        self.manager.on_task(task["cls"], task["message"])
        
        # Verify Position Closed
        pos = self.manager.position_manager.get_position(pos.id)
        self.assertTrue(pos.is_closed)
        print(f" -> Position Closed confirm")
        
        print("[PASS] Full System Flow Verified")

if __name__ == "__main__":
    unittest.main()
