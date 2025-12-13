import unittest
import os
import sys
sys.path.append(os.getcwd())
import time
from decimal import Decimal
from unittest.mock import MagicMock
from account.dbupbit import DBUpbit
from account.manager import AccountDBManager

class TestTradingErrors(unittest.TestCase):
    def setUp(self):
        self.test_db_path = "test_error_cases.db"
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
        
        self.callback_mock = MagicMock()
        self.db_upbit = DBUpbit(self.test_db_path, self.callback_mock)
        self.account_manager = AccountDBManager(self.callback_mock)
        self.account_manager.manager = self.db_upbit # Inject test DB instance
        
        # Initial Funding
        self.db_upbit.add_balance("KRW", Decimal("1000000")) # 1M KRW
        self.db_upbit.add_balance("KRW-BTC", Decimal("0.1"), Decimal("50000000")) # 0.1 BTC @ 50M (Value 5M)

    def tearDown(self):
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)

    def test_buy_insufficient_balance(self):
        print("\n[TEST] Buy Insufficient Balance")
        # Try to buy 1 BTC @ 50M (Requires 50M KRW, have 1M)
        try:
            self.account_manager.buy_limit_order("KRW-BTC", 50000000, 1.0)
            print("FAIL: Order was created despite insufficient balance.")
            self.fail("Should have raised InsufficientBalanceException")
        except Exception as e:
            print(f"PASS: Caught expected exception: {e}")
            # Verify no order created
            orders = self.db_upbit.get_open_orders()
            self.assertEqual(len(orders), 0)

    def test_sell_insufficient_volume(self):
        print("\n[TEST] Sell Insufficient Volume")
        # Try to sell 1.0 BTC (Have 0.1)
        try:
            self.account_manager.sell_limit_order("KRW-BTC", 60000000, 1.0)
            print("FAIL: Order was created despite insufficient volume.")
            self.fail("Should have raised InsufficientBalanceException")
        except Exception as e:
            print(f"PASS: Caught expected exception: {e}")
            # Verify no order created
            orders = self.db_upbit.get_open_orders()
            self.assertEqual(len(orders), 0)

    def test_cancel_invalid_uuid(self):
        print("\n[TEST] Cancel Invalid UUID")
        result = self.account_manager.cancel_order("invalid-uuid")
        # Should return None or similar, not crash
        print(f"Cancel Validation Result: {result}")
        self.assertIsNone(result)

    def test_locking_funds(self):
        print("\n[TEST] Funds Locking")
        # Buy 0.01 BTC @ 10M = 100,000 KRW
        price = 10000000
        vol = 0.01
        cost = price * vol
        
        # Before
        balance_before = self.db_upbit.get_balance("KRW") # 1,000,000
        
        self.account_manager.buy_limit_order("KRW-BTC", price, vol)
        
        # After
        asset = self.db_upbit.asset_repo.get("KRW")
        print(f"Balance: {asset.balance}, Locked: {asset.locked}")
        
        # Expectation: 
        # Option A: Balance decreases by cost (simple model)
        # Option B: Balance stays same, Locked increases by cost (more accurate)
        # Assuming we want Option B or A, checking if 'Available' is reduced.
        # Since get_balance returns `balance`, if we use locking, `balance` might include locked?
        # Usually get_balance returns 'total' or 'available'?
        # In Upbit API, 'balance' is available, 'locked' is separate.
        # Let's verify what our DB does.
        
        # If implementation is correct, `asset.balance` (available) should decrease OR `asset.locked` should increase.
        # Let's assume we want valid locking: Available decreases, Locke increases.
        
        # CURRENTLY (Broken state): Nothing changes.
        if asset.locked == 0 and asset.balance == balance_before:
             print("FAIL: Funds were not locked.")
             self.fail("Funds were not locked")

    def test_buy_market_insufficient(self):
        print("\n[TEST] Buy Market Insufficient Balance")
        # Mock get_current_price to return 50M
        self.account_manager.get_current_price = MagicMock(return_value=Decimal("50000000"))
        
        # Try to buy 1 BTC Market (Cost 50M) - Have 1M
        try:
            self.account_manager.buy_market_order("KRW-BTC", 1.0)
            print("FAIL: Market Order was created despite insufficient balance.")
            self.fail("Should have raised InsufficientBalanceException")
        except Exception as e:
            print(f"PASS: Caught expected exception: {e}")
            orders = self.db_upbit.get_open_orders()
            self.assertEqual(len(orders), 0)

if __name__ == "__main__":
    unittest.main()
