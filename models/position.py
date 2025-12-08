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
    strateges: Optional[List[str]] = None

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
            strategies_str = None
            if self.strateges:
                import json
                strategies_str = json.dumps(self.strateges)
                
            # Serialize config if it exists (assuming it's JSON serializable or simple type)
            config_str = None
            if self.config:
                import json
                try:
                    config_str = json.dumps(self.config)
                except:
                    config_str = str(self.config)

            cursor.execute("""
                INSERT OR REPLACE INTO positions (
                    id, ticker, entry_price, volume, config, entry_time,
                    order_id, highest_price, status, close_price, "close_time", strateges
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.id, self.ticker, self.entry_price, self.volume, config_str, self.entry_time,
                self.order_id, self.highest_price, self.status, self.close_price, self.close_time, strategies_str
            ))
            conn.commit()

    @classmethod
    def load_all(cls, db_path: str = "account.db", status: Optional[str] = None) -> list["Position"]:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            initialize_db(db_path)
            
            query = "SELECT * FROM positions"
            params = []
            if status:
                query += " WHERE status = ?"
                params.append(status)
                
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            positions = []
            for row in rows:
                # row indices match the table columns defined in initialize_db
                # id, ticker, entry_price, volume, config, entry_time, order_id, highest_price, status, close_price, close_time, strateges
                
                # Deserialize fields
                config_val = row[4]
                if config_val:
                    try:
                        import json
                        config_val = json.loads(config_val)
                    except:
                        pass # Keep as string if json load fails
                
                strategies_val = row[11]
                if strategies_val:
                    import json
                    strategies_val = json.loads(strategies_val)

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
                    close_time=row[10],
                    strateges=strategies_val
                )
                positions.append(pos)
            return positions

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
                strateges TEXT
            )
        """)
        conn.commit()
