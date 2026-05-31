import sqlite3
from decimal import Decimal
import pyupbit
import datetime
from abc import ABC, abstractmethod
from typing import List, Optional, Any, Callable
import logging

# New architecture imports
from account.dbupbit import DBTradeManager
from account.dtos import OrderDTO
from account.exceptions import InsufficientBalanceException
from tools.ticker import Ticker

logger = logging.getLogger(__name__)

class AccountBase(ABC):
    def __init__(self):
        pass
    
    @abstractmethod
    def get_balance(self, ticker: str) -> Decimal:
        pass

    @abstractmethod
    def get_asset_balance(self, ticker: str) -> dict:
        """Get full asset balance info including avg_buy_price"""
        pass
    
    @abstractmethod
    def get_balances(self) -> List[dict]:
        pass

    @abstractmethod
    def buy_limit_order(self, ticker: str, price: Decimal, volume: Decimal) -> Any:
        pass
    
    @abstractmethod
    def buy_market_order(self, ticker: str, volume: Decimal) -> Any:
        pass
    
    @abstractmethod
    def sell_market_order(self, ticker: str, volume: Decimal) -> Any:
        pass

    @abstractmethod
    def sell_limit_order(self, ticker: str, price: Decimal, volume: Decimal) -> Any:
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

class AccountDBManager(AccountBase):
    def __init__(self, callback: Callable[[Any, dict], None], config: dict = None, db_path: str = "account.db"):
        super().__init__()
        self.config = config
        self.manager = DBTradeManager(db_path, callback, config)
    
    def init(self):
        self.manager.init()

        # Initial Funding for Virtual Account
        initial_balance = 0
        if self.config and "initial_balance" in self.config:
            initial_balance = self.config["initial_balance"]
            
        if initial_balance > 0 and len(self.manager.get_balances()) == 0:
            logger.info(f"Initializing Virtual Account with {initial_balance:,.0f} KRW")
            self.manager.add_balance("KRW", Decimal(str(initial_balance)), avg_buy_price=Decimal(1))

    def get_balance(self, ticker: str) -> Decimal:
        return self.manager.get_balance(ticker)

    def get_asset_balance(self, ticker: str) -> dict:
         """Get full asset balance info including avg_buy_price from DB"""
         # AccountDBManager -> DBTradeManager -> AssetRepo
         asset_dto = self.manager.asset_repo.get(Ticker(ticker).currency)
         if asset_dto:
             return asset_dto.model_dump()
         return {
            'currency': Ticker(ticker).currency,
            'balance': 0.0,
            'avg_buy_price': 0.0,
            'locked': 0.0,
            'unit_currency': 'KRW'
        }
    
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

    def sell_limit_order(self, ticker: str, price: Decimal, volume: Decimal) -> dict:
        return self.manager.create_order(
            market=ticker,
            side="ask",
            ord_type="limit",
            price=price,
            volume=volume
        )
    
    def buy_limit_order(self, ticker: str, price: Decimal, volume: Decimal) -> dict:
        order = self.manager.create_order(
            market=ticker,
            side="bid",
            ord_type="limit",
            price=price,
            volume=volume
        )
    
        return order
    
    def buy_market_order(self, ticker: str, volume: Decimal) -> dict:
        return self.manager.create_order(
            market=ticker,
            side="bid",
            ord_type="market",
            price=Decimal("0"),
            volume=volume 
        )

    def sell_market_order(self, ticker: str, volume: Decimal) -> OrderDTO:
        return self.manager.create_order(
            market=ticker,
            side="ask",
            ord_type="market",
            price=Decimal("0"),
            volume=volume
        )
    
    def get_order(self, ticker: str, state: str = "wait") -> List[OrderDTO]:
        return self.manager.get_open_orders(ticker)
    
    def cancel_order(self, uuid: str) -> OrderDTO:
        return self.manager.cancel_order(uuid)

    def on_order_complete(self, order: OrderDTO):
        self.manager.process_order_complete(order)
    
    def check_order(self, market: str, orderbook_units: List[dict]) -> Optional[OrderDTO]:
        return self.manager.check_and_execute_orders(market, orderbook_units)
    


