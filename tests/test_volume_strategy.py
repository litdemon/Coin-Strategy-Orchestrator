import unittest
from unittest.mock import MagicMock, patch
from decimal import Decimal
import pandas as pd
from datetime import datetime, timedelta

from strategy.models import StrategyContext, SignalType, StrategyType
from strategy.volume_strategy import VolumeSpikeStrategy, VolumeSpikeStrategyConfig

class TestVolumeSpikeStrategy(unittest.TestCase):
    def setUp(self):
        self.context = StrategyContext(
            strategy_id="test-strat",
            ticker="KRW-BTC",
            budget=Decimal("10000")
        )
        self.config = VolumeSpikeStrategyConfig(
            name="volume_spike_strategy",
            type=StrategyType.BUY,
            check_interval=60,
            buy_amount=Decimal("10000"),
            period=20,
            multiplier=1.5
        )
        self.strategy = VolumeSpikeStrategy(self.context, self.config)

    @patch('pyupbit.get_ohlcv')
    def test_on_schedule_triggers_buy_signal(self, mock_get_ohlcv):
        # 1. Prepare Mock Data (21 rows: 20 previous + 1 current)
        # Average volume should be 100.
        # Current volume should be 160 (1.6x -> > 1.5x)
        
        data = []
        base_time = datetime.now()
        for i in range(21):
            row = {
                'open': 100, 'high': 110, 'low': 90, 'close': 105,
                'volume': 100  # Base volume
            }
            if i == 20: # Current candle (last row)
                row['volume'] = 160 # Spike
            
            data.append(row)
        
        df = pd.DataFrame(data)
        mock_get_ohlcv.return_value = df
        
        # 2. Execute on_schedule
        signal = self.strategy.on_schedule()
        
        # 3. Verify Signal
        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.BUY)
        self.assertEqual(signal.ticker, "KRW-BTC")
        self.assertIn("Volume Spike", signal.reason)
        self.assertEqual(signal.data['ratio'], 1.6)

    @patch('pyupbit.get_ohlcv')
    def test_on_schedule_no_signal_low_volume(self, mock_get_ohlcv):
        # Current volume 100 (1.0x -> < 1.5x)
        data = []
        for i in range(21):
            row = {'open': 100, 'high': 110, 'low': 90, 'close': 105, 'volume': 100}
            data.append(row)
        
        df = pd.DataFrame(data)
        mock_get_ohlcv.return_value = df
        
        signal = self.strategy.on_schedule()
        self.assertIsNone(signal)

if __name__ == '__main__':
    unittest.main()
