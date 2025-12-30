from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CommandExecutionContext:
    """명령 실행에 필요한 핵심 객체 컨테이너.

    Manager 가 보유하던 하위 컴포넌트들을 MCP Tool 에 주입하기 위한 목적이다.
    """

    account_manager: Any
    pocket_manager: Any
    strategy_manager: Any
    messaging: Any
    dashboard: Any
    current_prices: Any
    upbit_websocket: Any
    virtual: bool = False


_COMMAND_CONTEXT: Optional[CommandExecutionContext] = None


def set_execution_context(context: CommandExecutionContext) -> None:
    """글로벌 컨텍스트를 설정한다."""

    global _COMMAND_CONTEXT
    _COMMAND_CONTEXT = context


def get_execution_context() -> CommandExecutionContext:
    """설정된 컨텍스트를 반환한다."""

    if _COMMAND_CONTEXT is None:
        raise RuntimeError("CommandExecutionContext is not configured")
    return _COMMAND_CONTEXT
