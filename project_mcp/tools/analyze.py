from typing import Any
from project_mcp.base import Tool
from tools.ticker import Ticker
from strategy.analysis_helper import (
    get_market_data,
    get_orderbook_pressure,
    calculate_indicators,
    analyze_signal,
    calculate_anomaly_zscore,
)

_VALID_INTERVALS = {"minute1", "minute3", "minute5", "minute10", "minute15", "minute30", "minute60", "day", "week", "month"}

_SUMMARIES = {
    "BUY": "매수 신호가 감지되었습니다. 기술적 지표가 상승 가능성을 시사합니다.",
    "SELL": "매도 신호가 감지되었습니다. 기술적 지표가 하락 압력을 시사합니다.",
    "HOLD": "현재 뚜렷한 방향성이 없습니다. 추가 확인 후 진입을 권장합니다.",
}


class AnalyzeTool(Tool):
    """시장 동향 분석 도구 - 기술적 지표 기반 매수/매도/홀드 추천."""

    def identifier(self) -> str:
        return "analyze"

    def execute(self, ticker: str, interval: str = "minute1", count: int = 200) -> Any:
        """
        특정 티커의 시장 동향을 분석하여 매수/매도/홀드 추천을 반환합니다.

        Args:
            ticker: 분석할 티커 (예: "KRW-BTC" 또는 "BTC")
            interval: 캔들 주기 (minute1, minute5, minute60, day 등)
            count: 분석에 사용할 캔들 개수 (최대 200)
        """
        if not ticker:
            return {"error": "'ticker' is required (e.g. 'KRW-BTC' or 'BTC')"}
        if interval not in _VALID_INTERVALS:
            return {"error": f"Invalid interval '{interval}'. Valid: {sorted(_VALID_INTERVALS)}"}
        if not (10 <= count <= 500):
            return {"error": "'count' must be between 10 and 500"}

        market = Ticker(ticker).market

        df = get_market_data(market, interval=interval, count=count)
        if df.empty:
            return {"error": f"Failed to retrieve market data for {market}"}

        df = calculate_indicators(df)
        orderbook = get_orderbook_pressure(market)
        result = analyze_signal(df, orderbook)

        anomaly = calculate_anomaly_zscore(market, interval=interval)

        summary = _SUMMARIES[result["recommendation"]]
        if not anomaly.get("error"):
            if anomaly["is_anomaly"] and anomaly["direction"] == "DIP":
                summary += " 급락 이상치 감지 — 단기 반등 매수 타이밍 가능."
            elif anomaly["is_anomaly"] and anomaly["direction"] == "MOMENTUM":
                summary += " 급등 이상치 감지 — 추격 매수 주의."

        return {
            "ticker": market,
            "interval": interval,
            "current_price": result["current_price"],
            "recommendation": result["recommendation"],
            "score": result["score"],
            "indicators": result["indicators"],
            "reasons": result["reasons"],
            "anomaly": anomaly,
            "summary": summary,
        }
