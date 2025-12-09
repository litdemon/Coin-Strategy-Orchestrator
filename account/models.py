from dataclasses import dataclass
import sqlite3
from typing import List, Optional
from decimal import Decimal

@dataclass
class Asset:
    currency: str
    balance: Decimal
    locked: Decimal
    avg_buy_price: Decimal
    avg_buy_price_modified: bool
    unit_currency: str

    @property
    def ticker(self) -> str:
        return f"{self.unit_currency}-{self.currency}"

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

    def to_dict(self) -> dict:
        return {
            "currency": self.currency,
            "balance": str(self.balance),
            "locked": str(self.locked),
            "avg_buy_price": str(self.avg_buy_price),
            "avg_buy_price_modified": self.avg_buy_price_modified,
            "unit_currency": self.unit_currency
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
            self.unit_currency
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
                unit_currency=row[5]
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
                unit_currency TEXT
            )
        """)


@dataclass
class Balance:
    assets: List[Asset]

    @classmethod
    def from_list(cls, data: List[dict]) -> "Balance":
        return cls(assets=[Asset.from_dict(item) for item in data])
    
    def save(self, db_path: str = "account.db"):
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            for asset in self.assets:
                asset.save(cursor)
            conn.commit()

    @classmethod
    def load(cls, db_path: str = "account.db") -> "Balance":
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            assets = Asset.load_all(cursor)
            return cls(assets=assets)

    def get_balances(self) -> List[dict]:
        """
        Returns a list of all assets as dictionaries.
        """
        return [asset.to_dict() for asset in self.assets]

    def get_balance(self, ticker: str) -> Decimal:
        """
        Returns the balance for a given ticker.
        If ticker is "KRW-BTC", searches for "BTC".
        If ticker is "KRW", searches for "KRW".
        Returns 0 if not found.
        """
        currency = ticker.split("-")[1] if "-" in ticker else ticker
        for asset in self.assets:
            if asset.currency == currency:
                return asset.balance
        return Decimal(0)
    
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

