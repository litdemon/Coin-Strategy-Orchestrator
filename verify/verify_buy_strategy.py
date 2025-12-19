import pyupbit
import pandas as pd
import numpy as np
from datetime import datetime

class ScalpingSignal:
    def __init__(self, ticker="KRW-BTC"):
        self.ticker = ticker
        
    def get_market_data(self):
        """1분봉 데이터 가져오기"""
        df = pyupbit.get_ohlcv(self.ticker, count=600, period=1)
        return df
    
    def get_orderbook_pressure(self):
        """호가창 매수/매도 압력 분석"""
        orderbook = pyupbit.get_orderbook(ticker=[self.ticker])
        
        # 매수/매도 호가 총량 계산
        bid_volume = sum([item['bid_size'] for item in orderbook['orderbook_units']])
        ask_volume = sum([item['ask_size'] for item in orderbook['orderbook_units']])
        
        # 매수 압력 비율 (0.5 이상이면 매수세 우위)
        buy_pressure = bid_volume / (bid_volume + ask_volume) if (bid_volume + ask_volume) > 0 else 0.5
        
        return {
            'bid_volume': bid_volume,
            'ask_volume': ask_volume,
            'buy_pressure': buy_pressure,
            'orderbook': orderbook
        }
    
    def calculate_indicators(self, df):
        """기술적 지표 계산"""
        # 이동평균선 (5, 20)
        df['ma5'] = df['close'].rolling(window=5).mean()
        df['ma20'] = df['close'].rolling(window=20).mean()
        
        # RSI (14)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 볼린저 밴드 (20, 2)
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        
        # 거래량 이동평균
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        
        # 거래량 급증 여부 (평균 대비 1.5배 이상)
        df['volume_surge'] = df['volume'] > (df['volume_ma'] * 1.5)
        
        return df
    
    def detect_entry_signal(self):
        """진입 시점 탐지"""
        # 데이터 가져오기
        df = self.get_market_data()
        df = self.calculate_indicators(df)
        
        # 호가창 분석
        orderbook_data = self.get_orderbook_pressure()
        
        # 최근 데이터
        current = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 신호 초기화
        signal = {
            'timestamp': datetime.now(),
            'price': current['close'],
            'action': 'HOLD',
            'strength': 0,
            'reasons': []
        }
        
        score = 0
        
        # 1. 이동평균선 골든크로스 (단기 > 장기)
        if current['ma5'] > current['ma20'] and prev['ma5'] <= prev['ma20']:
            score += 3
            signal['reasons'].append('MA 골든크로스')
        elif current['ma5'] > current['ma20']:
            score += 1
            signal['reasons'].append('MA 상승 정렬')
        
        # 2. RSI 과매도 반등
        if 30 < current['rsi'] < 40 and current['rsi'] > prev['rsi']:
            score += 2
            signal['reasons'].append('RSI 과매도 반등')
        elif 40 < current['rsi'] < 60:
            score += 1
            signal['reasons'].append('RSI 중립')
        
        # 3. 볼린저 밴드 하단 터치 후 반등
        if prev['close'] <= prev['bb_lower'] and current['close'] > current['bb_lower']:
            score += 2
            signal['reasons'].append('볼린저 하단 반등')
        
        # 4. 거래량 급증
        if current['volume_surge']:
            score += 2
            signal['reasons'].append('거래량 급증')
        
        # 5. 호가창 매수 압력
        if orderbook_data['buy_pressure'] > 0.55:
            score += 2
            signal['reasons'].append(f"매수 압력 강함 ({orderbook_data['buy_pressure']:.2%})")
        elif orderbook_data['buy_pressure'] > 0.52:
            score += 1
            signal['reasons'].append(f"매수 압력 우위 ({orderbook_data['buy_pressure']:.2%})")
        
        # 6. 가격 상승 모멘텀
        if current['close'] > prev['close'] and prev['close'] > df.iloc[-3]['close']:
            score += 2
            signal['reasons'].append('연속 상승')
        
        # 진입 신호 판단
        if score >= 7:
            signal['action'] = 'STRONG_BUY'
            signal['strength'] = score
        elif score >= 5:
            signal['action'] = 'BUY'
            signal['strength'] = score
        elif score <= -5:
            signal['action'] = 'SELL'
            signal['strength'] = score
        
        # 추가 정보
        signal['indicators'] = {
            'ma5': current['ma5'],
            'ma20': current['ma20'],
            'rsi': current['rsi'],
            'bb_position': (current['close'] - current['bb_lower']) / (current['bb_upper'] - current['bb_lower']),
            'volume_ratio': current['volume'] / current['volume_ma'] if current['volume_ma'] > 0 else 0,
            'buy_pressure': orderbook_data['buy_pressure']
        }
        
        return signal
    
    def print_signal(self, signal):
        """신호 출력"""
        print(f"\n{'='*60}")
        print(f"[{signal['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}] {self.ticker}")
        print(f"{'='*60}")
        print(f"현재가: {signal['price']:,.0f}원")
        print(f"\n🎯 신호: {signal['action']} (강도: {signal['strength']})")
        print(f"\n📊 근거:")
        for i, reason in enumerate(signal['reasons'], 1):
            print(f"  {i}. {reason}")
        
        print(f"\n📈 지표 상태:")
        ind = signal['indicators']
        print(f"  - MA5: {ind['ma5']:,.0f} | MA20: {ind['ma20']:,.0f}")
        print(f"  - RSI: {ind['rsi']:.1f}")
        print(f"  - 볼린저 위치: {ind['bb_position']:.1%}")
        print(f"  - 거래량 비율: {ind['volume_ratio']:.2f}x")
        print(f"  - 매수 압력: {ind['buy_pressure']:.1%}")
        print(f"{'='*60}\n")

# 실행 예제
if __name__ == "__main__":
    # 스캘핑 신호 생성기
    
    # scalper = ScalpingSignal("KRW-BTC")
    scalper = ScalpingSignal("KRW-AERGO")
    
    print("🔍 1분봉 스캘핑 진입 시점 분석 시작...\n")
    
    # 신호 감지
    signal = scalper.detect_entry_signal()
    
    # 결과 출력
    scalper.print_signal(signal)
    
    # 실시간 모니터링 (선택사항)
    import time
    while True:
        signal = scalper.detect_entry_signal()
        scalper.print_signal(signal)
        time.sleep(60)  # 1분마다 체크