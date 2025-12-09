import sqlite3
import json
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Optional, List, Dict, Any
from models.position import Position
from src.stratege_manager import StrategyManager, StrategyFactory
from strategy.base import Signal


class PositionEx(Position):
    
    # Strategy 직렬화된 데이터 저장
    strategies_data: Optional[List[Dict[str, Any]]] = None
    
    # Strategy Manager (DB에 저장되지 않음)
    _strategy_manager: Optional[StrategyManager] = None
    
    class Config:
        arbitrary_types_allowed = True
    
    @property
    def strategy_manager(self) -> StrategyManager:
        """Strategy Manager 접근 (lazy initialization)"""
        if self._strategy_manager is None:
            self._strategy_manager = StrategyManager(self)
            self._strategy_manager.load_strategies()
        return self._strategy_manager
    
    def add_strategy(self, strategy_type: str, config: Dict[str, Any]):
        """Strategy 추가 편의 메서드"""
        strategy = StrategyFactory.create(strategy_type, self.id, config)
        self.strategy_manager.add_strategy(strategy)
    
    def update_price(self, current_price: float) -> List[Signal]:
        """가격 업데이트 및 Signal 반환"""
        # 최고가 업데이트
        if self.highest_price is None or current_price > self.highest_price:
            self.highest_price = current_price
        
        # Strategy 업데이트
        return self.strategy_manager.update(current_price)
    
    def to_db_dict(self) -> Dict[str, Any]:
        """DB 저장용 딕셔너리"""
        data = self.model_dump(exclude={'_strategy_manager'})
        if self.strategies_data:
            data['strategies_data'] = json.dumps(self.strategies_data)
        return data
    
    @classmethod
    def from_db_dict(cls, data: Dict[str, Any]) -> 'Position':
        """DB에서 로드"""
        if isinstance(data.get('strategies_data'), str):
            data['strategies_data'] = json.loads(data['strategies_data'])
        return cls(**data)
    
    def save(self, db_path: str = "account.db"):
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            Position.initialize_db(db_path)
            
            # Serialize strategies list to JSON string if it exists
            strategies_str = None
            if self.strategies_data:
                import json
                strategies_str = json.dumps(self.strategies_data)
                
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
                    order_id, highest_price, status, close_price, "close_time", strategies_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.id, self.ticker, self.entry_price, self.volume, config_str, self.entry_time,
                self.order_id, self.highest_price, self.status, self.close_price, self.close_time, strategies_str
            ))
            conn.commit()

    def archive(self, db_path: str = "account.db"):
        """
        Moves the position from 'positions' table to 'position_history' table.
        Should be called after the position is closed.
        """
        if not self.is_closed:
             raise ValueError("Position must be closed before archiving.")

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            Position.initialize_db(db_path)
            
            # Serialize fields
            strategies_str = None
            if self.strategies_data:
                import json
                strategies_str = json.dumps(self.strategies_data)
            
            config_str = None
            if self.config:
                import json
                try:
                    config_str = json.dumps(self.config)
                except:
                    config_str = str(self.config)

            # Insert into history
            cursor.execute("""
                INSERT OR REPLACE INTO position_history (
                    id, ticker, entry_price, volume, config, entry_time,
                    order_id, highest_price, status, close_price, "close_time", strategies_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.id, self.ticker, self.entry_price, self.volume, config_str, self.entry_time,
                self.order_id, self.highest_price, self.status, self.close_price, self.close_time, strategies_str
            ))
            
            # Delete from active positions
            cursor.execute("DELETE FROM positions WHERE id = ?", (self.id,))
            
            conn.commit()

    @classmethod
    def load_all(cls, db_path: str = "account.db", status: Optional[str] = None) -> list["Position"]:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            PositionEx.initialize_db(db_path)
            
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
                # id, ticker, entry_price, volume, config, entry_time, order_id, highest_price, status, close_price, close_time, strategies_data
                
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
                    strategies_data=strategies_val
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

class PositionManager:
    def __init__(self, db_path: str = "account.db"):
        self.db_path = db_path
        self.positions: List[PositionEx] = []
        self.load_positions()

    def load_positions(self):
        self.positions = PositionEx.load_all(self.db_path)