
import unittest
import sqlite3
import os
import sys
from decimal import Decimal
import uuid
import datetime
from unittest.mock import MagicMock

# Adjust path to include project root
sys.path.append(os.getcwd())

import account.account
from account.account import Account, Asset, Balance, OrderDB, OrderInfo

TEST_DB_PATH = "test_account.db"

class TestAccount(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Override DB_PATH for the module
        cls.original_db_path = account.account.DB_PATH
        account.account.DB_PATH = TEST_DB_PATH
        
        # Create Tables
        # Since we can't rely on Asset.init_db (as it might not be implemented fully or correctly in the snippet),
        # we manually create them to be safe, assuming the schema.
        # However, checking tools/db_interface.py, it constructs schema from Pydantic fields.
        # Asset inherits DBInterface. So we can try calling Asset.init_db(TEST_DB_PATH).
        # Same for OrderDB.
        
        # Clean up first
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
            
        Asset.init_db(TEST_DB_PATH)
        OrderDB.init_db(TEST_DB_PATH)

    @classmethod
    def tearDownClass(cls):
        # Restore DB_PATH
        account.account.DB_PATH = cls.original_db_path
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    def setUp(self):
        # Clear Data
        try:
            with sqlite3.connect(TEST_DB_PATH, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM assets")
                cursor.execute("DELETE FROM orders")
                
                # Initial Balance: KRW 10,000,000
                cursor.execute("""
                    INSERT INTO assets (currency, balance, locked, avg_buy_price, avg_buy_price_modified, unit_currency)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, ('KRW', '10000000', '0', '0', 0, 'KRW'))
                conn.commit()
        except Exception as e:
            print(f"Error in setUp: {e}")
            raise

    def test_initialization(self):
        print(f"DEBUG: Account DB_PATH={account.account.DB_PATH}")
        acc = Account(None)
        print(f"DEBUG: Loaded assets keys: {list(acc.balance.assets.keys())}")
        self.assertIsInstance(acc.balance, Balance)
        self.assertEqual(acc.get_balance("KRW"), Decimal("10000000"))

    def test_buy_limit_order(self):
        acc = Account(None)
        # Buy BTC: 50,000,000 KRW/BTC, 0.1 BTC
        price = 50000000.0
        volume = 0.1
        ticker = "KRW-BTC"
        
        order = acc.buy_limit_order(ticker, price, volume)
        
        # Verify Return
        self.assertEqual(order.market, ticker)
        self.assertEqual(order.side, "bid")
        self.assertEqual(order.price, price)
        self.assertEqual(order.volume, volume)
        self.assertEqual(order.state, "wait")
        
        # Verify Memory
        self.assertIn(order.uuid, acc.orders)
        
        # Verify DB
        db_order = OrderDB.get_order(order.uuid)
        self.assertIsNotNone(db_order)
        self.assertEqual(db_order.uuid, order.uuid)

    def test_buy_market_order(self):
        acc = Account(None)
        ticker = "KRW-BTC"
        volume = 100000.0 # Buying 100,000 KRW worth of BTC (market order uses price as volume?)
        # Wait, buy_market_order(ticker, volume) -> volume argument.
        # Is volume amount of coin or price(KRW)?
        # Upbit 'price' order is buy by KRW amount. 'market' usually means buy volume at market price.
        # In Account.buy_market_order code:
        # ord_type='market', price=0.0, volume=volume.
        # This looks like buying specific VOLUME of coin at market price.
        
        order = acc.buy_market_order(ticker, volume)
        self.assertEqual(order.ord_type, "market")
        self.assertIn(order.uuid, acc.orders)
        
        # Verify DB
        db_order = OrderDB.get_order(order.uuid)
        self.assertIsNotNone(db_order)

    def test_execution_limit_buy(self):
        acc = Account(None)
        ticker = "KRW-BTC"
        price = 50000000.0
        volume = 0.1 # Cost 5,000,000
        
        order = acc.buy_limit_order(ticker, price, volume)
        
        # Mock Orderbook
        # Bid order fills if ask_price <= order_price
        orderbook = [{"ask_price": 50000000.0, "bid_price": 49000000.0}]
        
        # Check Order
        filled_order = acc.check_order(ticker, orderbook)
        
        self.assertIsNotNone(filled_order)
        self.assertEqual(filled_order.state, "done")
        self.assertEqual(filled_order.uuid, order.uuid)
        
        # Verify Balance Update
        # KRW should decrease by (price * volume) + fee
        # Fee 0.05%
        cost = Decimal(str(price)) * Decimal(str(volume))
        fee = cost * Decimal("0.0005")
        expected_krw = Decimal("10000000") - cost - fee
        
        # BTC should be + 0.1
        krw_bal = acc.get_balance("KRW")
        btc_bal = acc.get_balance("BTC") # KRW-BTC logic resolves to BTC
        
        self.assertAlmostEqual(krw_bal, expected_krw)
        self.assertEqual(btc_bal, Decimal("0.1"))

    def test_execution_limit_sell(self):
        acc = Account(None)
        ticker = "KRW-BTC"
        
        # Need BTC first
        acc.balance.add_balance(ticker, Decimal("0.1"), Decimal("50000000"))
        
        # Sell 0.1 BTC at 55,000,000
        price = 55000000.0
        volume = 0.1
        
        order = acc.sell_limit_order(ticker, price, volume)
        
        # Mock Orderbook
        # Ask order fills if bid_price >= order_price
        orderbook = [{"ask_price": 56000000.0, "bid_price": 55000000.0}]
        
        filled_order = acc.check_order(ticker, orderbook)
        self.assertIsNotNone(filled_order)
        
        # Verify Balance
        # KRW should increase: 10,000,000 (initial) + (55,000,000 * 0.1) - fee
        # Profit: 5,500,000. Fee: 2,750. Net: 5,497,250.
        # Total KRW: 15,497,250
        
        cost = Decimal(str(price)) * Decimal(str(volume))
        fee = cost * Decimal("0.0005")
        expected_krw = Decimal("10000000") + cost - fee
        
        krw_bal = acc.get_balance("KRW")
        btc_bal = acc.get_balance("BTC")
        
        self.assertAlmostEqual(krw_bal, expected_krw)
        self.assertEqual(btc_bal, Decimal("0"))

if __name__ == '__main__':
    unittest.main()
