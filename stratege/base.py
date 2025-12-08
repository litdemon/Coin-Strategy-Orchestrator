
from abc import ABC, abstractmethod

class WatchPolicy(ABC):
    """감시 정책 추상 클래스"""
    
    def __init__(self, name: str, sell_ratio: float = 1.0):
        """
        Args:
            name: 정책 이름
            sell_ratio: 조건 만족시 매도할 비율 (0.0 ~ 1.0)
        """
        self.name = name
        self.sell_ratio = sell_ratio
    
    @abstractmethod
    def check_sell_signal(self, rot: 'Rot', current_price: float) -> bool:
        """매도 신호 체크
        
        Args:
            rot: 확인할 Rot 객체
            current_price: 현재 코인 가격
            
        Returns:
            매도 신호 여부
        """
        pass