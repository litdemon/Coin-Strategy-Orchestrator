import logging
import time
from typing import Dict, Type, List, Optional, Any
from decimal import Decimal

from strategy.models import StrategyContext, StrategyConfig, StrategyDTO, StrategyStatus, Signal, SignalType
from strategy.base import StrategyBase
from strategy.repository import StrategyRepository
from account.manager import AccountBase
import traceback

logger = logging.getLogger(__name__)

class StrategyManager:
    def __init__(self, db_path: str, account_manager: AccountBase):
        self.repo = StrategyRepository(db_path)
        self.account_manager = account_manager
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
    
    def create_strategy(self, type_name: str, ticker: str, budget: Decimal, config: Dict[str, Any], position_id: Optional[str] = None) -> str:
        """Create and start a new strategy."""
        if type_name not in self.strategy_classes:
            raise ValueError(f"Unknown strategy type: {type_name}")
        
        dto = StrategyDTO(
            type=type_name,
            ticker=ticker,
            budget=budget,
            position_id=position_id,
            config=config,
            state={},
            status=StrategyStatus.ACTIVE
        )
        
        self.repo.save(dto)
        self._instantiate_strategy(dto)
        
        log_msg = f"Created strategy {dto.strategy_id} ({type_name}) for {ticker}"
        if position_id:
            log_msg += f" (Position: {position_id})"
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
            position_id=strategy.context.position_id,
            config=strategy.config.model_dump(), # Assuming Pydantic model
            state=strategy.get_state(),
            status=StrategyStatus.ACTIVE
        )
        
        self.repo.save(dto)
        self.strategies[strategy_id] = strategy
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
            position_id=dto.position_id,
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
                    
                    if signal:
                        self.process_signal(signal)
                        self._persist_strategy(strategy_id) # Persist again if signal modified state
                    
                except Exception as e:
                    logger.error(f"Error in strategy {strategy_id} schedule: {e}")

    def process_signal(self, signal: Signal):
        """Execute actions based on signal."""
        logger.info(f"Processing signal: {signal}")
        
        try:
            if signal.type == SignalType.BUY:
                # execute buy
                if signal.price:
                     self.account_manager.buy_limit_order(signal.ticker, signal.price, signal.amount)
                else:
                     self.account_manager.buy_market_order(signal.ticker, signal.amount)

            elif signal.type == SignalType.SELL:
                 # execute sell
                if signal.price:
                    self.account_manager.sell_limit_order(signal.ticker, signal.price, signal.amount)
                else:
                    self.account_manager.sell_market_order(signal.ticker, signal.amount)

            elif signal.type == SignalType.CLOSE_POSITION:
                # Close specific position if linked, or ticker balance
                target_position_id = signal.data.get("position_id") or self.strategies[signal.strategy_id].context.position_id
                
                if target_position_id:
                     # Specific Position Close Logic
                     # We need to know the volume of that position.
                     # PositionRepo? AccountManager doesn't track "Positions" with ID in the new architecture yet?
                     # Models/position.py exists but AccountManager uses Asset/Order.
                     # If we use strict Position ID, we need a Position Manager/Repo.
                     # For now, fall back to Ticker close but Log the ID.
                     logger.info(f"Closing specific position {target_position_id} (Logic falls back to ticker sell for now)")
                
                # Fetch current balance
                balance = self.account_manager.get_balance(signal.ticker)
                
                if balance > 0:
                    ratio = Decimal("1.0")
                    if signal.data and "close_ratio" in signal.data:
                         ratio = Decimal(str(signal.data["close_ratio"]))
                    
                    volume_to_sell = balance * ratio
                    self.account_manager.sell_market_order(signal.ticker, volume_to_sell)
                    logger.info(f"Closed position for {signal.ticker}: {volume_to_sell} units (Ratio: {ratio})")
                else:
                    logger.warning(f"Signal received to Close Position for {signal.ticker} but balance is 0.")

            elif signal.type == SignalType.PARTIAL_CLOSE:
                # Reuse logic
                balance = self.account_manager.get_balance(signal.ticker)
                if balance > 0:
                    ratio = Decimal("0.5")
                    if signal.data and "close_ratio" in signal.data:
                         ratio = Decimal(str(signal.data["close_ratio"]))
                    
                    volume_to_sell = balance * ratio
                    self.account_manager.sell_market_order(signal.ticker, volume_to_sell) 
                    logger.info(f"Partial close {signal.ticker}: {volume_to_sell} units")

        except Exception as e:
            logger.error(f"Failed to execute signal {signal}: {e}")
            
        # TODO: Implement actual execution logic with AccountManager
        
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

    def stop_strategy(self, strategy_id: str):
        """Stop a strategy."""
        if strategy_id in self.strategies:
            del self.strategies[strategy_id]
            
        dto = self.repo.get(strategy_id)
        if dto:
            dto.status = StrategyStatus.STOPPED
            dto.updated_at = time.time()
            self.repo.save(dto)
            self.repo.save(dto)
            logger.info(f"Stopped strategy {strategy_id}")

    def archive_strategy(self, strategy_id: str):
        """Archive a strategy (move to archive table and remove from memory)."""
        if strategy_id in self.strategies:
            del self.strategies[strategy_id]
        
        try:
            self.repo.archive(strategy_id)
            logger.info(f"Archived strategy {strategy_id}")
        except Exception as e:
            logger.error(f"Failed to archive strategy {strategy_id}: {e}")

    def load_strategies_by_position_id(self, position_id: str) -> List[str]:
        """
        Check active strategies and return list of strategy types linked to the position_id.
        """
        return [
            s.config.strategy_type 
            for s in self.strategies.values() 
            if s.context.position_id == position_id
        ]
