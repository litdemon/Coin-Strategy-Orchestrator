import uuid
import time
import logging
import sqlite3
import os

from pydantic import BaseModel, Field
from typing import Optional, Any, List

class Position(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ticker: str
    entry_price: float
    volume: float
    config: Optional[Any] = None
    entry_time: float = Field(default_factory=time.time)
    
    # Fields refactored from Rot
    order_id: Optional[str] = None
    highest_price: Optional[float] = None
    status: str = "active" # active, closed

    close_price: Optional[float] = None
    close_time: Optional[float] = None

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def profit_rate(self, current_price: float) -> float:
        if self.entry_price == 0:
            return 0.0
        return (current_price - self.entry_price) / self.entry_price

    def close(self, close_price: float) -> None:
        self.close_price = close_price
        self.close_time = time.time()
        
    @property
    def is_closed(self) -> bool:
        return self.close_price is not None

    def __repr__(self) -> str:
        profit_rate = self.profit_rate(self.close_price) if self.close_price else 0
        return f"Position(id={self.id}, ticker={self.ticker}, entry={self.entry_price}, close={self.close_price}, profit={profit_rate:.4f})"


    def save(self, db_path: str = "account.db"):
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            initialize_db(db_path)
            
            # Serialize strategies list to JSON string if it exists
            # For Position base class, we just ignore strategies_data or handle generic config
            
            config_str = None
            if self.config:
                import json
                try:
                    config_str = json.dumps(self.config)
                except:
                    config_str = str(self.config)

            # NOTE: strategies_data is handled by PositionEx, but if we save generic Position, 
            # we need to respect the schema. The schema has 'strategies_data' column.
            # We will pass None if it doesn't exist on self (it doesn't on base Position).
            strategies_str = getattr(self, "strategies_data", None)
            if strategies_str and not isinstance(strategies_str, str):
                 import json
                 strategies_str = json.dumps(strategies_str)

            cursor.execute("""
                INSERT OR REPLACE INTO positions (
                    id, ticker, entry_price, volume, config, entry_time,
                    order_id, highest_price, status, close_price, "close_time", strategies_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.id, self.ticker, self.entry_price, self.volume, config_str, self.entry_time,
                self.order_id, self.highest_price, self.status, self.close_price, self.close_time, strategies_str
            ))
            conn.commit()

    def archive(self, db_path: str = "account.db"):
        if not self.is_closed:
             raise ValueError("Position must be closed before archiving.")

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            initialize_db(db_path)
            
            config_str = None
            if self.config:
                import json
                try:
                    config_str = json.dumps(self.config)
                except:
                    config_str = str(self.config)

            strategies_str = getattr(self, "strategies_data", None)
            if strategies_str and not isinstance(strategies_str, str):
                 import json
                 strategies_str = json.dumps(strategies_str)
            
            cursor.execute("""
                INSERT OR REPLACE INTO position_history (
                    id, ticker, entry_price, volume, config, entry_time,
                    order_id, highest_price, status, close_price, "close_time", strategies_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.id, self.ticker, self.entry_price, self.volume, config_str, self.entry_time,
                self.order_id, self.highest_price, self.status, self.close_price, self.close_time, strategies_str
            ))
            
            cursor.execute("DELETE FROM positions WHERE id = ?", (self.id,))
            conn.commit()

    @classmethod
    def load_all(cls, db_path: str = "account.db", status: Optional[str] = None) -> list["Position"]:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            Position.initialize_db(db_path)
            
            query = "SELECT * FROM positions"
            params = []
            if status:
                query += " WHERE status = ?"
                params.append(status)
                
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            positions = []
            for row in rows:
                config_val = row[4]
                if config_val:
                    try:
                        import json
                        config_val = json.loads(config_val)
                    except:
                        pass
                
                # strategies_data is row[11], but base Position doesn't have it.
                # We can ignore it or store in config if needed. 
                # For now, base Position won't load it into a field, but it's fine.
                
                pos = cls(
                    id=row[0],
                    ticker=row[1],
                    entry_price=row[2],
                    volume=row[3],
                    config=config_val,
                    entry_time=row[5],
                    order_id=row[6],
                    highest_price=row[7],
                    status=row[8],
                    close_price=row[9],
                    close_time=row[10]
                )
                positions.append(pos)
            return positions

    @staticmethod
    def initialize_db(db_path: str = "account.db"):
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id TEXT PRIMARY KEY,
                    ticker TEXT,
                    entry_price REAL,
                    volume REAL,
                    config TEXT,
                    entry_time REAL,
                    order_id TEXT,
                    highest_price REAL,
                    status TEXT,
                    close_price REAL,
                    "close_time" REAL,
                    strategies_data TEXT
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS position_history (
                    id TEXT PRIMARY KEY,
                    ticker TEXT,
                    entry_price REAL,
                    volume REAL,
                    config TEXT,
                    entry_time REAL,
                    order_id TEXT,
                    highest_price REAL,
                    status TEXT,
                    close_price REAL,
                    "close_time" REAL,
                    strategies_data TEXT
                )
            """)
            conn.commit()
