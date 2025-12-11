from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from pydantic import BaseModel, Field
from enum import Enum
import uuid
import time
import json

if TYPE_CHECKING:
    from models.position import PositionBase


class SignalType(Enum):
    CLOSE = "close"
    PARTIAL_CLOSE = "partial_close"
    UPDATE_STOP = "update_stop"


class Signal(BaseModel):
    """Strategy에서 발생하는 신호"""
    type: SignalType
    position_id: str
    reason: str
    data: Optional[Dict[str, Any]] = None
    timestamp: float = Field(default_factory=time.time)


class StrategyConfig(BaseModel):
    """Strategy 설정을 저장하기 위한 베이스 클래스"""
    strategy_type: str
    
    class Config:
        extra = "allow"  # 추가 필드 허용


class StrategyBase(ABC):
    """Strategy 베이스 클래스"""
    
    def __init__(self, position_id: str, config: StrategyConfig):
        self.position_id = position_id
        self.config = config
        self.signals: List[Signal] = []
    
    @abstractmethod
    def update(self, current_price: float, position: 'Position') -> Optional[Signal]:
        """가격 업데이트 시 호출, Signal 반환"""
        pass
    
    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Strategy를 dict로 직렬화 (DB 저장용)"""
        pass
    
    @classmethod
    @abstractmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StrategyBase':
        """dict에서 Strategy 복원"""
        pass
    
    def emit_signal(self, signal: Signal):
        """신호 발생"""
        self.signals.append(signal)
        return signal
