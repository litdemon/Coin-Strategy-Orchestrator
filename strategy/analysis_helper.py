import logging
import traceback
from typing import Dict, Any

import numpy as np
import pandas as pd
import pyupbit

logger = logging.getLogger(__name__)

MA_SHORT = 5
MA_LONG = 20
RSI_PERIOD = 14
RSI_OVERSOLD = 40
BB_PERIOD = 20
BB_STD = 2
VOLUME_SURGE_MULTIPLIER = 2.0
MIN_BUY_PRESSURE = 0.52
MIN_SIGNAL_SCORE = 5
STRONG_SIGNAL_SCORE = 7


def get_market_data(market: str, interval: str = "minute1", count: int = 200) -> pd.DataFrame:
    try:
        df = pyupbit.get_ohlcv(market, interval=interval, count=count)
        if df is None or df.empty:
            logger.warning(f"No market data for {market}")
            return pd.DataFrame()
        return df
    except Exception as e:
        logger.error(f"Error getting market data: {e}")
        return pd.DataFrame()


def get_orderbook_pressure(market: str) -> Dict[str, Any]:
    try:
        orderbook = pyupbit.get_orderbook(ticker=market)
        if not orderbook or len(orderbook) == 0:
            return {"buy_pressure": 0.5, "bid_volume": 0, "ask_volume": 0}
        units = orderbook["orderbook_units"]
        bid_volume = sum(u["bid_size"] for u in units)
        ask_volume = sum(u["ask_size"] for u in units)
        total = bid_volume + ask_volume
        buy_pressure = bid_volume / total if total > 0 else 0.5
        return {"bid_volume": bid_volume, "ask_volume": ask_volume, "buy_pressure": buy_pressure}
    except Exception as e:
        logger.error(f"Error getting orderbook: {e}\n{traceback.format_exc()}")
        return {"buy_pressure": 0.5, "bid_volume": 0, "ask_volume": 0}


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["ma_short"] = df["close"].rolling(MA_SHORT).mean()
    df["ma_long"] = df["close"].rolling(MA_LONG).mean()
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(RSI_PERIOD).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(RSI_PERIOD).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))
    df["bb_middle"] = df["close"].rolling(BB_PERIOD).mean()
    bb_std = df["close"].rolling(BB_PERIOD).std()
    df["bb_upper"] = df["bb_middle"] + bb_std * BB_STD
    df["bb_lower"] = df["bb_middle"] - bb_std * BB_STD
    df["volume_ma"] = df["volume"].rolling(20).mean()
    df["volume_surge"] = df["volume"] > df["volume_ma"] * VOLUME_SURGE_MULTIPLIER
    return df


def calculate_anomaly_zscore(
    market: str,
    period: int = 60,
    z_score_threshold: float = 3.0,
    interval: str = "minute1",
) -> Dict[str, Any]:
    try:
        df = pyupbit.get_ohlcv(market, interval=interval, count=period + 10)
        if df is None or df.empty:
            return {"error": f"No data for {market}"}

        df = df.copy()
        df["close"] = df["close"].astype(float)
        df["log_return"] = np.log(df["close"] / df["close"].shift(1))
        df = df.dropna()

        if len(df) < period + 1:
            return {"error": "Not enough data"}

        history = df.iloc[-1 - period : -1]
        current_return = float(df.iloc[-1]["log_return"])
        mean = float(history["log_return"].mean())
        std = float(history["log_return"].std())

        if std == 0:
            return {"z_score": 0.0, "is_anomaly": False, "direction": None,
                    "current_return": current_return, "mean": mean, "std": std, "threshold": z_score_threshold}

        z_score = (current_return - mean) / std
        is_anomaly = abs(z_score) > z_score_threshold
        direction = None
        if z_score < -z_score_threshold:
            direction = "DIP"
        elif z_score > z_score_threshold:
            direction = "MOMENTUM"

        return {
            "z_score": round(z_score, 4),
            "is_anomaly": is_anomaly,
            "direction": direction,
            "current_return": round(current_return, 6),
            "mean": round(mean, 6),
            "std": round(std, 6),
            "threshold": z_score_threshold,
        }
    except Exception as e:
        logger.error(f"Error in calculate_anomaly_zscore: {e}")
        return {"error": str(e)}


