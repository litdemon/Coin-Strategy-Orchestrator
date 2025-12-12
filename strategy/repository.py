import sqlite3
import json
from typing import List, Optional
from decimal import Decimal
from strategy.models import StrategyDTO, StrategyStatus

class StrategyRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategies (
                    strategy_id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    budget TEXT NOT NULL,
                    position_id TEXT,
                    status TEXT NOT NULL,
                    config JSON NOT NULL,
                    state JSON NOT NULL,
                    created_at REAL,
                    updated_at REAL
                )
            """)
            conn.commit()

    def save(self, strategy: StrategyDTO):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO strategies 
                (strategy_id, type, ticker, budget, position_id, status, config, state, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                strategy.strategy_id,
                strategy.type,
                strategy.ticker,
                str(strategy.budget),
                strategy.position_id,
                strategy.status,
                json.dumps(strategy.config, default=str),
                json.dumps(strategy.state, default=str),
                strategy.created_at,
                strategy.updated_at
            ))
            conn.commit()

    def get(self, strategy_id: str) -> Optional[StrategyDTO]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM strategies WHERE strategy_id = ?", (strategy_id,))
            row = cursor.fetchone()
            
            if row:
                return self._row_to_dto(row)
            return None

    def get_all(self, status: Optional[StrategyStatus] = None) -> List[StrategyDTO]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if status:
                cursor.execute("SELECT * FROM strategies WHERE status = ?", (status,))
            else:
                cursor.execute("SELECT * FROM strategies")
                
            return [self._row_to_dto(row) for row in cursor.fetchall()]

    def _row_to_dto(self, row: sqlite3.Row) -> StrategyDTO:
        return StrategyDTO(
            strategy_id=row['strategy_id'],
            type=row['type'],
            ticker=row['ticker'],
            budget=Decimal(row['budget']),
            position_id=row['position_id'],
            status=StrategyStatus(row['status']),
            config=json.loads(row['config']),
            state=json.loads(row['state']),
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )
