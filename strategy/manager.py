import logging
import time
from typing import Dict, Type, List, Optional, Any
from decimal import Decimal

from strategy.models import StrategyContext, StrategyConfig, StrategyDTO, StrategyStatus, Signal, SignalType
from strategy.base import StrategyBase
from strategy.repository import StrategyRepository
from account.manager import AccountBase
import traceback
from abc import ABC, abstractmethod
from typing import Dict, Any

logger = logging.getLogger(__name__)

class StrategyObserver(ABC):

    @abstractmethod
    def on_strategy_created(self, strategy: StrategyBase):
        pass

    @abstractmethod
    def on_strategy_signal(self, strategy: StrategyBase, signal: Signal):
        pass

    @abstractmethod
    def on_strategy_updated(self, strategy: StrategyBase):
        pass

    @abstractmethod
    def on_strategy_deleted(self, strategy: StrategyBase):
        pass


class StrategyManager:
    def __init__(self, db_path: str, observer: StrategyObserver):
        self.repo = StrategyRepository(db_path)
        self.observer = observer
        self.strategies: Dict[str, StrategyBase] = {} # Active strategy instances
        self.strategy_classes: Dict[str, Type[StrategyBase]] = {}
        
        # Initialize DB
        self.repo.init_db()

    def register_strategy(self, type_name: str, strategy_cls: Type[StrategyBase]):
        """Register a strategy class."""
        self.strategy_classes[type_name] = strategy_cls
        logger.info(f"Registered strategy type: {type_name}")

    def load_strategies(self):
        """Load active strategies from DB."""
        # dtos = self.repo.get_all(status=StrategyStatus.ACTIVE)
        dtos = self.repo.get_all()
        logger.info(f"Loading strategies from DB: {len(dtos)}")
        for dto in dtos:
            try:
                logger.info(f"Loading strategy {dto.strategy_id} ({dto.type})")
                self._instantiate_strategy(dto)
            except Exception as e:
                logger.error(f"Failed to load strategy {dto.strategy_id:8<}: {e}")
                logger.error(traceback.format_exc())
                # Potentially mark as ERROR in DB?
    
    def create_strategy(self, type_name: str, ticker: str, budget: Decimal, config: Dict[str, Any], pocket_id: Optional[str] = None) -> str:
        """Create and start a new strategy."""
        if type_name not in self.strategy_classes:
            raise ValueError(f"Unknown strategy type: {type_name}")
        
        dto = StrategyDTO(
            type=type_name,
            ticker=ticker,
            budget=budget,
            pocket_id=pocket_id,
            config=config,
            state={},
            status=StrategyStatus.ACTIVE
        )
        
        self.repo.save(dto)
        self._instantiate_strategy(dto)

        # callback
        self.observer.on_strategy_created(dto)
        
        log_msg = f"Created strategy {dto.strategy_id} ({type_name}) for {ticker}"
        if pocket_id:
            log_msg += f" (Pocket: {pocket_id})"
        logger.info(log_msg)
        return dto.strategy_id

    def add_strategy(self, strategy: StrategyBase):
        """Add an already instantiated strategy."""
        # Ensure it's active
        strategy_id = strategy.context.strategy_id
        type_name = strategy.config.strategy_type
        
        # Verify it uses a known type, or auto-register?
        # Ideally we should register it if unknown, but for now let's assume valid type.
        
        dto = StrategyDTO(
            strategy_id=strategy_id,
            type=type_name,
            ticker=strategy.context.ticker,
            budget=strategy.context.budget,
            pocket_id=strategy.context.pocket_id,
            config=strategy.config.model_dump(), # Assuming Pydantic model
            state=strategy.get_state(),
            status=StrategyStatus.ACTIVE
        )
        
        self.repo.save(dto)
        self.strategies[strategy_id] = strategy

        # callback
        self.observer.on_strategy_created(strategy)
        
        logger.info(f"Added strategy instance {strategy_id} ({type_name})")

    def _instantiate_strategy(self, dto: StrategyDTO):
        """Helper to instantiate and restore a strategy."""
        cls = self.strategy_classes[dto.type]
        
        config_cls = getattr(cls, 'ConfigModel', StrategyConfig)
        config_obj = config_cls(**dto.config)

        context = StrategyContext(
            strategy_id=dto.strategy_id,
            ticker=dto.ticker,
            budget=dto.budget,
            pocket_id=dto.pocket_id,
            last_execution_time=dto.last_execution_time
        )
        
        instance = cls(context, config_obj)
        instance.restore_state(dto.state)
        self.strategies[dto.strategy_id] = instance
        logger.info(f"Instantiated strategy {dto.strategy_id:8} ({dto.type})")

    def on_tick(self, ticker: str, price: Decimal):
        """Process price update for all relevant strategies."""
        price = Decimal(str(price)) # Ensure Decimal
        for strategy_id, strategy in self.strategies.items():
            if strategy.context.ticker == ticker:
                # If strategy is linked to a position, ideally we check if position is active?
                # But here we just assume if it's running it processes ticks.
                try:
                    signal = strategy.on_tick(price)
                    if signal:
                        self.process_signal(signal)
                        self._persist_strategy(strategy_id)
                    elif strategy.is_updated:
                        self._persist_strategy(strategy_id)
                        strategy.is_updated = False # Reset flag
                except Exception as e:
                    logger.error(f"Error in strategy {strategy_id}: {e}")

    def on_orderbook(self, ticker: str, orderbook: Dict[str, Any]):
        """Process orderbook update for all relevant strategies."""
        for strategy_id, strategy in self.strategies.items():
            if strategy.context.ticker == ticker:
                try:
                    signal = strategy.on_orderbook(orderbook)
                    if signal:
                        self.process_signal(signal)
                        self._persist_strategy(strategy_id)
                    elif strategy.is_updated:
                        self._persist_strategy(strategy_id)
                        strategy.is_updated = False
                except Exception as e:
                    logger.error(f"Error in strategy {strategy_id} on_orderbook: {e}")

    def on_schedule(self):
        """Check time-based schedules for all strategies."""
        current_time = time.time()
        
        for strategy_id, strategy in self.strategies.items():
            should_run = False
            
            # 1. Interval Check
            interval = strategy.config.execution_interval
            if interval and interval > 0:
                # Check against last_execution in state
                last_exec = strategy.context.last_execution_time
                if current_time - last_exec >= interval:
                    should_run = True
            
            # 2. Crontab Schedule Check (MVP Stub)
            # if strategy.config.schedule:
            #     # TODO: Integrate 'croniter' or similar for parsing
            #     pass

            if should_run:
                try:
                    signal = strategy.on_schedule()
                    
                    # Update state with last execution time
                    strategy.context.last_execution_time = current_time
                    self._persist_strategy(strategy_id)
                    
                    self._persist_strategy(strategy_id)
                    
                    if signal:
                        self.process_signal(signal)
                        self._persist_strategy(strategy_id) # Persist again if signal modified state
                    elif strategy.is_updated:
                        self._persist_strategy(strategy_id)
                        strategy.is_updated = False
                    
                except Exception as e:
                    logger.error(f"Error in strategy {strategy_id} schedule: {e}")

    def process_signal(self, signal: Signal):
        """Execute actions based on signal."""
        logger.info(f"Processing signal: {signal.model_dump_json( )}")
        
        try:
            strategy = self.strategies.get(signal.strategy_id)
            if strategy:
                self.observer.on_strategy_signal(strategy, signal)
            else:
                logger.warning(f"Ignored signal from unknown strategy: {signal.strategy_id}")
        except Exception as e:
            logger.error(f"Failed to execute signal {signal}: {e}")
            
    def _persist_strategy(self, strategy_id: str):
        """Save current state of strategy to DB."""
        strategy = self.strategies.get(strategy_id)
        if not strategy:
            return
            
        dto = self.repo.get(strategy_id)
        if dto:
            dto.state = strategy.get_state()
            dto.updated_at = time.time()
            dto.last_execution_time = strategy.context.last_execution_time
            self.repo.save(dto)
            
            # Notify observer of update (e.g. Dashboard)
            self.observer.on_strategy_updated(strategy)

    def stop_strategy(self, strategy_id: str):
        """Stop a strategy."""
        if strategy_id in self.strategies:
            del self.strategies[strategy_id]
            
        dto = self.repo.get(strategy_id)
        if dto:
            dto.status = StrategyStatus.STOPPED
            dto.updated_at = time.time()
            self.repo.save(dto)

            # callback
            self.observer.on_strategy_deleted(dto)
            
            logger.info(f"Stopped strategy {strategy_id}")

    def archive_strategy(self, strategy_id: str):
        """Archive a strategy (move to archive table and remove from memory)."""
        if strategy_id in self.strategies:
            del self.strategies[strategy_id]
        
        try:
            dto = self.repo.get(strategy_id)
            self.repo.archive(strategy_id)
            logger.info(f"Archived strategy {strategy_id}")

            # callback
            self.observer.on_strategy_deleted(dto)
            
        except Exception as e:
            logger.error(f"Failed to archive strategy {strategy_id:8}: {e}")
            logger.warning(traceback.format_exc())

    def load_strategies_by_pocket_id(self, pocket_id: str) -> List[str]:
        """
        Check active strategies and return list of strategy types linked to the pocket_id.
        """
        return [
            s.config.strategy_type 
            for s in self.strategies.values() 
            if s.context.pocket_id == pocket_id
        ]

    def delete_strategies_by_pocket_id(self, pocket_id: str):
        """Delete all strategies associated with a pocket_id."""
        logger.info(f"Deleting strategies for Pocket {pocket_id}")
        
        # Identify strategies to delete first to avoid runtime error during iteration
        to_delete = []
        
        # 1. Check Active Strategies (Memory)
        for strategy_id, strategy in self.strategies.items():
            if strategy.context.pocket_id == pocket_id:
                to_delete.append(strategy_id)
        
        # 2. Check DB (for stopped/inactive ones if needed? Or just all ACTIVE ones)
        # Using repo to find all strategies with pocket_id might be better?
        # Current Repo interface doesn't support complex filtering easily, but we can iterate.
        all_dtos = self.repo.get_all()
        for dto in all_dtos:
            if dto.pocket_id == pocket_id and dto.strategy_id not in to_delete:
                to_delete.append(dto.strategy_id)
        
        for strategy_id in to_delete:
            self.stop_strategy(strategy_id)
            self.archive_strategy(strategy_id)
