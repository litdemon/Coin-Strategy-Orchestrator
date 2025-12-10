from dataclasses import dataclass
import sqlite3
from typing import List, Optional, Any
from decimal import Decimal
import pyupbit


@dataclass
class AssetBase:
    currency: str
    balance: Decimal
    locked: Decimal
    avg_buy_price: Decimal
    avg_buy_price_modified: bool
    unit_currency: str


class Asset(AssetBase):
    def __init__(self, currency: str, balance: Decimal, locked: Decimal, avg_buy_price: Decimal, avg_buy_price_modified: bool, unit_currency: str):
        super().__init__(currency, balance, locked, avg_buy_price, avg_buy_price_modified, unit_currency)
    
    @property
    def ticker(self) -> str:
        return f"{self.currency}"

    @classmethod
    def from_dict(cls, data: dict) -> "Asset":
        return cls(
            currency=data["currency"],
            balance=Decimal(str(data["balance"])),
            locked=Decimal(str(data["locked"])),
            avg_buy_price=Decimal(str(data["avg_buy_price"])),
            avg_buy_price_modified=data["avg_buy_price_modified"],
            unit_currency=data["unit_currency"]
        )

    def append(self, other: "Asset") -> "Asset":
        self.balance += other.balance
        self.locked += other.locked
        self.avg_buy_price = (self.avg_buy_price + other.avg_buy_price) / 2
        self.avg_buy_price_modified = self.avg_buy_price_modified or other.avg_buy_price_modified
        return self

    def to_dict(self) -> dict:
        return {
            "currency": self.currency,
            "balance": str(self.balance),
            "locked": str(self.locked),
            "avg_buy_price": str(self.avg_buy_price),
            "avg_buy_price_modified": self.avg_buy_price_modified,
        }

    def save(self, cursor: sqlite3.Cursor):
        cursor.execute("""
            INSERT OR REPLACE INTO assets 
            (currency, balance, locked, avg_buy_price, avg_buy_price_modified, unit_currency)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            self.currency, 
            str(self.balance), 
            str(self.locked), 
            str(self.avg_buy_price), 
            int(self.avg_buy_price_modified),
            self.unit_currency,
        ))

    @classmethod
    def load_all(cls, cursor: sqlite3.Cursor) -> List["Asset"]:
        cursor.execute("SELECT * FROM assets")
        rows = cursor.fetchall()
        assets = []
        for row in rows:
            assets.append(cls(
                currency=row[0],
                balance=Decimal(row[1]),
                locked=Decimal(row[2]),
                avg_buy_price=Decimal(row[3]),
                avg_buy_price_modified=bool(row[4]),
                unit_currency=row[5],
            ))
        return assets
    
    @staticmethod
    def initialize_db(db_path: str = "account.db"):
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS assets (
                currency TEXT PRIMARY KEY,
                balance TEXT,
                locked TEXT,
                avg_buy_price TEXT,
                avg_buy_price_modified INTEGER,
                unit_currency TEXT)
        """)


