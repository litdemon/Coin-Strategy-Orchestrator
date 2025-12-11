import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.position_manager import Position
from src.stratege_manager import StrategyFactory
from strategy.tailingstop import TakeProfitStrategy, TakeProfitConfig, SignalType
from strategy.base import StrategyConfig, StrategyBase, Signal
import time
from typing import Dict, Any, Optional
def example_1_basic_usage():
    """예제 1: 기본 사용법"""
    print("=" * 60)
    print("Example 1: Basic Usage")
    print("=" * 60)
    
    # Position 생성
    position = Position(
        ticker="KRW-BTC",
        entry_price=50000.0,
        volume=1.0
    )
    
    # Strategy 추가 - 방법 1: 직접 추가
    position.add_strategy("trailing_stop", {
        "trail_percent": 0.05,
        "activation_percent": 0.03
    })
    
    # Strategy 추가 - 방법 2: Strategy 객체 생성 후 추가
    take_profit = TakeProfitStrategy(
        position.id,
        TakeProfitConfig(target_percent=0.10, partial=True, partial_ratio=0.5)
    )
    position.strategy_manager.add_strategy(take_profit)
    
    # 손절 추가
    position.add_strategy("stop_loss", {"stop_percent": 0.05})
    
    print(f"Position: {position.ticker}")
    print(f"Entry Price: ${position.entry_price:,.0f}")
    print(f"Active Strategies: {len(position.strategy_manager.strategies)}")
    for s in position.strategy_manager.strategies:
        print(f"  - {s.config.strategy_type}")
    
    # 가격 업데이트
    print("\n--- Price Updates ---")
    prices = [51000, 52000, 53000, 55000, 54000, 52500]
    
    for price in prices:
        signals = position.update_price(price)
        print(f"Price: ${price:,.0f}", end="")
        
        if signals:
            print(f" 🚨")
            for signal in signals:
                print(f"  Signal: {signal.type.value}")
                print(f"  Reason: {signal.reason}")
        else:
            print(" ✓")


def example_2_db_persistence():
    """예제 2: DB 저장 및 복원"""
    print("\n" + "=" * 60)
    print("Example 2: DB Persistence")
    print("=" * 60)
    
    # 1. Position 생성 및 Strategy 설정
    print("\n[1] Creating Position with Strategies")
    position = Position(
        ticker="ETH/USDT",
        entry_price=3000.0,
        volume=10.0
    )
    
    position.add_strategy("trailing_stop", {
        "trail_percent": 0.03,
        "activation_percent": 0.05
    })
    position.add_strategy("take_profit", {
        "target_percent": 0.15,
        "partial": False
    })
    
    # 가격 업데이트로 상태 변경
    position.update_price(3200)
    position.update_price(3300)
    
    print(f"Position ID: {position.id}")
    print(f"Strategies: {len(position.strategy_manager.strategies)}")
    
    # Strategy 상태 확인
    trailing = position.strategy_manager.get_strategy("trailing_stop")
    if trailing:
        print(f"Trailing Stop - Highest: ${trailing.highest_price}, Activated: {trailing.activated}")
    
    # 2. DB 저장
    print("\n[2] Saving to DB")
    db_data = position.to_db_dict()
    print(f"DB Data Keys: {list(db_data.keys())}")
    print(f"Strategies Data Length: {len(db_data.get('strategies_data', ''))}")
    
    # 3. DB에서 복원
    print("\n[3] Restoring from DB")
    restored_position = Position.from_db_dict(db_data)
    print(f"Restored Position ID: {restored_position.id}")
    print(f"Restored Strategies: {len(restored_position.strategy_manager.strategies)}")
    
    # Strategy 상태 복원 확인
    restored_trailing = restored_position.strategy_manager.get_strategy("trailing_stop")
    if restored_trailing:
        print(f"Restored Trailing Stop - Highest: ${restored_trailing.highest_price}, Activated: {restored_trailing.activated}")
    
    # 4. 복원된 Position으로 계속 작업
    print("\n[4] Continue with Restored Position")
    signals = restored_position.update_price(3400)
    if signals:
        print(f"Signals Generated: {len(signals)}")
        for signal in signals:
            print(f"  - {signal.type.value}: {signal.reason}")


