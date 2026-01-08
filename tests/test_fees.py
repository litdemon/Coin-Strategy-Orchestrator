import sys
import os
import unittest
from decimal import Decimal
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from account.dbupbit import DBTradeManager
from account.dtos import OrderDTO

# Configure logging
logging.basicConfig(level=logging.INFO)

class TestFees(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_fees.db"
        # Reset DB
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            
        config = {
            "fees": {
                "KRW": 0.0005 # 0.05%
            }
        }
        self.db = DBTradeManager(self.db_path, config=config)
        self.db.init()
        
        # Initial Deposit
        self.db.add_balance("KRW", Decimal("10000000"))

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_buy_fee(self):
        print("\n=== Test Buy Fee ===")
        ticker = "KRW-BTC"
        price = Decimal("100000000")
        volume = Decimal("0.01")
        expected_trade_amount = price * volume # 1,000,000
        expected_fee = expected_trade_amount * Decimal("0.0005") # 500
        expected_total_cost = expected_trade_amount + expected_fee # 1,000,500
        
        # 1. Place Order
        print(f"Placing Buy Order: {volume} BTC @ {price} KRW")
        order = self.db.create_order(ticker, "bid", "limit", price, volume)
        
        # Verify Lock Amount
        print(f"Locked: {order['locked']}")
        self.assertEqual(order['locked'], expected_total_cost)
        
        # 2. Execute Order
        print("Executing Order...")
        units = [{
            "ask_price": float(price),
            "bid_price": float(price - 1000),
            "ask_size": 1.0,
            "bid_size": 1.0
        }]
        completed = self.db.check_and_execute_orders(ticker, units)
        self.assertIsNotNone(completed)
        self.assertEqual(completed.state, "done")
        
        # 3. Verify Balances
        btc_balance = self.db.get_balance(ticker)
        krw_balance = self.db.get_balance("KRW") # Ticker('KRW').currency is KRW
        print(f"BTC Balance: {btc_balance}")
        print(f"KRW Balance: {krw_balance}")
        
        self.assertEqual(btc_balance, volume)
        self.assertEqual(krw_balance, Decimal("10000000") - expected_total_cost)

    def test_sell_fee(self):
        print("\n=== Test Sell Fee ===")
        ticker = "KRW-BTC"
        
        # Setup: Buy first to have items to sell
        buy_price = Decimal("100000000")
        buy_volume = Decimal("0.01")
        self.db.add_balance(ticker, buy_volume, buy_price)
        
        start_krw = self.db.get_balance("KRW")
        print(f"Start KRW: {start_krw}")
        
        sell_price = Decimal("110000000")
        sell_volume = Decimal("0.01")
        
        expected_trade_amount = sell_price * sell_volume # 1,100,000
        expected_fee = expected_trade_amount * Decimal("0.0005") # 550
        expected_receive = expected_trade_amount - expected_fee # 1,099,450
        
        # 1. Place Sell Order
        print(f"Placing Sell Order: {sell_volume} BTC @ {sell_price} KRW")
        order = self.db.create_order(ticker, "ask", "limit", sell_price, sell_volume)
        
        # Verify Lock (Coin Locked)
        self.assertEqual(order['locked'], sell_volume)
        
        # 2. Execute Order
        print("Executing Order...")
        units = [{
            "ask_price": float(sell_price + 1000),
            "bid_price": float(sell_price),
            "ask_size": 1.0,
            "bid_size": 1.0
        }]
        completed = self.db.check_and_execute_orders(ticker, units)
        self.assertIsNotNone(completed)
        
        # 3. Verify Balances
        btc_balance = self.db.get_balance(ticker)
        krw_balance = self.db.get_balance("KRW")
        print(f"BTC Balance: {btc_balance}")
        print(f"KRW Balance: {krw_balance}")
        
        self.assertEqual(btc_balance, 0)
        self.assertEqual(krw_balance, start_krw + expected_receive)

if __name__ == '__main__':
    unittest.main()