@dataclass
class Balance:
    _assets: dict[str, Asset]

    @property
    def assets(self):
        # Prevent direct modification of the dictionary
        return self._assets

    @classmethod
    def from_list(cls, data: List[dict]) -> "Balance":
        return cls(_assets={Ticker(item['currency']).currency: Asset.from_dict(item) for item in data})
    
    def save(self, db_path: str = "account.db"):
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            for asset in self._assets.values():
                asset.save(cursor)
            conn.commit()

    @classmethod
    def load(cls, db_path: str = "account.db") -> "Balance":
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            assets_list = Asset.load_all(cursor)
            # Use currency as key
            assets_dict = {asset.currency: asset for asset in assets_list}
            return cls(_assets=assets_dict)

    def get_balances(self) -> List[dict]:
        """
        Returns a list of all assets as dictionaries.
        """
        return [asset.to_dict() for asset in self._assets.values()]

    def get_balance(self, ticker: str) -> Decimal:
        """
        Returns the balance for a given ticker or currency.
        If ticker is "KRW-BTC", searches for "BTC".
        If ticker is "KRW", searches for "KRW".
        Returns 0 if not found.
        """
        ticker_obj = Ticker(ticker)
        asset = self._assets.get(ticker_obj.currency)
        if asset:
            return asset.balance
        return Decimal(0)
    
    def add_asset(self, asset: Asset):
        """Adds or updates an asset in the balance."""
        self._assets[asset.currency] = asset

    def get_asset(self, ticker: str) -> Optional[Asset]:
        """Returns the Asset object for a given ticker or currency."""
        ticker_obj = Ticker(ticker)
        return self._assets.get(ticker_obj.currency)

    def get_all_assets(self) -> List[Asset]:
        """Returns a list of all Asset objects."""
        return list(self._assets.values())

    def buy_order(self, ticker: str, price: Decimal, volume: Decimal, executor=None):
        """
        Placeholder for buy order.
        Requires an executor to communicate with the exchange.
        """
        if executor:
            return executor.buy_limit_order(ticker, price, volume)
        raise NotImplementedError("Executor reference required for order execution.")

    def sell_order(self, ticker: str, price: Decimal, volume: Decimal, executor=None):
        """
        Placeholder for sell order.
        Requires an executor to communicate with the exchange.
        """
        if executor:
            return executor.sell_limit_order(ticker, price, volume)
        raise NotImplementedError("Executor reference required for order execution.")

    def add_balance(self, ticker: str, amount: Any, avg_buy_price: Decimal = Decimal(0)):
        """
        Adds the amount to the balance for a given ticker or currency.
        Supports both ticker (KRW-BTC) and currency (BTC) formats.
        """
        ticker_obj = Ticker(ticker)
        
        # Ensure amount is Decimal
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))

        # 기존 balance에 새로운 avg_buy_price를 적용한 후 balance에 amount를 추가
        asset = self._assets.get(ticker_obj.currency)
        if asset:
            asset.avg_buy_price = (asset.avg_buy_price * asset.balance + avg_buy_price * amount) / (asset.balance + amount)
            asset.balance += amount
        else:
            self._create_asset(ticker_obj, amount, avg_buy_price)

    def set_balance(self, ticker: str, amount: Any, avg_buy_price: Decimal = Decimal(0)):
        """
        Sets the balance for a given ticker or currency.
        Supports both ticker (KRW-BTC) and currency (BTC) formats.
        """
        ticker_obj = Ticker(ticker)
        
        # Ensure amount is Decimal
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
            
        if self._is_asset_exists(ticker_obj.currency):
            asset = self._assets[ticker_obj.currency]
            asset.balance = amount
            asset.avg_buy_price = avg_buy_price
        else:
            # For set_balance, if it doesn't exist, we might need current price if not provided, 
            # but usually set_balance implies we have a target state.
            # If avg_buy_price is 0 (default), and we are creating, it might be inaccurate if we don't fetch price.
            # Mirroring original logic:
            if avg_buy_price == 0:
                 price = pyupbit.get_current_price(str(ticker_obj))
                 # Handle case where price fetch might fail or return None
                 if price is None:
                     price = Decimal(0)
                 else:
                     price = Decimal(str(price))
                 avg_buy_price = price
            
            self._create_asset(ticker_obj, amount, avg_buy_price)

    def _create_asset(self, ticker: str, balance: Decimal,  avg_buy_price: Decimal):
        new_asset = Asset(
            currency=Ticker(ticker).currency,
            balance=balance,
            locked=Decimal(0),
            avg_buy_price=avg_buy_price,
            avg_buy_price_modified=False,
            unit_currency=Ticker(ticker).unit_currency
        )
        self._assets[ticker.currency] = new_asset
    
    def _is_asset_exists(self, currency: str) -> bool:
        return currency in self._assets