def example_3_signal_handling():
    """예제 3: Signal 처리"""
    print("\n" + "=" * 60)
    print("Example 3: Signal Handling")
    print("=" * 60)
    
    position = Position(
        ticker="SOL/USDT",
        entry_price=100.0,
        volume=50.0
    )
    
    # 여러 Strategy 추가
    position.add_strategy("trailing_stop", {"trail_percent": 0.05})
    position.add_strategy("take_profit", {"target_percent": 0.20})
    position.add_strategy("stop_loss", {"stop_percent": 0.10})
    
    # 시나리오: 가격 상승 후 하락
    print("\n--- Scenario: Price Rise then Fall ---")
    price_sequence = [105, 110, 115, 120, 125, 120, 115, 110, 105, 100, 95, 90]
    
    for price in price_sequence:
        signals = position.update_price(price)
        
        profit_pct = (price - position.entry_price) / position.entry_price * 100
        print(f"\nPrice: ${price:,.0f} (P&L: {profit_pct:+.1f}%)")
        
        if signals:
            for signal in signals:
                print(f"  🚨 {signal.type.value.upper()}")
                print(f"     {signal.reason}")
                
                # Signal 타입별 처리 예시
                if signal.type == SignalType.CLOSE:
                    print(f"     → Execute: Close entire position")
                    position.status = "closed"
                    position.close_price = price
                    position.close_time = time.time()
                    break
                    
                elif signal.type == SignalType.PARTIAL_CLOSE:
                    ratio = signal.data.get('close_ratio', 0.5)
                    close_volume = position.volume * ratio
                    print(f"     → Execute: Close {close_volume} units ({ratio*100:.0f}%)")
                    position.volume -= close_volume
        
        if position.status == "closed":
            print("\n💰 Position Closed!")
            break


def example_4_custom_strategy():
    """예제 4: 커스텀 Strategy 추가"""
    print("\n" + "=" * 60)
    print("Example 4: Custom Strategy")
    print("=" * 60)
    
    # 커스텀 Strategy: 시간 기반 청산
    class TimeBasedExitConfig(StrategyConfig):
        strategy_type: str = "time_based_exit"
        max_hold_seconds: float
    
    class TimeBasedExitStrategy(StrategyBase):
        """일정 시간 후 자동 청산"""
        
        def update(self, current_price: float, position: Position) -> Optional[Signal]:
            config: TimeBasedExitConfig = self.config
            hold_time = time.time() - position.entry_time
            
            if hold_time >= config.max_hold_seconds:
                return self.emit_signal(Signal(
                    type=SignalType.CLOSE,
                    position_id=self.position_id,
                    reason=f"Time limit reached ({hold_time:.0f}s)",
                    data={"hold_time": hold_time}
                ))
            return None
        
        def to_dict(self) -> Dict[str, Any]:
            return {
                "strategy_type": "time_based_exit",
                "position_id": self.position_id,
                "config": self.config.model_dump(),
                "state": {}
            }
        
        @classmethod
        def from_dict(cls, data: Dict[str, Any]) -> 'TimeBasedExitStrategy':
            config = TimeBasedExitConfig(**data["config"])
            return cls(data["position_id"], config)
    
    # Factory에 등록
    StrategyFactory.register("time_based_exit", TimeBasedExitStrategy, TimeBasedExitConfig)
    
    # 사용
    position = Position(ticker="DOGE/USDT", entry_price=0.1, volume=10000)
    
    position.add_strategy("time_based_exit", {"max_hold_seconds": 5})
    position.add_strategy("take_profit", {"target_percent": 0.50})
    
    print(f"Position: {position.ticker}")
    print(f"Strategies: {[s.config.strategy_type for s in position.strategy_manager.strategies]}")
    
    # 시간 경과 시뮬레이션
    print("\n--- Time-based Exit Test ---")
    import time as time_module
    
    for i in range(7):
        time_module.sleep(1)
        signals = position.update_price(0.12)
        
        hold_time = time.time() - position.entry_time
        print(f"Time: {hold_time:.0f}s | Price: $0.12", end="")
        
        if signals:
            print(f" 🚨 {signals[0].reason}")
            break
        else:
            print(" ✓")


# 실행
if __name__ == "__main__":
    example_1_basic_usage()
    example_2_db_persistence()
    example_3_signal_handling()
    example_4_custom_strategy()