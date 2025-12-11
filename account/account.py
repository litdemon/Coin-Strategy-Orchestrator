
import sqlite3
from decimal import Decimal
import pyupbit
import uuid
import datetime
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import List, Optional, Any, Callable

from tools.ticker import Ticker
from tools.db_interface import DBInterface
from models.my_asset import MyAsset, AssetItem
from models.my_order import MyOrder

def adapt_decimal(d):
    return str(d)

def convert_decimal(s):
    return Decimal(s)

sqlite3.register_adapter(Decimal, adapt_decimal)
sqlite3.register_converter("DECIMAL", convert_decimal)

from models.orderInfo import OrderInfo

DB_PATH = "account.db"

class AssetBase(BaseModel):
    currency: str
    balance: Decimal
    locked: Decimal
    avg_buy_price: Decimal
    avg_buy_price_modified: bool
    unit_currency: str


class Asset(AssetBase, DBInterface):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    @property
    def ticker(self) -> str:
        return Ticker(self.currency).ticker
    
    def save(self, db_path: str = None):
        if db_path is None:
            db_path = DB_PATH
        super().save(db_path)

    def add(self, balance, avg_buy_price) -> "Asset":
        self.balance += balance
        self.avg_buy_price = (self.avg_buy_price + avg_buy_price) / 2
        self.save()
        return self
    
    def sub(self, balance:float):
        self.balance -= balance
        self.save()
        return self

    def add_locked(self, locked:float):
        self.locked += locked
        self.save()
        return self

    def sub_locked(self, locked:float):
        self.locked -= locked
        self.save()
        return self

class OrderDB(OrderInfo, DBInterface):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def save(self, db_path: str = None):
        if db_path is None:
            db_path = DB_PATH
        super().save(db_path)

    @classmethod
    def _get_table_name(cls) -> str:
        return "orders"

    @classmethod
    def load(cls, state: str = "wait", db_path: str = None) -> dict[str, "OrderDB"]:
        if db_path is None:
            db_path = DB_PATH
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE state = ?", (state,))
        rows = cursor.fetchall()
        column_names = [description[0] for description in cursor.description]
        conn.close()

        orders = {}
        for row in rows:
            order_data = dict(zip(column_names, row))
            orders[order_data['uuid']] = cls(**order_data)

        return orders

    @classmethod
    def get_order(cls, uuid: str) -> Optional["OrderDB"]:
        # DB_PATH global is used directly here, but we should allow it to be patched?
        # get_order doesn't take db_path arg. We should add it or use global DB_PATH.
        # If we use global DB_PATH, patching 'account.account.DB_PATH' works!
        # Because we access it at runtime inside the function.
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE uuid = ?", (uuid,))
        row = cursor.fetchone()
        conn.close()

        if row:
            column_names = [description[0] for description in cursor.description]
            order_data = dict(zip(column_names, row))
            return OrderDB(**order_data)
        return None

class BalanceBase(BaseModel):
    assets: dict[str, Asset]

