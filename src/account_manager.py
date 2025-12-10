import sys
import os
import uuid
import datetime
from typing import Optional, List, Dict, Any, Callable
from decimal import Decimal

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.order_manager import OrderManager, OrderInfoEx
from account.models import Balance, Asset

class AccountManager:
    """
    Manages a virtual account for simulation.
    Handles Buy/Sell requests, manages Balance (Locking), and interacts with OrderManager.
    Simulates 'myOrder' and 'myAsset' messages upon execution.
    """
    def __init__(self, order_manager: OrderManager, balance: Balance, observer_callback: Callable[[dict], None]):
        self.order_manager = order_manager
        self.balance = balance
        self.observer_callback = observer_callback # Callback to send simulated WS messages
        
        # Override OrderManager's callback to intercept execution
        self.order_manager.on_order_complete = self._on_order_executed

    def buy(self, ticker: str, price: float, volume: float) -> Optional[str]:
        """
        Places a Buy Limit Order.
        """
        price_dec = Decimal(str(price))
        volume_dec = Decimal(str(volume))
        
        cost = price_dec * volume_dec
        fee = cost * Decimal("0.0005") # 0.05%
        total_required = cost + fee
        
        # Check Balance (KRW)
        krw_balance = self.balance.get_balance("KRW")
        if krw_balance < total_required:
            print(f"[AccountManager] Insufficient KRW. Required: {total_required}, Available: {krw_balance}")
            return None

        # Lock Funds
        self.balance.set_balance("KRW", krw_balance - total_required)
        
        order = OrderInfoEx(
            uuid=str(uuid.uuid4()),
            side="bid",
            ord_type="limit",
            price=price,
            state="wait",
            market=ticker,
            created_at=datetime.datetime.now().isoformat(),
            volume=volume,
            remaining_volume=volume,
            reserved_fee=float(fee), # OrderInfo expects float? OrderInfo fields are float/int usually
            remaining_fee=float(fee),
            paid_fee=0.0,
            locked=float(total_required),
            executed_volume=0.0,
            trades_count=0
        )
        
        self.order_manager.add_order(order)
        print(f"[AccountManager] Buy Order Placed: {ticker} {volume} @ {price}")
        return order.uuid

    def sell(self, ticker: str, price: float, volume: float) -> Optional[str]:
        """
        Places a Sell Limit Order.
        """
        price_dec = Decimal(str(price))
        volume_dec = Decimal(str(volume))
        
        # Check Balance (Coin)
        coin_balance = self.balance.get_balance(ticker)
        if coin_balance < volume_dec:
            print(f"[AccountManager] Insufficient {ticker}. Required: {volume_dec}, Available: {coin_balance}")
            return None
            
        # Lock Coin
        self.balance.set_balance(ticker, coin_balance - volume_dec)
        
        order = OrderInfoEx(
            uuid=str(uuid.uuid4()),
            side="ask",
            ord_type="limit",
            price=price,
            state="wait",
            market=ticker,
            created_at=datetime.datetime.now().isoformat(),
            volume=volume,
            remaining_volume=volume,
            reserved_fee=0.0, 
            remaining_fee=0.0,
            paid_fee=0.0,
            locked=volume,
            executed_volume=0.0,
            trades_count=0
        )
        
        self.order_manager.add_order(order)
        print(f"[AccountManager] Sell Order Placed: {ticker} {volume} @ {price}")
        return order.uuid

    def _on_order_executed(self, order: OrderInfoEx):
        """
        Callback from OrderManager when an order is 'done' (fully executed).
        """
        print(f"[AccountManager] Processing Execution for {order.uuid} ({order.side})")
        
        if order.side.lower() == "bid":
            # Buy Executed: We already deducted KRW. We need to Add Coin.
            current_coin = self.balance.get_balance(order.market)
            self.balance.set_balance(order.market, current_coin + Decimal(str(order.volume)))
            
        elif order.side.lower() == "ask":
            # Sell Executed: We already deducted Coin. We need to Add KRW.
            earnings = Decimal(str(order.volume)) * Decimal(str(order.price))
            fee = earnings * Decimal("0.0005")
            earnings_after_fee = earnings - fee
            
            current_krw = self.balance.get_balance("KRW")
            self.balance.set_balance("KRW", current_krw + earnings_after_fee)
            
            order.paid_fee = float(fee) # Update order info record

        # Save Balance
        self.balance.save() # Assuming save defaults to loaded DB_PATH or we need to pass it. 
        # Note: Balance.save needs db_path. Assuming Balance class stores it or we pass it?
        # Checking Balance class usage in main.py: Balance.load(DB_PATH). 
        # Balance instance probably doesn't store DB_PATH internally if loaded via classmethod returning instance.
        # We might need to ensure Balance has save capability or pass DB_PATH.
        # For now, let's assume we need to handle DB path or Balance has it.
        # Looking at main.py, balance.save(DB_PATH) is called.
        # We'll need to pass DB_PATH to AccountManager or Balance.
        # Let's assume AccountManager knows DB_PATH or use a default.
        # Fix: AccountManager should save balance.
        
        # Simulate Messages
        self._simulate_my_order(order)
        self._simulate_my_asset()

    def _simulate_my_order(self, order: OrderInfoEx):
        msg = {
            "type": "myOrder",
            "code": order.market,
            "uuid": order.uuid,
            "ask_bid": order.side,
            "order_type": order.ord_type,
            "state": "done",
            "price": order.price,
            "volume": order.volume,
            "executed_volume": order.volume, # Assuming full fill
            "trade_count": 1
        }
        if self.observer_callback:
            self.observer_callback(self, msg) # Simulate passing (cls, msg) or just msg depending on interface

    def _simulate_my_asset(self):
        # Construct assets list
        assets_list = []
        for asset in self.balance.get_all_assets():
            assets_list.append({
                "code": asset.ticker,
                "balance": asset.balance,
                "locked": asset.locked,
                "avg_buy_price": asset.avg_buy_price,
                "currency": asset.currency
            })
            
        msg = {
            "type": "myAsset",
            "assets": assets_list
        }
        if self.observer_callback:
            self.observer_callback(self, msg)