def analyze_signal(df: pd.DataFrame, orderbook_data: Dict[str, Any]) -> Dict[str, Any]:
    if len(df) < 3:
        return {"score": 0, "reasons": [], "recommendation": "HOLD"}

    cur = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]

    score = 0
    reasons = []

    # MA
    if pd.notna(cur["ma_short"]) and pd.notna(cur["ma_long"]):
        if cur["ma_short"] > cur["ma_long"] and prev["ma_short"] <= prev["ma_long"]:
            score += 3
            reasons.append("MA 골든크로스")
            ma_trend = "GOLDEN_CROSS"
        elif cur["ma_short"] > cur["ma_long"]:
            score += 1
            reasons.append("MA 상승 정렬")
            ma_trend = "ABOVE"
        else:
            ma_trend = "BELOW"
    else:
        ma_trend = "UNKNOWN"

    # RSI
    rsi_val = float(cur["rsi"]) if pd.notna(cur["rsi"]) else None
    if rsi_val is not None:
        if 30 < rsi_val < RSI_OVERSOLD and rsi_val > prev["rsi"]:
            score += 2
            reasons.append(f"RSI 과매도 반등 ({rsi_val:.1f})")
        elif 40 < rsi_val < 60:
            score += 1
            reasons.append("RSI 중립")

    # Bollinger Band
    bb_position = "MIDDLE"
    if pd.notna(cur["bb_lower"]) and pd.notna(prev["bb_lower"]):
        if prev["close"] <= prev["bb_lower"] and cur["close"] > cur["bb_lower"]:
            score += 2
            reasons.append("볼린저 하단 반등")
            bb_position = "LOWER_BOUNCE"
        elif cur["close"] >= cur["bb_upper"]:
            bb_position = "UPPER"
        elif cur["close"] <= cur["bb_lower"]:
            bb_position = "LOWER"

    # Volume surge
    volume_surge = bool(cur["volume_surge"])
    if volume_surge:
        score += 2
        reasons.append("거래량 급증")

    # Orderbook pressure
    buy_pressure = orderbook_data.get("buy_pressure", 0.5)
    if buy_pressure > 0.55:
        score += 2
        reasons.append(f"매수 압력 강함 ({buy_pressure:.1%})")
    elif buy_pressure > MIN_BUY_PRESSURE:
        score += 1
        reasons.append(f"매수 압력 우위 ({buy_pressure:.1%})")

    # Price momentum
    if cur["close"] > prev["close"] > prev2["close"]:
        score += 2
        reasons.append("연속 상승")
    elif cur["close"] < prev["close"] < prev2["close"]:
        score -= 2
        reasons.append("연속 하락")

    if score >= STRONG_SIGNAL_SCORE:
        recommendation = "BUY"
    elif score >= MIN_SIGNAL_SCORE:
        recommendation = "BUY"
    elif score <= 0:
        recommendation = "SELL"
    else:
        recommendation = "HOLD"

    return {
        "score": score,
        "recommendation": recommendation,
        "reasons": reasons,
        "indicators": {
            "rsi": round(rsi_val, 2) if rsi_val is not None else None,
            "ma_short": float(cur["ma_short"]) if pd.notna(cur["ma_short"]) else None,
            "ma_long": float(cur["ma_long"]) if pd.notna(cur["ma_long"]) else None,
            "ma_trend": ma_trend,
            "bb_position": bb_position,
            "volume_surge": volume_surge,
            "buy_pressure": round(buy_pressure, 4),
        },
        "current_price": float(cur["close"]),
    }
