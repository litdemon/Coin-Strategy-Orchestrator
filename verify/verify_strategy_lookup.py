from unittest.mock import MagicMock
from strategy.manager import StrategyManager
from strategy.models import StrategyContext, StrategyConfig

def test_load_strategies_by_position_id():
    # Mock dependencies
    mock_repo = MagicMock()
    mock_account = MagicMock()
    
    # Mock StrategyManager partially
    manager = StrategyManager(":memory:", mock_account)
    manager.repo = mock_repo # Override repo
    
    # Create fake strategies
    strat1 = MagicMock()
    strat1.context = StrategyContext(strategy_id="s1", ticker="BTC", budget=100, position_id="pos1")
    strat1.config = StrategyConfig(strategy_type="TrailingStop")
    
    strat2 = MagicMock()
    strat2.context = StrategyContext(strategy_id="s2", ticker="ETH", budget=100, position_id="pos2")
    strat2.config = StrategyConfig(strategy_type="RSI")
    
    strat3 = MagicMock() # Multiple strat on one pos
    strat3.context = StrategyContext(strategy_id="s3", ticker="BTC", budget=100, position_id="pos1")
    strat3.config = StrategyConfig(strategy_type="MACD")

    # Inject into manager
    manager.strategies = {
        "s1": strat1,
        "s2": strat2,
        "s3": strat3
    }
    
    # Test
    strategies_pos1 = manager.load_strategies_by_position_id("pos1")
    print(f"Strategies for pos1: {strategies_pos1}")
    
    if "TrailingStop" in strategies_pos1 and "MACD" in strategies_pos1 and len(strategies_pos1) == 2:
        print("SUCCESS: Found correct strategies for pos1")
    else:
        print("FAILURE: Incorrect strategies for pos1")

    strategies_pos2 = manager.load_strategies_by_position_id("pos2")
    print(f"Strategies for pos2: {strategies_pos2}")
    
    if strategies_pos2 == ["RSI"]:
        print("SUCCESS: Found correct strategies for pos2")
    else:
        print("FAILURE: Incorrect strategies for pos2")
        
    strategies_pos_none = manager.load_strategies_by_position_id("pos_none")
    if strategies_pos_none == []:
        print("SUCCESS: Found no strategies for non-existent pos")
    else:
         print(f"FAILURE: Found strategies for non-existent pos: {strategies_pos_none}")

if __name__ == "__main__":
    test_load_strategies_by_position_id()
