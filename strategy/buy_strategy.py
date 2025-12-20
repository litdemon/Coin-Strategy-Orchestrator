from decimal import Decimal
from typing import Optional, Dict, Any, List
import time
import pyupbit
import pandas as pd
import numpy as np
from strategy.base import StrategyBase
from strategy.models import StrategyContext, StrategyConfig, Signal, SignalType, StrategyType

class ScalpingStrategyConfig(StrategyConfig):
    name: str = "scalping_strategy"
    type: StrategyType = StrategyType.BUY
    
    # 매수 설정
    buy_amount: Decimal
    
    # 수익/손절 설정
    take_profit_pct: Decimal = Decimal("0.008")  # 0.8% 익절
    stop_loss_pct: Decimal = Decimal("0.005")    # 0.5% 손절
    
    # 신호 강도 임계값
    min_signal_strength: int = 5  # 최소 5점 이상
    strong_signal_threshold: int = 7  # 7점 이상이면 강한 매수
    
    # 체크 간격
    check_interval: int = 60  # 1분마다 체크
    
    # 지표 설정
    ma_short_period: int = 5
    ma_long_period: int = 20
    rsi_period: int = 14
    rsi_oversold: int = 40
    bb_period: int = 20
    bb_std: int = 2
    volume_surge_multiplier: float = 1.5
    
    # 호가창 설정
    min_buy_pressure: float = 0.52  # 최소 매수 압력 52%
    
    class Config:
        arbitrary_types_allowed = True


