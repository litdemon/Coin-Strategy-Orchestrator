from decimal import Decimal
from typing import Optional, Dict, Any, List
import pyupbit
import pandas as pd
import numpy as np
import logging
from strategy.base import StrategyBase
from strategy.models import StrategyContext, StrategyConfig, Signal, SignalType, StrategyType

logger = logging.getLogger(__name__)

class AnomalyStrategyConfig(StrategyConfig):
    name: str = "anomaly_detection"
    type: StrategyType = StrategyType.BUY
    
    execution_interval: int = 60  # 1 minute
    period: int = 60              # Lookback period (e.g., 60 minutes)
    z_score_threshold: float = 3.0 
    buy_amount: Decimal           # Amount to buy on signal
    
    # Mode: "DIP" (Buy on negative Z-score), "MOMENTUM" (Buy on positive), "BOTH" (Any outlier)
    mode: str = "DIP" 

    class Config:
        arbitrary_types_allowed = True

class AnomalyStrategy(StrategyBase):
    """
    Anomaly Detection Strategy using Z-Score on 1-minute OHLC Log Returns.
    
    Logic:
    1. Calculate Log Returns: ln(Close_t / Close_t-1)
    2. Compute Mean and StdDev over 'period'.
    3. Compute Z-Score of current return.
    4. Trigger Signal if Z-Score exceeds threshold based on mode.
    """
    ConfigModel = AnomalyStrategyConfig

    def __init__(self, context: StrategyContext, config: AnomalyStrategyConfig):
        super().__init__(context, config)
        self.config: AnomalyStrategyConfig = config
        self.logger = logging.getLogger(__name__)

    def on_tick(self, current_price: Decimal) -> Optional[Signal]:
        # Relies on scheduled 1-min OHLC checks
        return None

    def on_schedule(self) -> Optional[Signal]:
        """Check 1-minute candles for anomalies."""
        try:
            # Need period + 1 for returns calculation
            count = self.config.period + 10
            df = pyupbit.get_ohlcv(self.context.ticker, interval="minute1", count=count)
            
            if df is None or df.empty or len(df) < self.config.period + 2:
                self.logger.warning(f"Not enough data for {self.context.ticker} anomaly detection")
                return None
            
            # 1. Feature Engineering: Log Returns
            # Log Return = ln(Close / PrevClose)
            # Use 'close' column
            df['close'] = df['close'].astype(float)
            df['log_return'] = np.log(df['close'] / df['close'].shift(1))
            
            # Drop NaN created by shift
            df = df.dropna()
            
            if len(df) < self.config.period + 1:
                return None

            # 2. Statistics on Rolling Window (excluding current candle? or including?)
            # We want to check if CURRENT candle is anomalous compared to history.
            # History = last 'period' candles BEFORE current.
            # df.iloc[-1] is the current (potentially incomplete if queried mid-minute? Pyupbit usually returns completed or current updating)
            # Pyupbit get_ohlcv(count) includes the latest candle which might be actively updating.
            # Using it might be noisy. But anomaly usually implies "Right Now".
            
            current_candle = df.iloc[-1]
            history = df.iloc[-1-self.config.period : -1] # Last 'period' candles excluding current
            
            if history.empty:
                return None
                
            mean = history['log_return'].mean()
            std = history['log_return'].std()
            
            if std == 0:
                return None
                
            current_return = current_candle['log_return']
            z_score = (current_return - mean) / std
            
            self.logger.debug(f"{self.context.ticker} Z-Score: {z_score:.2f} (Ret: {current_return:.4%}, Mean: {mean:.4%}, Std: {std:.4%})")
            
            # 3. Detection Logic
            is_anomaly = False
            reason = ""
            
            if self.config.mode == "DIP" and z_score < -self.config.z_score_threshold:
                 is_anomaly = True
                 reason = f"Negative Anomaly (Dip) Detected. Z-Score: {z_score:.2f}"
            elif self.config.mode == "MOMENTUM" and z_score > self.config.z_score_threshold:
                 is_anomaly = True
                 reason = f"Positive Anomaly (Momentum) Detected. Z-Score: {z_score:.2f}"
            elif self.config.mode == "BOTH" and abs(z_score) > self.config.z_score_threshold:
                 is_anomaly = True
                 desc = "Dip" if z_score < 0 else "Momentum"
                 reason = f"Volatility Anomaly ({desc}) Detected. Z-Score: {z_score:.2f}"
            
            if is_anomaly:
                self.logger.info(f"{reason} for {self.context.ticker}")
                return self.emit_signal(Signal(
                    type=SignalType.BUY, # Assuming usage is for entry.
                    strategy_id=self.context.strategy_id,
                    ticker=self.context.ticker,
                    amount=self.config.buy_amount,
                    reason=reason,
                    data={
                        "z_score": float(z_score),
                        "current_return": float(current_return),
                        "mean": float(mean),
                        "std": float(std),
                        "period": self.config.period,
                        "close": float(current_candle['close'])
                    }
                ))

        except Exception as e:
            self.logger.error(f"Error in AnomalyStrategy: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            
        return None