class Balance(BalanceBase, DBInterface):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def assets(self):
        # Prevent direct modification of the dictionary
        return self.assets

    @classmethod
    def from_list(cls, data: List[dict]) -> "Balance":
        return cls(assets={Ticker(item['currency']).currency: Asset(**item) for item in data})
    
    @classmethod
    def load(cls, db_path: str = None) -> "Balance":
        if db_path is None:
            db_path = DB_PATH
        assets_list = Asset.load_all(db_path)
        
        assets = {asset.currency: asset for asset in assets_list}
        return cls(assets=assets)

    def get_balances(self) -> List[dict]:
        return [asset.model_dump() for asset in self.assets.values()]

    def get_balance(self, ticker: str) -> Decimal:
        ticker_obj = Ticker(ticker)
        asset = self.assets.get(ticker_obj.currency)
        if asset:
            return asset.balance
        return Decimal(0)

    def add_balance(self, ticker: str, amount: Any, avg_buy_price: Decimal = Decimal(0)):
        ticker_obj = Ticker(ticker)
        
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))

        asset = self.assets.get(ticker_obj.currency)
        if asset:
            asset.add(amount, avg_buy_price)
        else:
            asset = Asset(currency=ticker_obj.currency,
                        balance=amount,
                        locked=Decimal(0),
                        avg_buy_price=avg_buy_price,
                        avg_buy_price_modified=False,
                        unit_currency=ticker_obj.unit_currency  )
            
            self.assets[ticker_obj.currency] = asset
        asset.save()
        # for return MyAsset
        item = AssetItem(currency=ticker_obj.currency, balance=asset.balance, locked=asset.locked)
        my_asset_msg = MyAsset(assets=[item])
        return my_asset_msg.model_dump_json()

    def sub_balance(self, ticker: str, amount: Any, avg_buy_price: Decimal = Decimal(0)) -> str:
        ticker_obj = Ticker(ticker)
        
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))

        asset = self.assets.get(ticker_obj.currency)
        if asset:
            asset.sub(amount)
        else:
            raise ValueError(f"Asset {ticker_obj.currency} not found")
        
        # for return MyAsset
        asset.save()
        item = AssetItem(currency=ticker_obj.currency, balance=asset.balance, locked=asset.locked)
        my_asset_msg = MyAsset(assets=[item])
        return my_asset_msg.model_dump_json()


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
    def buy_limit_order(self, ticker: str, price: float, volume: float) -> OrderInfo:
        pass
    
    @abstractmethod
    def buy_market_order(self, ticker: str, volume: float) -> OrderInfo:
        pass
    
    @abstractmethod
    def sell_market_order(self, ticker: str, volume: float) -> OrderInfo:
        pass
    
    @abstractmethod
    def get_order(self, ticker: str, state: str = "wait") -> List[OrderInfo]:
        pass
    
    @abstractmethod
    def cancel_order(self, uuid: str) -> OrderInfo:
        pass

    @abstractmethod
    def get_order(self, ticker: str, state: str = "wait") -> List[OrderInfo]:
        pass

    def on_order_complete(self, order: OrderInfo):
        pass
    
    def check_order(self, market: str, orderbook_units: List[dict]) -> OrderInfo:
        pass    
    
    def get_orders(self) -> List[dict]:
        pass

    def cancel_order(self, uuid: str) -> OrderInfo:
        pass
    
    def on_order_complete(self, order: OrderInfo):
        pass
    
    def check_order(self, market: str, orderbook_units: List[dict]) -> OrderInfo:
        pass    
    
class AccountUpbit(AccountBase):

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
    
    def buy_limit_order(self, ticker: str, price: float, volume: float) -> OrderInfo:
        return self.upbit.buy_limit_order(ticker, price, volume)
    
    def buy_market_order(self, ticker: str, volume: float) -> OrderInfo:
        return self.upbit.buy_market_order(ticker, volume)
    
    def sell_market_order(self, ticker: str, volume: float) -> OrderInfo:
        return self.upbit.sell_market_order(ticker, volume)
    
    def get_order(self, ticker: str, state: str = "wait") -> List[OrderInfo]:
        return self.upbit.get_order(ticker, state)
    
    def cancel_order(self, uuid: str) -> OrderInfo:
        return self.upbit.cancel_order(uuid)
    
    def on_order_complete(self, order: OrderInfo):
        pass
    
    def check_order(self, market: str, orderbook_units: List[dict]) -> OrderInfo:
        pass    



