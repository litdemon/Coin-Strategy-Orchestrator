import sqlite3
import json
import contextlib
from typing import List, Optional
from decimal import Decimal
from strategy.models import StrategyDTO, StrategyStatus, StrategyType

class StrategyRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def init_db(self):
        with contextlib.closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategies (
                    strategy_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    budget TEXT NOT NULL,
                    pocket_id TEXT,
                    status TEXT NOT NULL,
                    config JSON NOT NULL,
                    state JSON NOT NULL,
                    created_at REAL,
                    updated_at REAL,
                    last_execution_time REAL DEFAULT 0.0
                )
            """)
            conn.commit()

            # Create Archive Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategies_archive (
                    strategy_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    budget TEXT NOT NULL,
                    pocket_id TEXT,
                    status TEXT NOT NULL,
                    config JSON NOT NULL,
                    state JSON NOT NULL,
                    created_at REAL,
                    updated_at REAL,
                    last_execution_time REAL DEFAULT 0.0,
                    archived_at REAL
                )
            """)
            conn.commit()

    def save(self, strategy: StrategyDTO):
        with contextlib.closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO strategies 
                (strategy_id, name, type, ticker, budget, pocket_id, status, config, state, created_at, updated_at, last_execution_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                strategy.strategy_id,
                strategy.name,
                strategy.type.value, # Store Enum as string
                strategy.ticker,
                str(strategy.budget),
                strategy.pocket_id,
                strategy.status,
                json.dumps(strategy.config, default=str),
                json.dumps(strategy.state, default=str),
                strategy.created_at,
                strategy.updated_at,
                strategy.last_execution_time
            ))
            conn.commit()

    def archive(self, strategy_id: str):
        """Move strategy to archive table."""
        dto = self.get(strategy_id)
        if not dto:
            return

        with contextlib.closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            
            # Insert into archive
            import time
            archived_at = time.time()
            
            cursor.execute("""
                INSERT OR REPLACE INTO strategies_archive
                (strategy_id, name, type, ticker, budget, pocket_id, status, config, state, created_at, updated_at, last_execution_time, archived_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dto.strategy_id,
                dto.name,
                dto.type.value,
                dto.ticker,
                str(dto.budget),
                dto.pocket_id,
                "ARCHIVED", 
                json.dumps(dto.config, default=str),
                json.dumps(dto.state, default=str),
                dto.created_at,
                dto.updated_at,
                dto.last_execution_time,
                archived_at
            ))
            
            # Delete from active
            cursor.execute("DELETE FROM strategies WHERE strategy_id = ?", (strategy_id,))
            conn.commit()

    def get(self, strategy_id: str) -> Optional[StrategyDTO]:
        with contextlib.closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM strategies WHERE strategy_id = ?", (strategy_id,))
            row = cursor.fetchone()
            
            if row:
                return self._row_to_dto(row)
            return None

    def get_all(self, status: Optional[StrategyStatus] = None) -> List[StrategyDTO]:
        with contextlib.closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if status:
                cursor.execute("SELECT * FROM strategies WHERE status = ?", (status,))
            else:
                cursor.execute("SELECT * FROM strategies")
                
            return [self._row_to_dto(row) for row in cursor.fetchall()]

    def _row_to_dto(self, row: sqlite3.Row) -> StrategyDTO:
        # Backward compatibility check for last_execution_time
        last_exec = 0.0
        if 'last_execution_time' in row.keys():
             last_exec = row['last_execution_time']

        return StrategyDTO(
            strategy_id=row['strategy_id'],
            name=row['name'],
            type=StrategyType(row['type']),
            ticker=row['ticker'],
            budget=Decimal(row['budget']),
            pocket_id=row['pocket_id'],
            status=StrategyStatus(row['status']),
            config=json.loads(row['config']),
            state=json.loads(row['state']),
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            last_execution_time=last_exec
        )
