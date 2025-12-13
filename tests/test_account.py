
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
from account.account import Account
# New imports
from account.dtos import OrderDTO

TEST_DB_PATH = "test_account.db"

class TestAccount(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Override DB_PATH for the module
        cls.original_db_path = account.account.DB_PATH
        account.account.DB_PATH = TEST_DB_PATH
        
    @classmethod
    def tearDownClass(cls):
        # Restore DB_PATH
        account.account.DB_PATH = cls.original_db_path
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    def setUp(self):
        # Clear Data
        # Re-initialize DB for each test to ensure clean state
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
            
        # Initialize via Account (which inits Manager -> init_db)
        self.acc = Account(None)
        
        # Insert Initial Balance manually or via manager
        # Using Account's balance compatibility property or manager directly
        # acc.manager.asset_repo.init_db() is called in __init__
        
        with sqlite3.connect(TEST_DB_PATH) as conn:
            # We need to ensure tables exist if we deleted the file
            # Account() init above created them.
            cursor = conn.cursor()
            cursor.execute("DELETE FROM assets")
            cursor.execute("DELETE FROM orders")
            
            # Initial Balance: KRW 10,000,000
            cursor.execute("""
                INSERT INTO assets (currency, balance, locked, avg_buy_price, avg_buy_price_modified, unit_currency)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ('KRW', 10000000, 0, 0, 0, 'KRW'))
            conn.commit()

    def test_initialization(self):
        print(f"DEBUG: Account DB_PATH={account.account.DB_PATH}")
        acc = Account(None)
        
        # Test backward compatibility or new API
        # acc.balance might be a Compat object now
        print(f"DEBUG: Loaded balance: {acc.get_balance('KRW')}")
        
        self.assertEqual(acc.get_balance("KRW"), Decimal("10000000"))

    def test_buy_limit_order(self):
        acc = Account(None)
        price = 50000000.0
        volume = 0.1
        ticker = "KRW-BTC"
        
        order = acc.buy_limit_order(ticker, price, volume)
        
        # Verify Return (OrderDTO)
        self.assertEqual(order.market, ticker)
        self.assertEqual(order.side, "bid")
        self.assertEqual(order.price, Decimal(str(price)))
        self.assertEqual(order.volume, Decimal(str(volume)))
        self.assertEqual(order.state, "wait")
        
        # Verify Memory/DB (via compatibility property or direct manager)
        self.assertIn(order.uuid, acc.orders)
        
        # Verify DB directly
        repo_order = acc.manager.order_repo.get(order.uuid)
        self.assertIsNotNone(repo_order)
        self.assertEqual(repo_order.uuid, order.uuid)

    def test_buy_market_order(self):
        acc = Account(None)
        ticker = "KRW-BTC"
        volume = 100000.0 
        
        order = acc.buy_market_order(ticker, volume)
        self.assertEqual(order.ord_type, "market")
        self.assertIn(order.uuid, acc.orders)
        
        db_order = acc.manager.order_repo.get(order.uuid)
        self.assertIsNotNone(db_order)

    def test_execution_limit_buy(self):
        acc = Account(None)
        ticker = "KRW-BTC"
        price = 50000000.0
        volume = 0.1 
        
        order = acc.buy_limit_order(ticker, price, volume)
        
        orderbook = [{"ask_price": 50000000.0, "bid_price": 49000000.0}]
        
        filled_order = acc.check_order(ticker, orderbook)
        
        self.assertIsNotNone(filled_order)
        self.assertEqual(filled_order.state, "done")
        self.assertEqual(filled_order.uuid, order.uuid)
        
        cost = Decimal(str(price)) * Decimal(str(volume))
        fee = cost * Decimal("0.0005")
        expected_krw = Decimal("10000000") - cost - fee
        
        krw_bal = acc.get_balance("KRW")
        btc_bal = acc.get_balance("BTC") 
        
        self.assertAlmostEqual(krw_bal, expected_krw)
        self.assertEqual(btc_bal, Decimal("0.1"))

    def test_execution_limit_sell(self):
        acc = Account(None)
        ticker = "KRW-BTC"
        
        # Need BTC first
        acc.balance.add_balance(ticker, Decimal("0.1"), Decimal("50000000"))
        
        price = 55000000.0
        volume = 0.1
        
        order = acc.sell_limit_order(ticker, price, volume)
        
        orderbook = [{"ask_price": 56000000.0, "bid_price": 55000000.0}]
        
        filled_order = acc.check_order(ticker, orderbook)
        self.assertIsNotNone(filled_order)
        
        cost = Decimal(str(price)) * Decimal(str(volume))
        fee = cost * Decimal("0.0005")
        expected_krw = Decimal("10000000") + cost - fee
        
        krw_bal = acc.get_balance("KRW")
        btc_bal = acc.get_balance("BTC")
        
        self.assertAlmostEqual(krw_bal, expected_krw)
        self.assertEqual(btc_bal, Decimal("0"))

if __name__ == '__main__':
    unittest.main()