class ScalpingStrategy(StrategyBase):
    """
    1분봉 기반 스캘핑 전략
    - 다중 기술적 지표 분석
    - 호가창 매수/매도 압력 분석
    - 점수 기반 진입 신호
    """
    ConfigModel = ScalpingStrategyConfig

    def __init__(self, context: StrategyContext, config: ScalpingStrategyConfig):
        super().__init__(context, config)
        self.config: ScalpingStrategyConfig = config
        self.last_check_time: float = 0
        self.position_entry_price: Optional[Decimal] = None
        self.last_signal_strength: int = 0
        
    def _get_market_data(self) -> pd.DataFrame:
        """1분봉 데이터 가져오기"""
        try:
            df = pyupbit.get_ohlcv(self.context.ticker, count=600, period=1)
            if df is None or df.empty:
                self.logger.warning(f"Failed to get market data for {self.context.ticker}")
                return pd.DataFrame()
            return df
        except Exception as e:
            self.logger.error(f"Error getting market data: {e}")
            return pd.DataFrame()
    
    def _get_orderbook_pressure(self) -> Dict[str, Any]:
        """호가창 매수/매도 압력 분석"""
        try:
            orderbook = pyupbit.get_orderbook(ticker=[self.context.ticker])
            if not orderbook or len(orderbook) == 0:
                return {'buy_pressure': 0.5, 'bid_volume': 0, 'ask_volume': 0}
            
            orderbook = orderbook[0]
            
            # 매수/매도 호가 총량 계산
            bid_volume = sum([item['size'] for item in orderbook['orderbook_units']])
            ask_volume = sum([item['size'] for item in orderbook['orderbook_units']])
            
            # 매수 압력 비율
            total_volume = bid_volume + ask_volume
            buy_pressure = bid_volume / total_volume if total_volume > 0 else 0.5
            
            return {
                'bid_volume': bid_volume,
                'ask_volume': ask_volume,
                'buy_pressure': buy_pressure
            }
        except Exception as e:
            self.logger.error(f"Error getting orderbook: {e}")
            return {'buy_pressure': 0.5, 'bid_volume': 0, 'ask_volume': 0}
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """기술적 지표 계산"""
        if df.empty:
            return df
        
        # 이동평균선
        df['ma_short'] = df['close'].rolling(window=self.config.ma_short_period).mean()
        df['ma_long'] = df['close'].rolling(window=self.config.ma_long_period).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.config.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.config.rsi_period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 볼린저 밴드
        df['bb_middle'] = df['close'].rolling(window=self.config.bb_period).mean()
        bb_std = df['close'].rolling(window=self.config.bb_period).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * self.config.bb_std)
        df['bb_lower'] = df['bb_middle'] - (bb_std * self.config.bb_std)
        
        # 거래량 이동평균
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        df['volume_surge'] = df['volume'] > (df['volume_ma'] * self.config.volume_surge_multiplier)
        
        return df
    
    def _analyze_signal(self, df: pd.DataFrame, orderbook_data: Dict) -> Dict[str, Any]:
        """진입 신호 분석"""
        if len(df) < 3:
            return {'score': 0, 'reasons': [], 'action': 'HOLD'}
        
        current = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        
        score = 0
        reasons = []
        
        # 1. 이동평균선 분석
        if pd.notna(current['ma_short']) and pd.notna(current['ma_long']):
            if current['ma_short'] > current['ma_long'] and prev['ma_short'] <= prev['ma_long']:
                score += 3
                reasons.append('MA 골든크로스')
            elif current['ma_short'] > current['ma_long']:
                score += 1
                reasons.append('MA 상승 정렬')
        
        # 2. RSI 분석
        if pd.notna(current['rsi']):
            if 30 < current['rsi'] < self.config.rsi_oversold and current['rsi'] > prev['rsi']:
                score += 2
                reasons.append(f'RSI 과매도 반등 ({current["rsi"]:.1f})')
            elif 40 < current['rsi'] < 60:
                score += 1
                reasons.append('RSI 중립')
        
        # 3. 볼린저 밴드 분석
        if pd.notna(current['bb_lower']) and pd.notna(prev['bb_lower']):
            if prev['close'] <= prev['bb_lower'] and current['close'] > current['bb_lower']:
                score += 2
                reasons.append('볼린저 하단 반등')
        
        # 4. 거래량 급증
        if current['volume_surge']:
            score += 2
            reasons.append('거래량 급증')
        
        # 5. 호가창 매수 압력
        buy_pressure = orderbook_data.get('buy_pressure', 0.5)
        if buy_pressure > 0.55:
            score += 2
            reasons.append(f'매수 압력 강함 ({buy_pressure:.1%})')
        elif buy_pressure > self.config.min_buy_pressure:
            score += 1
            reasons.append(f'매수 압력 우위 ({buy_pressure:.1%})')
        
        # 6. 가격 상승 모멘텀
        if current['close'] > prev['close'] and prev['close'] > prev2['close']:
            score += 2
            reasons.append('연속 상승')
        
        # 신호 결정
        action = 'HOLD'
        if score >= self.config.strong_signal_threshold:
            action = 'STRONG_BUY'
        elif score >= self.config.min_signal_strength:
            action = 'BUY'
        
        return {
            'score': score,
            'reasons': reasons,
            'action': action,
            'current_price': float(current['close']),
            'rsi': float(current['rsi']) if pd.notna(current['rsi']) else None,
            'buy_pressure': buy_pressure
        }

    def on_tick(self, current_price: Decimal) -> Optional[Signal]:
        """
        매 틱마다 호출 - 포지션 보유 시 익절/손절 체크
        """
        if self.position_entry_price is None:
            return None
        
        # 수익률 계산
        profit_pct = (current_price - self.position_entry_price) / self.position_entry_price
        
        # 익절 체크
        if profit_pct >= self.config.take_profit_pct:
            self.logger.info(f"Take profit triggered: {profit_pct:.2%}")
            self.position_entry_price = None
            return self.emit_signal(Signal(
                type=SignalType.SELL,
                strategy_id=self.context.strategy_id,
                ticker=self.context.ticker,
                reason=f"익절 실행 (수익률: {profit_pct:.2%})"
            ))
        
        # 손절 체크
        if profit_pct <= -self.config.stop_loss_pct:
            self.logger.info(f"Stop loss triggered: {profit_pct:.2%}")
            self.position_entry_price = None
            return self.emit_signal(Signal(
                type=SignalType.SELL,
                strategy_id=self.context.strategy_id,
                ticker=self.context.ticker,
                reason=f"손절 실행 (손실률: {profit_pct:.2%})"
            ))
        
        return None

    def on_schedule(self) -> Optional[Signal]:
        """
        주기적으로 호출 - 진입 시점 분석
        """
        current_time = time.time()
        
        # 체크 간격 확인
        if current_time - self.last_check_time < self.config.check_interval:
            return None
        
        self.last_check_time = current_time
        
        # 이미 포지션 보유 중이면 스킵
        if self.position_entry_price is not None:
            return None
        
        # 시장 데이터 수집
        df = self._get_market_data()
        if df.empty:
            return None
        
        # 지표 계산
        df = self._calculate_indicators(df)
        
        # 호가창 분석
        orderbook_data = self._get_orderbook_pressure()
        
        # 신호 분석
        signal_data = self._analyze_signal(df, orderbook_data)
        self.last_signal_strength = signal_data['score']
        
        # 로깅
        self.logger.info(
            f"Signal Analysis - Score: {signal_data['score']}, "
            f"Action: {signal_data['action']}, "
            f"Price: {signal_data['current_price']:,.0f}, "
            f"Reasons: {', '.join(signal_data['reasons'])}"
        )
        
        # 매수 신호 발생
        if signal_data['action'] in ['BUY', 'STRONG_BUY']:
            self.position_entry_price = Decimal(str(signal_data['current_price']))
            
            return self.emit_signal(Signal(
                type=SignalType.BUY,
                strategy_id=self.context.strategy_id,
                ticker=self.context.ticker,
                amount=self.config.buy_amount,
                reason=f"{signal_data['action']} - {', '.join(signal_data['reasons'][:3])}"
            ))
        
        return None

    def get_state(self) -> Dict[str, Any]:
        """상태 저장"""
        return {
            "last_check_time": self.last_check_time,
            "position_entry_price": str(self.position_entry_price) if self.position_entry_price else None,
            "last_signal_strength": self.last_signal_strength
        }

    def restore_state(self, state: Dict[str, Any]):
        """상태 복원"""
        self.last_check_time = state.get("last_check_time", 0)
        entry_price = state.get("position_entry_price")
        self.position_entry_price = Decimal(entry_price) if entry_price else None
        self.last_signal_strength = state.get("last_signal_strength", 0)