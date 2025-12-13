
import unittest
from unittest.mock import MagicMock
import sys
import os
import time
from decimal import Decimal

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import Manager
from account.manager import AccountDBManager
from account.dbupbit import DBUpbit

class TestDBAccountFlow(unittest.TestCase):
    def setUp(self):
        # We need to use real file or in-memory DB for AccountDBManager? 
        # In this project AccountDBManager uses "account.db" (global DB_PATH).
        # We should use a test DB.
        self.test_db_path = "test_verify_flow.db"
        
        # Monkey patch DB_PATH or inject it
        # AccountDBManager is hardcoded in manager.py to "account.db"
        # but DBUpbit takes db_path. 
        # However, AccountDBManager instantiates DBUpbit with DB_PATH.
        # We can subclass or mock AccountDBManager to inject our DB.
        
        # For verification, we want to test Manager + AccountDBManager integration.
        # Let's use a temporary DB file path.
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
            
        # We'll use Manager(virtual=True) but we need to hijack its AccountDBManager
        # to use our test DB.
        self.manager = Manager(virtual=True)
        self.manager.dashboard = MagicMock()
        self.manager.messaging = MagicMock()
        # Stub strategy/position manager dependencies if not fully self-contained
        
        # Override account manager with one using our test DB
        # Manager.init() creates self.account_manager.
        # We can re-create it.
        # But Manager.init() also initializes PositionManager with default DB_PATH.
        # We should probably patch DB_PATH at module level or pass it if possible.
        # Given codebase, DB_PATH is global constant in account/manager.py.
        # We can patch it?
        
    def tearDown(self):
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)

    def consume_event(self, event_type, timeout_cycles=10):
        # Helper to skip other events (like myAsset) and find myOrder
        for _ in range(timeout_cycles):
            if self.manager.task_queue.empty():
                return None
            task = self.manager.task_queue.get()
            msg = task["message"]
            if msg.get("type") == event_type:
                return task
            if msg.get("type") == "myOrder":
                print(f"[VERIFY] Ignored myOrder (looking for {event_type}): {msg['uuid']} {msg['state']}")
            else:
                print(f"[VERIFY] Ignored event: {msg.get('type')}")
        return None

    def test_full_order_flow(self):
        # 1. Setup Manager with Test DB
        # We will manually construct dependencies to avoid side effects of global main.py execution
        
        # Custom AccountDBManager with test DB logic
        class TestAccountManager(AccountDBManager):
            def __init__(self, callback, db_path):
                self.manager = DBUpbit(db_path, callback)

        self.manager.account_manager = TestAccountManager(self.manager.on_ws_message, self.test_db_path)
        
        # Mock Strategy Manager
        self.manager.strategy_manager = MagicMock()
        self.manager.strategy_manager.load_strategies_by_position_id.return_value = []
        
        # We also need PositionManager to use the same DB or it won't see changes?
        # Actually PositionManager uses its own DB tables but in same file usually.
        # Let's patch PositionManager to use test_db_path too.
        from src.position_manager import PositionManager
        self.manager.position_manager = PositionManager(self.test_db_path)
        
        # Force initial balance for testing
        self.manager.account_manager.manager.add_balance("KRW", Decimal("1000000"))
        
        # Flush queue to remove myAsset event from add_balance
        while not self.manager.task_queue.empty():
            self.manager.task_queue.get()
        
        # 2. Buy Command
        ticker = "KRW-BTC"
        price = 50000000.0
        volume = 0.001
        
        # Call buy_limit_order
        # This creates 'wait' order
        order = self.manager.account_manager.buy_limit_order(ticker, price, volume)
        self.assertIsNotNone(order)
        self.assertEqual(order.state, "wait")
        self.assertEqual(order.side, "bid")
        
        # Verify myOrder 'wait' event was emitted (callback called)
        # We can check task queue of manager?
        # Manager.task_queue should receive {"cls": self.manager.account_manager, "message": {...}}
        # But Manager.run() loop isn't running. We must manually process queue or check it.
        
        task = self.consume_event("myOrder")
        self.assertIsNotNone(task, "Did not receive myOrder (wait)")
        msg = task["message"]
        
        print(f"[VERIFY] Buy Order Created Event: {msg}")
        self.assertEqual(msg["type"], "myOrder")
        self.assertEqual(msg["state"], "wait")
        self.assertEqual(msg["uuid"], order.uuid)
        
        # Process this event in Manager manually to trigger listeners (like PositionManager if it listened?)
        # PositionManager listens to filled orders ("done"), not wait.
        self.manager.on_task(task["cls"], task["message"])
        
        # 3. Simulate Execution
        # We need to trigger check_order or just call process_order_complete manually?
        # In real virtual mode, check_and_execute_orders is called when orderbook flows in.
        # Let's simulate orderbook update.
        orderbook = [{"ask_price": 49000000.0, "bid_price": 48000000.0}] # Ask price lower than bid limit -> executes
        
        executed_order = self.manager.account_manager.check_order(ticker, orderbook)
        self.assertIsNotNone(executed_order)
        self.assertEqual(executed_order.state, "done")
        
        # Verify 'done' event emitted
        task = self.consume_event("myOrder")
        self.assertIsNotNone(task, "Did not receive myOrder (done)")
        msg = task["message"]
        
        print(f"[VERIFY] Buy Order Executed Event: {msg}")
        self.assertEqual(msg["type"], "myOrder")
        self.assertEqual(msg["state"], "done")
        
        # Process this event -> Should trigger PositionManager.create_position
        self.manager.on_task(task["cls"], task["message"])
        
        # Verify Position Created
        positions = self.manager.position_manager.get_positions(ticker)
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].volume, volume)
        print(f"[VERIFY] Position Created: {positions[0].id}")
        
        # 4. Sell Command
        # Sell half
        sell_volume = volume / 2
        sell_price = 60000000.0
        
        sell_order = self.manager.account_manager.sell_limit_order(ticker, sell_price, sell_volume)
        
        # Consume 'wait' event
        task = self.consume_event("myOrder")
        self.assertIsNotNone(task, "Did not receive Sell myOrder (wait)")
        print(f"[VERIFY] Sell Order Created Event: {task['message']['uuid']}")
        
        # 5. Execute Sell
        orderbook_sell = [{"ask_price": 61000000.0, "bid_price": 62000000.0}] # Bid price higher than ask limit -> executes
        
        executed_sell = self.manager.account_manager.check_order(ticker, orderbook_sell)
        
        # Consume 'done' event
        task = self.consume_event("myOrder")
        self.assertIsNotNone(task, "Did not receive Sell myOrder (done)")
        msg = task["message"]
        print(f"[VERIFY] Sell Order Executed Event: {msg}")
        
        # Process event -> Should trigger PositionManager to Close/Update
        # Current PositionManager logic closes the first position found for the ticker on ANY sell.
        self.manager.on_task(task["cls"], msg)
        
        # Verify Position Closed
        # Re-fetch position
        positions = self.manager.position_manager.get_positions(ticker, only_active=False)
        # Should be closed
        self.assertTrue(positions[0].is_closed)
        print(f"[VERIFY] Position Closed: {positions[0].id}")
        
        # 6. Cancel Test
        # Create another buy order
        cancel_order_obj = self.manager.account_manager.buy_limit_order(ticker, 40000000.0, 0.01)
        # Consume wait
        self.consume_event("myOrder")
        
        # Cancel it
        cancelled = self.manager.account_manager.cancel_order(cancel_order_obj.uuid)
        self.assertEqual(cancelled.state, "cancel")
        
        # Check 'cancel' event
        task = self.consume_event("myOrder")
        self.assertIsNotNone(task, "Did not receive Cancel myOrder")
        msg = task["message"]
        print(f"[VERIFY] Cancel Event: {msg}")
        self.assertEqual(msg["state"], "cancel")
        self.assertEqual(msg["uuid"], cancel_order_obj.uuid)
        
if __name__ == "__main__":
    unittest.main()
