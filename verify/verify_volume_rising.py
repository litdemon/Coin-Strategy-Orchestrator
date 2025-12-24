import unittest
from unittest.mock import MagicMock, patch
from decimal import Decimal
import pandas as pd
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from strategy.models import StrategyContext, SignalType
from strategy.volume_strategy import VolumeSpikeStrategy, VolumeSpikeStrategyConfig

class TestVolumeSpikeStrategy(unittest.TestCase):
    def setUp(self):
        context = StrategyContext(strategy_id="test_id", ticker="KRW-BTC", budget=Decimal("10000"))
        config = VolumeSpikeStrategyConfig(buy_amount=Decimal("10000")) 
        self.strategy = VolumeSpikeStrategy(context, config)

    @patch('strategy.volume_strategy.pyupbit.get_ohlcv')
    def test_volume_spike_rising_price(self, mock_get_ohlcv):
        """Test: Volume Spike (3.0x+) AND Price Rising -> Should Trigger Signal"""
        # Create Data: 20 candles with avg vol 100, last candle vol 350, close 105 > open 100
        data = []
        for _ in range(20):
            data.append({'volume': 100, 'open': 100, 'close': 100})
            
        # Spike Candle (Ratio 3.5, Rising)
        data.append({'volume': 350, 'open': 100, 'close': 105}) 
        
        df = pd.DataFrame(data)
        mock_get_ohlcv.return_value = df
        
        signal = self.strategy.on_schedule()
        
        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.BUY)
        self.assertIn("Volume Spike", signal.reason)
        print("Verified: Signal triggered on Spike (3.5x) + Rising Candle")

    @patch('strategy.volume_strategy.pyupbit.get_ohlcv')
    def test_volume_spike_falling_price(self, mock_get_ohlcv):
        """Test: Volume Spike (3.0x+) BUT Price Falling -> Should NOT Trigger"""
        # Create Data
        data = []
        for _ in range(20):
            data.append({'volume': 100, 'open': 100, 'close': 100})
            
        # Spike Candle (Ratio 3.5, Falling)
        data.append({'volume': 350, 'open': 105, 'close': 100}) 
        
        df = pd.DataFrame(data)
        mock_get_ohlcv.return_value = df
        
        signal = self.strategy.on_schedule()
        
        self.assertIsNone(signal)
        print("Verified: Signal suppressed on Spike (3.5x) + Falling/Flat Candle")

    @patch('strategy.volume_strategy.pyupbit.get_ohlcv')
    def test_no_spike(self, mock_get_ohlcv):
        """Test: No Volume Spike (< 3.0x) -> Should NOT Trigger"""
        data = []
        for _ in range(20):
            data.append({'volume': 100, 'open': 100, 'close': 100})
        
        # Small Spike (2.0x, Rising)
        data.append({'volume': 200, 'open': 100, 'close': 105}) 
        
        df = pd.DataFrame(data)
        mock_get_ohlcv.return_value = df
        
        signal = self.strategy.on_schedule()
        
        self.assertIsNone(signal)
        print("Verified: Signal suppressed on Small Spike (2.0x)")

if __name__ == '__main__':
    unittest.main()
