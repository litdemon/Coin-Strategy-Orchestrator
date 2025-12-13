import unittest
import sys
import os
import shutil
import time
import uuid
from decimal import Decimal
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from account.dbupbit import DBUpbit
from account.manager import AccountDBManager
from account.repositories import AssetRepository, OrderRepository
from account.exceptions import InsufficientBalanceException
from src.main import Manager
from src.position_manager import PositionManager
import logging

# Configure logging to show info/debug
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(levelname)s: %(message)s')

class TestTradingScenarios(unittest.TestCase):
    def setUp(self):
        self.test_db_path = "test_scenarios.db"
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
            
        # -- 1. Setup Manager with Mocked Dependencies --
        self.manager = Manager()
        self.manager.mqtt_client = MagicMock()
        self.manager.upbit_websocket = MagicMock()
        self.manager.upbit_websocket.codes = []
        self.manager.dashboard = MagicMock() # Mock Dashboard
        self.manager.strategy_manager = None # Mock Strategy Manager


        # -- 2. Hijack AccountDBManager to use TEST DB --
        # DBUpbit with test DB
        self.db_upbit = DBUpbit(db_path=self.test_db_path, callback=self.manager.on_ws_message)
        
        # Manually initialize account_manager
        self.manager.account_manager = AccountDBManager(callback=self.manager.on_ws_message)
        self.manager.account_manager.manager = self.db_upbit
        
        # -- 3. Hijack PositionManager to use TEST DB --
        self.manager.position_manager = PositionManager(db_path=self.test_db_path)
        
        # -- 4. Initial Funding --
        # Add 10,000,000 KRW and 1 BTC for testing
        self.db_upbit.add_balance("KRW", Decimal("10000000"))
        self.db_upbit.add_balance("KRW-BTC", Decimal("1"), Decimal("50000000"))

    def tearDown(self):
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)

    def _process_queue(self):
        """Process all pending tasks in Manager queue"""
        while not self.manager.task_queue.empty():
            task = self.manager.task_queue.get()
            cls = task['cls']
            # print(f"DEBUG: Task cls type: {type(cls)}")
            # print(f"DEBUG: Has process_order_complete? {hasattr(cls, 'process_order_complete')}")
            self.manager.on_task(**task)

    def _execute_limit_buy(self, ticker, price, amount_krw):
        # Calculate volume from amount_krw
        volume = float(amount_krw) / price
        order = self.manager.account_manager.buy_limit_order(ticker, price, volume)
        self._process_queue()
        return order

    def _execute_limit_sell(self, ticker, price, volume):
        order = self.manager.account_manager.sell_limit_order(ticker, price, volume)
        self._process_queue()
        return order

    # --- 1. Buy Order Tests ---

    def test_B01_limit_buy(self):
        """B-01: 지정가 매수 - 주문 생성 및 자산 잠금 확인"""
        print("\n[Test] B-01: Limit Buy Order")
        price = 50000000.0
        amount_krw = 1000000.0 # 1 Million KRW
        
        order = self._execute_limit_buy("KRW-BTC", price, amount_krw)
        
        self.assertEqual(order.state, "wait")
        self.assertEqual(float(order.price), price)
        # Volume check: 1,000,000 / 50,000,000 = 0.02
        expected_vol = 0.02
        self.assertAlmostEqual(float(order.volume), expected_vol)
        
        # Check Locked KRW: (Price * Volume) * 1.0005 (fee)
        # 1,000,000 * 1.0005 = 1,000,500
        asset = self.db_upbit.get_balance("KRW") # Balance is available, need to check locked from Repo
        repo_asset = self.db_upbit.asset_repo.get("KRW")
        self.assertAlmostEqual(float(repo_asset.locked), 1000500.0)
        print(" -> Passed")

    def test_B02_B03_market_buy_position_creation(self):
        """B-02 & B-03: 시장가 매수 / 매수 체결 및 포지션 생성"""
        print("\n[Test] B-02/B-03: Market Buy & Position Creation (Simulated via Limit Execution)")
        # Note: B-02 implies generic market buy, but here we simulate execution via DBUpbit logic.
        # DBUpbit executes market orders immediately if orderbook provided, or Limit orders if matched.
        
        # Place Limit Buy
        order = self._execute_limit_buy("KRW-BTC", 50000000.0, 1000000.0)
        
        # Simulate Market Move (Orderbook) asking 49,000,000 (Lower than limit, so executes)
        orderbook = [{"ask_price": 49000000.0, "bid_price": 48000000.0}]
        
        # Execute
        executed_order = self.db_upbit.check_and_execute_orders("KRW-BTC", orderbook)
        self._process_queue() # Process 'done' event to create position
        
        self.assertIsNotNone(executed_order)
        self.assertEqual(executed_order.state, "done")
        self.assertEqual(executed_order.uuid, order.uuid)
        
        # Verify Position Created
        # We need to manually invoke Manager's handler because verify uses mocked components logic differently?
        # Verify_trading_system calls `manager.on_ws_message` which calls `position_manager.on_order_fill`.
        # DBUpbit callback emits 'myOrder', manager handles it.
        # But here DBUpbit.callback is self.manager.on_ws_message.
        
        # Check PositionManager
        positions = self.manager.position_manager.get_positions("KRW-BTC")
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].volume, float(executed_order.volume))
        print(" -> Passed")

    def test_B04_insufficient_balance(self):
        """B-04: 잔고 부족 매수"""
        print("\n[Test] B-04: Insufficient Balance")
        current_krw = 10000000.0 
        required = 20000000.0 # Exceeds balance
        
        with self.assertRaises(InsufficientBalanceException):
            self._execute_limit_buy("KRW-BTC", 50000000.0, required)
        print(" -> Passed")

    # --- 2. Sell Order Tests ---

    def test_S01_limit_sell(self):
        """S-01: 지정가 매도"""
        print("\n[Test] S-01: Limit Sell Order")
        # We have 1 BTC initial balance
        volume = 0.5
        price = 60000000.0
        
        order = self._execute_limit_sell("KRW-BTC", price, volume)
        
        self.assertEqual(order.state, "wait")
        self.assertEqual(order.side, "ask")
        self.assertEqual(float(order.volume), volume)
        
        # Check Locked BTC
        repo_asset = self.db_upbit.asset_repo.get("BTC")
        self.assertEqual(float(repo_asset.locked), 0.5)
        print(" -> Passed")

    def test_S02_sell_execution_closes_position(self):
        """S-02: 매도 체결 시 포지션 종료"""
        print("\n[Test] S-02: Sell Execution Closes Position")
        # 1. Create Position first (Buy)
        buy_order = self._execute_limit_buy("KRW-BTC", 50000000.0, 1000000.0) # 0.02 BTC
        self.db_upbit.check_and_execute_orders("KRW-BTC", [{"ask_price": 50000000.0, "bid_price": 49000000.0}])
        self._process_queue()
        
        pos = self.manager.position_manager.get_positions("KRW-BTC")[0]
        self.assertFalse(pos.is_closed)
        
        # 2. Sell content of position
        sell_order = self._execute_limit_sell("KRW-BTC", 60000000.0, 0.02)
        
        # 3. Execute Sell
        # Bid price >= Limit price
        self.db_upbit.check_and_execute_orders("KRW-BTC", [{"ask_price": 61000000.0, "bid_price": 60000000.0}])
        self._process_queue()
        
        # Verify Position Closed
        # Manager logic: on_order_fill (ask, done) -> closes position
        # Need to refresh position object from manager
        pos_after = self.manager.position_manager.get_position(pos.id)
        self.assertTrue(pos_after.is_closed)
        print(" -> Passed")
        
    def test_S04_insufficient_asset_sell(self):
        """S-04: 보유 수량 초과 매도"""
        print("\n[Test] S-04: Insufficient Asset Sell")
        # We have 1 BTC + 0.02 (from previous test if run sequentially? No, setUp resets DB)
        # setUp: 1 BTC.
        # Try selling 2 BTC.
        with self.assertRaises(InsufficientBalanceException):
             self._execute_limit_sell("KRW-BTC", 60000000.0, 2.0)
        print(" -> Passed")

    # --- 3. Cancel Order Tests ---
    
    def test_C01_cancel_active_order(self):
        """C-01: 활성 주문 취소"""
        print("\n[Test] C-01: Cancel Active Order")
        order = self._execute_limit_buy("KRW-BTC", 50000000.0, 1000000.0)
        uuid = order.uuid
        
        # Cancel
        cancelled_order = self.manager.account_manager.cancel_order(uuid)
        
        self.assertEqual(cancelled_order.state, "cancel")
        
        # Check Funds Returned (Locked should be 0)
        repo_asset = self.db_upbit.asset_repo.get("KRW")
        self.assertEqual(float(repo_asset.locked), 0.0)
        print(" -> Passed")

    def test_C03_cancel_executed_failure(self):
        """C-03: 체결된 주문 취소 시도 (실패)"""
        print("\n[Test] C-03: Cancel Executed Order Fail")
        # Create and Execute
        order = self._execute_limit_buy("KRW-BTC", 50000000.0, 1000000.0)
        self.db_upbit.check_and_execute_orders("KRW-BTC", [{"ask_price": 50000000.0, "bid_price": 49000000.0}])
        self._process_queue()
        
        # Try Cancel
        # account_manager.cancel_order returns the order object.
        # If order state is 'done', it should return it without changing state to 'cancel'? 
        # Or raise error? AccountDBManager: "if order and order.state == 'wait': ... else return order"
        
        result_order = self.manager.account_manager.cancel_order(order.uuid)
        self.assertEqual(result_order.state, "done")
        print(" -> Passed")

if __name__ == '__main__':
    unittest.main()
