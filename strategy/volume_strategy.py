from decimal import Decimal
from typing import Optional, Dict, Any
import pyupbit
import pandas as pd
import logging
from strategy.base import StrategyBase
from strategy.models import StrategyContext, StrategyConfig, Signal, SignalType, StrategyType

logger = logging.getLogger(__name__)

class VolumeSpikeStrategyConfig(StrategyConfig):
    name: str = "volume_spike_strategy"
    type: StrategyType = StrategyType.BUY
    
    execution_interval: int = 60  # 1 minute
    period: int = 20
    multiplier: float = 1.5
    buy_amount: Decimal # Required for execution logic to know how much to buy

    class Config:
        arbitrary_types_allowed = True

class VolumeSpikeStrategy(StrategyBase):
    """
    Test Strategy: Buy when volume spikes.
    Logic: Current 1min volume > (Average of previous 20 1min volumes) * 1.5
    """
    ConfigModel = VolumeSpikeStrategyConfig

    def __init__(self, context: StrategyContext, config: VolumeSpikeStrategyConfig):
        super().__init__(context, config)
        self.config: VolumeSpikeStrategyConfig = config
        self.logger = logging.getLogger(__name__)
        self.last_volume_ratio = 0.0

    def on_tick(self, current_price: Decimal) -> Optional[Signal]:
        # This strategy relies on scheduled checks (1 min candles), not tick updates.
        return None

    def on_schedule(self) -> Optional[Signal]:
        """Check 1-minute candles for volume spike."""
        try:
            # Get enough data for period + correlation
            count = self.config.period + 5 
            df = pyupbit.get_ohlcv(self.context.ticker, interval="minute1", count=count)
            
            if df is None or df.empty or len(df) < self.config.period + 1:
                logger.warning(f"Not enough data for {self.context.ticker}")
                return None

            # Current Candle (might be incomplete if fetching precisely at min start, 
            # but usually 'minute1' returns completed candles + current partial. 
            # We want the LAST COMPLETED candle or CURRENT evolving candle?
            # Standard backtesting logic usually uses closed candles. 
            # Real-time logic often checks current evolving volume vs avg.
            # Let's use the most recent closed candle to be safe and avoiding repainting issues,
            # OR check the current forming candle if we want immediate reaction.
            # User requirement: "1분 단위로 검사" (Check every 1 minute).
            # If we check every 60s, we are likely looking at the just-closed candle.
            
            # df.iloc[-1] is the current (potentially incomplete) candle or just closed?
            # pyupbit get_ohlcv includes the current open candle as the last row.
            
            # Let's look at the *current* volume (df.iloc[-1]['volume']) 
            # vs Average of previous self.config.period candles (iloc[-period-1 : -1])
            
            current_volume = df.iloc[-1]['volume']
            previous_candles = df.iloc[-(self.config.period + 1):-1]
            avg_volume = previous_candles['volume'].mean()

            if avg_volume == 0:
                return None

            ratio = current_volume / avg_volume
            self.last_volume_ratio = ratio
            
            self.display = f"Vol Ratio: {ratio:.2f}x"
            self.is_updated = True
            
            if ratio >= self.config.multiplier:
                logger.info(f"Volume Spike Detected! Ratio: {ratio:.2f} > {self.config.multiplier}")
                
                signal = Signal(
                    type=SignalType.BUY,
                    ticker=self.context.ticker,
                    strategy_id=self.context.strategy_id,
                    amount=self.config.buy_amount,
                    reason=f"Volume Spike {ratio:.2f}x",
                    data={"ratio": ratio, "current_volume": current_volume, "avg_volume": avg_volume}
                )
                return self.emit_signal(signal)
            
        except Exception as e:
            logger.error(f"Error in VolumeSpikeStrategy: {e}")
        
        return None

    def get_state(self) -> Dict[str, Any]:
        return {
            "last_volume_ratio": self.last_volume_ratio
        }

    def restore_state(self, state: Dict[str, Any]):
        self.last_volume_ratio = state.get("last_volume_ratio", 0.0)
