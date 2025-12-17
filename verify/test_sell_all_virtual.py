
import unittest
import sys
import os
import shutil
import time
from decimal import Decimal
import logging

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import Manager
from account.manager import AccountDBManager
from strategy.models import StrategyStatus
from tools.ticker import Ticker
import account.manager
import src.main

# Patch MessagingFactory global import for referencing in setUp/tearDown
from messaging.factory import MessagingFactory
from messaging.interface import MessagingClient

# Test DB Path
TEST_DB = "test_sell_all.db"

class TestSellAllVirtual(unittest.TestCase):
    def setUp(self):
        # Clean up previous test db
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
            
        # Patch DB Paths globally for the modules
        account.manager.DB_PATH = TEST_DB
        src.main.DB_PATH = TEST_DB
        
        # Initialize Manager in Virtual Mode
        config = {
            "messaging": {
                "broker_type": "mqtt",
                "mqtt": {
                    "host": "test", # Dummy
                    "port": 1883,
                    "client_id": "test"
                }
            },
            "account": {
                "initial_balance": 10000000 # 10M KRW
            }
        }
        
        # Patch MessagingFactory.create_client to return Mock
        from messaging.factory import MessagingFactory
        from messaging.interface import MessagingClient
        
        self.original_create = MessagingFactory.create_client
        self.mock_messaging = type('MockMessaging', (MessagingClient,), {
            'connect': lambda s: True,
            'subscribe': lambda s, t, c: None,
            'unsubscribe': lambda s, t: None, # Added missing method
            'publish': lambda s, t, p: None,
            'disconnect': lambda s: None,
            'start': lambda s: None,
            'stop': lambda s: None
        })()
        MessagingFactory.create_client = lambda config: self.mock_messaging
        
        # Init Manager
        self.manager = Manager(virtual=True)
        self.manager.init(config=config)
        
    def tearDown(self):
        self.manager.stop()
        MessagingFactory.create_client = self.original_create
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
            
    def test_sell_all(self):
        # 1. Setup: Buy dummy coin to create Position, Strategy, Balance
        ticker = "KRW-BTC"
        price = 100000000.0
        volume = 0.01 # 1M KRW worth
        
        print(f"Creating position for {ticker}...")
        
        # Manually trigger buy via AccountManager (simulates order fill)
        # 1. Buy Order
        # Access inner manager for add_balance
        self.manager.account_manager.manager.add_balance("KRW", Decimal("10000000")) 
        self.manager.account_manager.buy_limit_order(ticker, Decimal(price), Decimal(volume))
        
        # 2. Simulate Order Fill (to trigger Position creation)
        
        # A. Create Balance
        self.manager.account_manager.manager.add_balance(ticker, Decimal(volume), Decimal(price))
        
        # B. Create Position
        pos = self.manager.position_manager.create_position(ticker, Decimal(price), Decimal(volume))
        
        # C. Create Strategy
        from strategy.models import StrategyContext, StrategyConfig
        from strategy.base import StrategyBase
        
        # Mock strategy class
        class MockStrategy(StrategyBase):
            def on_tick(self, price): return None
            def get_state(self): return {}
            def restore_state(self, state): pass
            
        self.manager.strategy_manager.register_strategy("mock", MockStrategy)
        sid = self.manager.strategy_manager.create_strategy(
            type_name="mock",
            ticker=ticker,
            budget=Decimal(volume),
            config={"strategy_type": "mock"}, # Added required field
            position_id=pos.id
        )
        
        # Verify Setup
        balances = self.manager.account_manager.get_balances()
        btc_balance = next((b for b in balances if b['currency'] == 'BTC'), None)
        self.assertIsNotNone(btc_balance, "Setup failed: No BTC balance")
        self.assertTrue(float(btc_balance['balance']) > 0, "Setup failed: BTC balance is 0")
        
        self.assertIn(pos.id, self.manager.position_manager.positions, "Setup failed: No Position")
        self.assertIn(sid, self.manager.strategy_manager.strategies, "Setup failed: No Strategy")
        
        print("Setup complete. Executing Sell All...")
        
        # 2. Execute command "Sell All"
        # We call process_command directly
        
        # Mock current price for market sell estimate
        self.manager.current_prices.update(ticker, price)
        
        cmd_data = {
            "action": "sell",
            "ticker": ticker,
            "volume": -1, # Sell All
            "price": 0 # Market
        }
        
        self.manager.process_command(f"trading/command/{time.time()}", cmd_data)
        
        # Simulate Sell Order Fill
        # The Sell Market Order is in 'wait' state, holding funds in 'locked'.
        # We need to fill it to clear the locked balance.
        orders = self.manager.account_manager.get_order(ticker, state='wait')
        # Filter for SELL ('ask') order
        sell_orders = [o for o in orders if o.side == 'ask']
        self.assertTrue(len(sell_orders) > 0, "No Sell order found")
        sell_order = sell_orders[0]
        
        # Complete it
        self.manager.account_manager.on_order_complete(sell_order)
         
        # 3. Verify Outcomes
        
        # A. Balance should be gone (or 0)
        balances_after = self.manager.account_manager.get_balances()
        btc_balance_after = next((b for b in balances_after if b['currency'] == 'BTC'), None)
        # get_balances should filter 0
        if btc_balance_after:
             print(f"BTC Balance remaining: {btc_balance_after}")
             # It might be very small dust? Or should be exactly 0 if logic works.
             # AccountDBManager sub_balance logic: new_bal = bal - amount.
             # If amount == bal, new_bal = 0.
             self.assertEqual(float(btc_balance_after.get('balance', 0)) + float(btc_balance_after.get('locked', 0)), 0, "Balance not zeroed")
        else:
             print("BTC Balance is gone (Correctly filtered)")
             
        # B. Position should be archived
        self.assertNotIn(pos.id, self.manager.position_manager.positions, "Position still in Active memory")
        
        # Check Archive Table
        import sqlite3
        with sqlite3.connect(TEST_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM positions_archive WHERE id = ?", (pos.id,))
            row = cursor.fetchone()
            self.assertIsNotNone(row, "Position not found in Archive DB")
            
            cursor.execute("SELECT * FROM positions WHERE id = ?", (pos.id,))
            row_active = cursor.fetchone()
            self.assertIsNone(row_active, "Position still in Active DB")
            
        # C. Strategy should be archived
        self.assertNotIn(sid, self.manager.strategy_manager.strategies, "Strategy still in Active memory")
        
        with sqlite3.connect(TEST_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM strategies_archive WHERE strategy_id = ?", (sid,))
            row = cursor.fetchone()
            self.assertIsNotNone(row, "Strategy not found in Archive DB")
            
            cursor.execute("SELECT * FROM strategies WHERE strategy_id = ?", (sid,))
            row_active = cursor.fetchone()
            self.assertIsNone(row_active, "Strategy still in Active DB")
            
        print("Verification Passed!")

if __name__ == '__main__':
    unittest.main()
