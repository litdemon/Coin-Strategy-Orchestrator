# Strategy Manager PRD

## 1. 개요 (Overview)
`StrategyManager`는 트레이딩 시스템 내에서 개별 전략(Strategy)들의 생명주기(생성, 실행, 종료, 아카이빙)를 관리하고, 외부 데이터(Ticker, Orderbook) 및 시간 이벤트(Schedule)에 따라 전략을 구동하는 핵심 모듈입니다.

## 2. 주요 요구사항 (Key Requirements)

### 2.1 Identity & Management
- **UUID 기반 관리**: 모든 전략 인스턴스는 고유한 UUID (`strategy_id`)를 가지며, 이를 통해 식별 및 관리됩니다.
- **상태 관리**: 전략은 `active` (활성), `stopped` (중지), `archived` (보관) 등의 상태를 가지며 DB에 영구 저장됩니다.

### 2.2 Relationships
- **Ticker (Coin) 연관성**:
  - 모든 전략은 특정 Ticker (e.g., `KRW-BTC`)와 연관됩니다.
  - 해당 Ticker의 실시간 가격(Trade) 또는 호가(Orderbook) 변동 시 관련 전략들이 트리거됩니다.
- **Position (Debt) 연관성 (Optional)**:
  - 전략은 특정 `position_id`와 연결될 수 있습니다. (주로 청산/손절/익절 전략)
  - `position_id`가 없는 전략은 진입(Buy) 전략이나 글로벌 모니터링 전략으로 간주됩니다.

### 2.3 Monitoring & Execution
- **Signal Check**:
  - `on_tick(ticker, current_price)`: 실시간 체결가 수신 시 호출.
  - `on_orderbook(ticker, orderbook)`: 호가 변경 시 호출.
  - 전략 내부 로직에 따라 `Signal` (BUY, SELL, CLOSE 등)을 생성하면 Manager가 이를 실행합니다.
- **Schedule Based Testing**:
  - Crontab 표현식 등을 활용한 시간 기반 주기적 실행을 지원해야 합니다.
  - 예: "매 1분마다", "매일 오전 9시" 등 주기적인 로직 검사 지원.

## 3. Data Architecture

### 3.1 DTO (StrategyDTO)
```python
class StrategyDTO(BaseModel):
    strategy_id: str          # UUID
    type: str                 # Strategy Class Name (e.g., "TrailingStop")
    ticker: str               # Target Coin (e.g., "KRW-BTC")
    position_id: Optional[str]# Linked Position ID (None if entry strategy)
    budget: Decimal           # Assigned Budget (for entry strategies)
    config: Dict[str, Any]    # Strategy-specific configuration
    state: Dict[str, Any]     # Runtime state (serialized)
    status: str               # active, stopped, archived
    created_at: float
    updated_at: float
    # schedule: Optional[str] # Crontab expression (Proposed)
```

### 3.2 Interfaces

#### IStrategyManager
- `create_strategy(type, ticker, config, position_id=None)`: 전략 생성
- `stop_strategy(strategy_id)`: 전략 중지
- `archive_strategy(strategy_id)`: 전략 보관 (DB 이동/삭제)
- `on_tick(ticker, price)`: 가격 변동 이벤트 핸들러
- `on_orderbook(ticker, orderbook)`: 호가 변동 이벤트 핸들러
- `on_schedule(timestamp)`: 스케줄러에 의한 주기적 호출

## 4. Implementation Details (Proposed)

### 4.1 Scheduling Mechanism
- Python `schedule` 라이브러리 또는 `APScheduler` 도입 고려, 혹은 단순 Loop 내 체크.
- **MVP 단계**: `Manager`의 메인 루프에서 1초 단위 `tick`을 발생시키고, `StrategyManager.on_schedule()` 내부에서 각 전략의 주기(interval)를 체크하여 실행.
- **확장**: 전략 Config에 `execution_interval` (초 단위) 또는 `cron_expression`을 필드로 추가.

### 4.2 Pocket Linkage
- `PocketManager`와 협업 필요.
- 포지션 생성 시 해당 포지션을 관리할 전략(예: TrailingStop)을 함께 생성하여 `pocket_id`를 주입.
- 포지션 종료 시 해당 전략도 `stop` 및 `archive` 처리.

## 5. Sequence Flows
1. **Market Data Event**:
   `UpbitWebSocket` -> `Manager` -> `StrategyManager.on_tick(ticker)` -> `Strategy(inst).on_tick()` -> `Signal` -> `Manager processes Order`
2. **Scheduled Event**:
   `Main Loop` -> `Manager` -> `StrategyManager.on_schedule()` -> `Strategy(inst).check_schedule()` -> `Signal` -> `Manager processes Order`