class Account(AccountBase):
    def __init__(self, callback: Callable[[Any, dict], None]):
        self.callback = callback or (lambda *args, **kwargs: None)
        self.balance = Balance.load()
        self.orders = OrderDB.load(state="wait")
    
    def get_balance(self, ticker: str) -> Decimal:
        return self.balance.get_balance(ticker)
    
    def get_balances(self) -> List[dict]:
        return self.balance.get_balances()
    
    def get_orders(self) -> List[dict]:
        return OrderDB.load(state="wait").values()
    
    def get_current_price(self, ticker: str) -> Decimal:
        return pyupbit.get_current_price(ticker)
    
    def get_ohlcv(self, ticker: str, interval: str = "minute1", count: int = 200) -> List[dict]:
        return pyupbit.get_ohlcv(ticker, interval, count)
        
    def get_orderbook(self, ticker: str) -> List[dict]:
        return pyupbit.get_orderbook(ticker)

    def sell_limit_order(self, ticker: str, price: float, volume: float) -> OrderInfo:
        orderinfo = OrderDB(uuid=str(uuid.uuid4()), 
                                side="ask", 
                                ord_type="limit", 
                                price=price, 
                                state="wait", 
                                market=ticker, 
                                created_at=datetime.datetime.now().isoformat(), 
                                volume=volume, 
                                remaining_volume=volume, 
                                reserved_fee=0.0, remaining_fee=0.0, paid_fee=0.0, 
                                locked=volume, 
                                executed_volume=0.0, 
                                trades_count=0)
        orderinfo.save()
        self.orders[orderinfo.uuid] = orderinfo
        return orderinfo
    
    def buy_limit_order(self, ticker: str, price: float, volume: float) -> OrderInfo:
        orderinfo = OrderDB(uuid=str(uuid.uuid4()), 
                                side="bid", 
                                ord_type="limit", 
                                price=price, 
                                state="wait", 
                                market=ticker, 
                                created_at=datetime.datetime.now().isoformat(), 
                                volume=volume, 
                                remaining_volume=volume, 
                                reserved_fee=0.0, remaining_fee=0.0, paid_fee=0.0, 
                                locked=volume, 
                                executed_volume=0.0, 
                                trades_count=0)
        orderinfo.save()
        self.orders[orderinfo.uuid] = orderinfo
        return orderinfo
    
    def buy_market_order(self, ticker: str, volume: float) -> OrderInfo:
        orderinfo = OrderDB(uuid=str(uuid.uuid4()), 
                                side="bid", 
                                ord_type="market", 
                                price=0.0, 
                                state="wait", 
                                market=ticker, 
                                created_at=datetime.datetime.now().isoformat(), 
                                volume=volume, 
                                remaining_volume=volume, 
                                reserved_fee=0.0, remaining_fee=0.0, paid_fee=0.0, 
                                locked=volume, 
                                executed_volume=0.0, 
                                trades_count=0)
        orderinfo.save()
        self.orders[orderinfo.uuid] = orderinfo
        return orderinfo

    def sell_market_order(self, ticker: str, volume: float) -> OrderInfo:
        orderinfo = OrderDB(uuid=str(uuid.uuid4()), 
                                side="ask", 
                                ord_type="market", 
                                price=0.0, 
                                state="wait", 
                                market=ticker, 
                                created_at=datetime.datetime.now().isoformat(), 
                                volume=volume, 
                                remaining_volume=volume, 
                                reserved_fee=0.0, remaining_fee=0.0, paid_fee=0.0, 
                                locked=volume, 
                                executed_volume=0.0, 
                                trades_count=0)
        orderinfo.save()
        self.orders[orderinfo.uuid] = orderinfo
        return orderinfo
    
    def get_order(self, ticker: str, state: str = "wait") -> List[OrderInfo]:
        '''
        미 체결 주문 정보를 가져옵니다.
        '''
        orders = []
        for order in self.orders.values():
            if order.market == ticker and order.state == state:
                orders.append(order)
        return orders
    
    def cancel_order(self, uuid: str) -> OrderInfo:

        order = OrderDB.get_order(uuid)
        if order:
            order.state = "cancel"
            order.save()
        return order

    def on_order_complete(self, order: OrderInfo):
        order.state = "done"
        order.save()
        krw_volume = order.volume * order.price
        fee = krw_volume * 0.0005
        
        if order.side == "bid":
            # 총 금액에서 수수료를 뺀 금액을 지불합니다.
            my_asset_msg = self.balance.add_balance(order.market, order.volume, order.price)
            self.callback(self, my_asset_msg)
            my_asset_msg = self.balance.sub_balance("KRW", krw_volume + fee)
            self.callback(self, my_asset_msg)
        else:
            # 총 금액에서 수수료를 뺀 금액을 지불합니다.
            my_asset_msg = self.balance.sub_balance(order.market, order.volume, order.price)
            self.callback(self, my_asset_msg)
            my_asset_msg = self.balance.add_balance("KRW", krw_volume - fee)
            self.callback(self, my_asset_msg)

    def check_order(self, market: str, orderbook_units: List[dict]) -> OrderInfo:
        # 현재 가격
        if orderbook_units is None or len(orderbook_units) == 0:
            return None
        orderbook_unit = orderbook_units[0]

        for order in self.get_order(market, "wait"):

            if order.ord_type == "limit":
                if order.side == "bid":
                    if order.price >= orderbook_unit["ask_price"]:
                        self.on_order_complete(order)
                        return order
                else:
                    if order.price <= orderbook_unit["bid_price"]:
                        self.on_order_complete(order)
                        return order
            elif order.ord_type == "market":
                order.executed_volume = order.volume
                order.price = orderbook_unit["ask_price"] if order.side == "bid" else orderbook_unit["bid_price"]
                self.on_order_complete(order)
                return order
        return None
