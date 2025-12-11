import sqlite3
from typing import List, Optional
from decimal import Decimal
from account.dtos import AssetDTO, OrderDTO
from account.exceptions import OrderNotFoundException

# Register adapters if not already valid in global scope,
# but usually it's better to do this at app startup.
# For now, I'll assume they are registered or register them here too just in case.
def adapt_decimal(d):
    return str(d)

def convert_decimal(s):
    return Decimal(s.decode('utf-8'))

sqlite3.register_adapter(Decimal, adapt_decimal)
sqlite3.register_converter("DECIMAL", convert_decimal)

class RepositoryBase:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _get_connection(self):
        return sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)

class AssetRepository(RepositoryBase):
    def init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS assets (
                    currency TEXT PRIMARY KEY,
                    balance DECIMAL,
                    locked DECIMAL,
                    avg_buy_price DECIMAL,
                    avg_buy_price_modified BOOLEAN,
                    unit_currency TEXT
                )
            """)

    def save(self, asset: AssetDTO):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO assets 
                (currency, balance, locked, avg_buy_price, avg_buy_price_modified, unit_currency)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                asset.currency,
                asset.balance,
                asset.locked,
                asset.avg_buy_price,
                asset.avg_buy_price_modified,
                asset.unit_currency
            ))

    def get(self, currency: str) -> Optional[AssetDTO]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM assets WHERE currency = ?", (currency,))
            row = cursor.fetchone()
            if row:
                # row is tuple: (currency, balance, locked, avg, modified, unit)
                return AssetDTO(
                    currency=row[0],
                    balance=row[1],
                    locked=row[2],
                    avg_buy_price=row[3],
                    avg_buy_price_modified=bool(row[4]),
                    unit_currency=row[5]
                )
        return None

    def get_all(self) -> List[AssetDTO]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM assets")
            rows = cursor.fetchall()
            return [
                AssetDTO(
                    currency=row[0],
                    balance=row[1],
                    locked=row[2],
                    avg_buy_price=row[3],
                    avg_buy_price_modified=bool(row[4]),
                    unit_currency=row[5]
                ) for row in rows
            ]

class OrderRepository(RepositoryBase):
    def init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    uuid TEXT PRIMARY KEY,
                    side TEXT,
                    ord_type TEXT,
                    price DECIMAL,
                    state TEXT,
                    market TEXT,
                    created_at TIMESTAMP,
                    volume DECIMAL,
                    remaining_volume DECIMAL,
                    reserved_fee DECIMAL,
                    remaining_fee DECIMAL,
                    paid_fee DECIMAL,
                    locked DECIMAL,
                    executed_volume DECIMAL,
                    trades_count INTEGER
                )
            """)

    def save(self, order: OrderDTO):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO orders 
                (uuid, side, ord_type, price, state, market, created_at, volume, remaining_volume, 
                 reserved_fee, remaining_fee, paid_fee, locked, executed_volume, trades_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order.uuid, order.side, order.ord_type, order.price, order.state, order.market, 
                order.created_at, order.volume, order.remaining_volume, order.reserved_fee, 
                order.remaining_fee, order.paid_fee, order.locked, order.executed_volume, order.trades_count
            ))

    def get(self, uuid: str) -> Optional[OrderDTO]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM orders WHERE uuid = ?", (uuid,))
            row = cursor.fetchone()
            if row:
                return self._map_row_to_dto(row)
        return None

    def get_by_state(self, state: str) -> List[OrderDTO]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM orders WHERE state = ?", (state,))
            rows = cursor.fetchall()
            return [self._map_row_to_dto(row) for row in rows]
            
    def get_by_market_and_state(self, market: str, state: str) -> List[OrderDTO]:
         with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM orders WHERE market = ? AND state = ?", (market, state))
            rows = cursor.fetchall()
            return [self._map_row_to_dto(row) for row in rows]

    def _map_row_to_dto(self, row) -> OrderDTO:
        # Assumes row matches table columns order defined in init_db
        return OrderDTO(
            uuid=row[0],
            side=row[1],
            ord_type=row[2],
            price=row[3],
            state=row[4],
            market=row[5],
            created_at=row[6],
            volume=row[7],
            remaining_volume=row[8],
            reserved_fee=row[9],
            remaining_fee=row[10],
            paid_fee=row[11],
            locked=row[12],
            executed_volume=row[13],
            trades_count=row[14]
        )
