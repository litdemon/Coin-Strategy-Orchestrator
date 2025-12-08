

from typing import Any
from stratege.base import WatchPolicy

class StopLossPolicy(WatchPolicy):
    """손절 정책"""
    
    def __init__(self, loss_percent: float, sell_ratio: float = 1.0):
        super().__init__(f"StopLoss_{loss_percent}%", sell_ratio)
        self.loss_percent = loss_percent
    
    def check_sell_signal(self, position: Any, current_price: float) -> bool:
        loss_rate = ((current_price - position.entry_price) / position.entry_price) * 100
        return loss_rate <= -self.loss_percent


class TakeProfitPolicy(WatchPolicy):
    """익절 정책"""
    
    def __init__(self, profit_percent: float, sell_ratio: float = 1.0):
        super().__init__(f"TakeProfit_{profit_percent}%", sell_ratio)
        self.profit_percent = profit_percent
    
    def check_sell_signal(self, position: Any, current_price: float) -> bool:
        profit_rate = ((current_price - position.entry_price) / position.entry_price) * 100
        return profit_rate >= self.profit_percent


class TrailingStopPolicy(WatchPolicy):
    """트레일링 스탑 정책"""
    
    def __init__(self, trailing_percent: float, sell_ratio: float = 1.0):
        super().__init__(f"TrailingStop_{trailing_percent}%", sell_ratio)
        self.trailing_percent = trailing_percent
        self.highest_price = 0.0
    
    def check_sell_signal(self, position: Any, current_price: float) -> bool:
        # Position 객체에 highest_price가 있다고 가정
        if not hasattr(position, 'highest_price'):
            return False
            
        if current_price > position.highest_price:
            position.highest_price = current_price
        
        if position.highest_price == 0:
            return False
            
        drop_rate = ((current_price - position.highest_price) / position.highest_price) * 100
        return drop_rate <= -self.trailing_percent