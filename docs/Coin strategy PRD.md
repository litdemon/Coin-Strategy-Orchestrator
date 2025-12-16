# PRD – Coin Strategy Orchestrator & Local-Persisted Strategy Engine (Draft)

## 1. Purpose
여러 코인 매매 전략(Trailing Stop, Scalping, Take Profit 등)을 예산 단위로 병렬 적용하고,
프로세스 중단·재시작 상황에서도 전략 상태가 지속(Persistence)되는 자동 매매 기반 시스템을 구축한다.

## 2. System Overview
### 2.1 Orchestrator
- 실시간 시세 스트림 및 OHLC 정보 수신
- 전략 프로세서로 데이터 라우팅
- 전략 상태 감시 및 트레이드 명령 발행
- Local DB와 전략 프로세서 간 동기화
- 예산 기반 전략 관리

### 2.2 Strategy Engine
- 입력: ticker, 예산, 목표 조건, 상태값, 파라미터
- 출력: buy/sell, trailing update 등
- Local DB에 상태 지속 저장
- 독립 실행 구조
- Lifecycle: create → active → paused → closed → archived

### 2.3 Account Manager
- 가상/실계좌 지원
- 주문 실행, 체결 반영, 잔고/포지션 관리
- Execution Layer 역할

## 3. Key Features
### 3.1 Strategy Persistence
- 전략 ID, 타입, 파라미터, 상태, 예산, 포지션 등 SQLite/DuckDB 저장
- 재시작 시 자동 복원

### 3.2 Strategy Types
- TrailingStop
- Scalping
- TakeProfit
- Grid/Multi-Entry
- Custom Python Strategy

공통 인터페이스:
```
class BaseStrategy:
    def on_price(self, ohlc, trade): ...
    def on_load(self): ...
    def on_persist(self): ...
    def get_orders(self): ...
```

## 4. Architecture
```
Price Feeder → Orchestrator → Strategy Engines → Account Manager ↔ Local DB
```

## 5. Core Requirements
### 5.1 Functional
- 여러 전략 동시 실행
- 전략별 예산 고정
- 전략 상태 DB 저장
- 재시작 자동 복원
- 실계좌/가상계좌 동일 인터페이스
- 전략 충돌 방지
- 매매 로그 기록
- 관리 명령 제공

### 5.2 Non-Functional
- 낮은 지연
- Crash-safe
- 최소 DB write
- 확장성/테스트 가능성

## 6. Data Model
### Strategy Table
```
strategy_id (PK)
type
ticker
budget
state
params_json
position_json
created_at
updated_at
last_price
resume_state_json
```

### History
```
history_id
strategy_id
action
price
volume
timestamp
raw_context_json
```

## 7. Lifecycle
- Start: DB load → Instance 생성 → on_load → Stream 구독
- Price Update: strategy.on_price → 주문 → DB persist
- Stop: safe persist

## 8. Admin Interface
```
/strategy/create
/strategy/{id}/pause
/strategy/{id}/resume
/strategy/{id}/stop
/strategy/list
/account/balance
/account/open_positions
```

## 9. Roadmap
- Multi-market
- Backtesting
- ML 기반 신호
- Risk engine
- A/B testing

## 10. Open Questions
- Local DB 선택?
- Strategy Template 저장 구조?
- Position State 위치?
- Multi-thread vs async?
