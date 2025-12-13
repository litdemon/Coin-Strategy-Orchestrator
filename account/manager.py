import sqlite3
from decimal import Decimal
import pyupbit
import datetime
from abc import ABC, abstractmethod
from typing import List, Optional, Any, Callable

# New architecture imports
from account.dbupbit import DBUpbit
from account.dtos import OrderDTO
from account.exceptions import InsufficientBalanceException
from models.orderInfo import OrderInfo # Keep for compatibility if needed, or replace usages. 
# But AccountBase signatures use OrderInfo. I should probably update AccountBase or ignore type hint mismatch for now.
# Or better, alias OrderDTO as OrderInfo if fields match, or change AccountBase.

from tools.ticker import Ticker

# Maintain DB_PATH global for compatibility/patching
DB_PATH = "account.db"

class AccountBase(ABC):
    def __init__(self):
        pass
    
    @abstractmethod
    def get_balance(self, ticker: str) -> Decimal:
        pass
    
    @abstractmethod
    def get_balances(self) -> List[dict]:
        pass

    @abstractmethod
    def buy_limit_order(self, ticker: str, price: float, volume: float) -> Any:
        pass
    
    @abstractmethod
    def buy_market_order(self, ticker: str, volume: float) -> Any:
        pass
    
    @abstractmethod
    def sell_market_order(self, ticker: str, volume: float) -> Any:
        pass

    @abstractmethod
    def sell_limit_order(self, ticker: str, price: float, volume: float) -> Any:
        pass
    
    @abstractmethod
    def get_order(self, ticker: str, state: str = "wait") -> List[Any]:
        pass
    
    @abstractmethod
    def cancel_order(self, uuid: str) -> Any:
        pass

    def on_order_complete(self, order: Any):
        pass
    
    def check_order(self, market: str, orderbook_units: List[dict]) -> Any:
        pass    
    
    def get_orders(self) -> List[dict]:
        pass

class AccountUpbitManager(AccountBase):

    def __init__(self, access_key, secret_key):
        self.upbit = pyupbit.Upbit(access_key, secret_key)

    def get_balance(self, ticker: str) -> Decimal:
        return self.upbit.get_balance(ticker)
    
    def get_balances(self) -> List[dict]:
        return self.upbit.get_balances()

    def get_orders(self) -> List[dict]:
        return self.upbit.get_order()
    
    def add_balance(self, ticker: str, amount: Any, avg_buy_price: Decimal = Decimal(0)):
        return Decimal(0)
    
    def buy_limit_order(self, ticker: str, price: float, volume: float) -> Any:
        return self.upbit.buy_limit_order(ticker, price, volume)
    
    def buy_market_order(self, ticker: str, volume: float) -> Any:
        return self.upbit.buy_market_order(ticker, volume)
    
    def sell_market_order(self, ticker: str, volume: float) -> Any:
        return self.upbit.sell_market_order(ticker, volume)
    
    def sell_limit_order(self, ticker: str, price: float, volume: float) -> Any:
        return self.upbit.sell_limit_order(ticker, price, volume)
    
    def get_order(self, ticker: str, state: str = "wait") -> List[Any]:
        return self.upbit.get_order(ticker, state)
    
    def cancel_order(self, uuid: str) -> Any:
        return self.upbit.cancel_order(uuid)
    
    def on_order_complete(self, order: Any):
        pass
    
    def check_order(self, market: str, orderbook_units: List[dict]) -> Any:
        pass    


class AccountDBManager(AccountBase):
    def __init__(self, callback: Callable[[Any, dict], None]):
        self.manager = DBUpbit(DB_PATH, callback)
    
    def get_balance(self, ticker: str) -> Decimal:
        return self.manager.get_balance(ticker)
    
    def get_balances(self) -> List[dict]:
        return self.manager.get_balances()
    
    def get_orders(self) -> List[dict]:
        # Return all wait orders as dicts
        orders = self.manager.get_open_orders()
        return [order.model_dump() for order in orders]
    
    def get_current_price(self, ticker: str) -> Decimal:
        return pyupbit.get_current_price(ticker)
    
    def get_ohlcv(self, ticker: str, interval: str = "minute1", count: int = 200) -> List[dict]:
        return pyupbit.get_ohlcv(ticker, interval, count)
        
    def get_orderbook(self, ticker: str) -> List[dict]:
        return pyupbit.get_orderbook(ticker)

    def sell_limit_order(self, ticker: str, price: float, volume: float) -> OrderDTO:
        return self.manager.create_order(
            market=ticker,
            side="ask",
            ord_type="limit",
            price=Decimal(str(price)),
            volume=Decimal(str(volume))
        )
    
    def buy_limit_order(self, ticker: str, price: float, volume: float) -> OrderDTO:
        return self.manager.create_order(
            market=ticker,
            side="bid",
            ord_type="limit",
            price=Decimal(str(price)),
            volume=Decimal(str(volume))
        )
    
    def buy_market_order(self, ticker: str, volume: float) -> OrderDTO:
        return self.manager.create_order(
            market=ticker,
            side="bid",
            ord_type="market",
            price=Decimal("0"),
            volume=Decimal(str(volume)) # Volume is amount of coin or price? Manager expects volume.
        )

    def sell_market_order(self, ticker: str, volume: float) -> OrderDTO:
        return self.manager.create_order(
            market=ticker,
            side="ask",
            ord_type="market",
            price=Decimal("0"),
            volume=Decimal(str(volume))
        )
    
    def get_order(self, ticker: str, state: str = "wait") -> List[OrderDTO]:
        return self.manager.get_open_orders(ticker)
    
    def cancel_order(self, uuid: str) -> OrderDTO:
        return self.manager.cancel_order(uuid)

    def on_order_complete(self, order: OrderDTO):
        self.manager.process_order_complete(order)
    
    def check_order(self, market: str, orderbook_units: List[dict]) -> Optional[OrderDTO]:
        return self.manager.check_and_execute_orders(market, orderbook_units)
    
    # Expose balance object for backward compatibility if tests access .balance.assets
    # But new architecture doesn't have Balance class.
    # verify/test_account.py accesses acc.balance.assets.
    # I should probably update the test or provide a property.
    @property
    def balance(self):
        # Mocking compatibility object
        class BalanceCompat:
            def __init__(self, manager):
                self.manager = manager
            @property
            def assets(self):
                # Return dict of {currency: AssetDTO}
                # But AssetDTO is not mutable like old Asset.
                # Tests might assume mutability or direct access.
                # This is tricky. I'll update the test instead.
                all_assets = self.manager.asset_repo.get_all()
                return {asset.currency: asset for asset in all_assets}
            
            def add_balance(self, ticker, amount, avg_buy_price=0):
                 return self.manager.add_balance(ticker, amount, avg_buy_price)

        return BalanceCompat(self.manager)
    
    @property
    def orders(self):
        # account.orders was a dict {uuid: OrderDB}.
        # Tests access acc.orders[uuid].
        # I should provide a property that builds this dict on fly.
        all_orders = self.manager.get_open_orders()
        return {order.uuid: order for order in all_orders}


