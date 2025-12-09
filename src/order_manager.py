import os
import sys
import json
import sqlite3
import logging
# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Optional, List, Dict, Any, Callable
from models.orderInfo import OrderInfo

logger = logging.getLogger(__name__)

class OrderInfoEx(OrderInfo):
    
    def save(self, db_path: str = "account.db"):
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            OrderInfoEx.initialize_db(db_path)
            
            cursor.execute("""
                INSERT OR REPLACE INTO orders (
                    uuid, side, ord_type, price, state, market, created_at,
                    volume, remaining_volume, reserved_fee, remaining_fee,
                    paid_fee, locked, executed_volume, trades_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.uuid, self.side, self.ord_type, self.price, self.state, self.market, self.created_at,
                self.volume, self.remaining_volume, self.reserved_fee, self.remaining_fee,
                self.paid_fee, self.locked, self.executed_volume, self.trades_count
            ))
            conn.commit()

    @classmethod
    def load_all(cls, db_path: str = "account.db", state: Optional[str] = None) -> List["OrderInfoEx"]:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            OrderInfoEx.initialize_db(db_path)
            
            query = "SELECT * FROM orders"
            params = []
            if state:
                query += " WHERE state = ?"
                params.append(state)
                
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            orders = []
            for row in rows:
                # row indices match the table columns defined in initialize_db
                # uuid, side, ord_type, price, state, market, created_at, volume, remaining_volume, reserved_fee, remaining_fee, paid_fee, locked, executed_volume, trades_count
                
                order = cls(
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
                orders.append(order)
            return orders

    @classmethod
    def get(cls, uuid: str, db_path: str = "account.db") -> Optional["OrderInfoEx"]:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            OrderInfoEx.initialize_db(db_path)
            
            cursor.execute("SELECT * FROM orders WHERE uuid = ?", (uuid,))
            row = cursor.fetchone()
            
            if row:
                return cls(
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
            return None

    @staticmethod
    def initialize_db(db_path: str = "account.db"):
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    uuid TEXT PRIMARY KEY,
                    side TEXT,
                    ord_type TEXT,
                    price REAL,
                    state TEXT,
                    market TEXT,
                    created_at TEXT,
                    volume REAL,
                    remaining_volume REAL,
                    reserved_fee REAL,
                    remaining_fee REAL,
                    paid_fee REAL,
                    locked REAL,
                    executed_volume REAL,
                    trades_count INTEGER
                )
            """)
            conn.commit()

class OrderManager:
    def __init__(self, on_order_complete: Callable[[OrderInfoEx], None], db_path: str = "account.db"):
        self.db_path = db_path
        self.on_order_complete = on_order_complete
        # Initialize DB and wait orders
        OrderInfoEx.initialize_db(self.db_path)
        self.wait_orders: List[OrderInfoEx] = OrderInfoEx.load_all(self.db_path, state="wait")
        logger.info(f"[OrderManager] Loaded {len(self.wait_orders)} wait orders.")

    def add_order(self, order: OrderInfoEx):
        """
        Saves a new order to DB and adds it to the internal wait list if state is 'wait'.
        """
        order.save(self.db_path)
        if order.state == "wait":
            self.wait_orders.append(order)
            logger.info(f"[OrderManager] Added new order {order.uuid} to wait list.")

    def check_execution(self, current_price_model: Any):
        """
        Checks if any wait orders are executed based on the current price.
        current_price_model: An object with a get(market) -> float method.
        """
        # Iterate over a copy of the list to allow removal during iteration
        for order in self.wait_orders[:]:
            current_price = current_price_model.get(order.market)
            
            if current_price == 0:
                continue

            executed = False
            
            # Simple execution logic:
            # Bid (Buy): if current_price <= order.price
            # Ask (Sell): if current_price >= order.price
            if order.side == "bid" and order.price is not None:
                if current_price <= order.price:
                    executed = True
            elif order.side == "ask" and order.price is not None:
                if current_price >= order.price:
                    executed = True
            
            if executed:
                logger.info(f"[OrderManager] Order {order.uuid} executed at {current_price} (Limit: {order.price})")
                self._handle_execution(order)

    def _handle_execution(self, order: OrderInfoEx):
        """
        Handles the execution of an order.
        """
        # 1. Update state
        order.state = "done"
        
        # 2. Update execution details (Assuming full execution for simplicity as per requirement)
        # You might want to update executed_volume, remaining_volume, etc. here if needed.
        # For now, just marking as done.
        
        # 3. Save to DB
        order.save(self.db_path)
        
        # 4. Remove from wait list
        if order in self.wait_orders:
            self.wait_orders.remove(order)
            
        # 5. Call callback
        if self.on_order_complete:
            self.on_order_complete(order)
