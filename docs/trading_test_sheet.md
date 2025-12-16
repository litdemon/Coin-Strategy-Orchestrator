# 거래 시스템 테스트 시트: 매수 / 매도 / 취소

**날짜:** 2025-12-13  
**대상 시스템:** `Coin Strategy` (에이전트 + 가상 계좌)  
**검증 도구:** `maru` CLI 및 `verify_db_account_flow.py`

---

## 1. 매수 주문 테스트 (Buy Order)

| ID | 테스트 케이스 | 단계 (Steps) | 예상 결과 (Expected Result) | 검증됨? |
| :--- | :--- | :--- | :--- | :--- |
| **B-01** | **지정가 매수 (CLI)** | 1. `maru buy KRW-BTC 50000 1000000` 실행<br>2. 대시보드/로그 확인<br />3. DB orders table 확인<br /> | - 주문 상태 `wait`로 생성됨.<br>- 가격: 50,000 KRW<br>- 수량: 100만 원 기준 계산됨<br>- KRW 잠금(Locked) 증가.<br /> | ✅ |
| **B-02** | **시장가 매수 (CLI)** | 1. `maru buy KRW-BTC -1 1000000 -p` 실행<br>*(시장가 지원 시)* | - 주문 타입 `market`으로 생성됨.<br>- 즉시 체결(실전) 또는 시뮬레이션 체결.<br>- 포지션 생성됨. | ✅ |
| **B-03** | **매수 체결 (가상)**| 1. 지정가 매수 주문 생성.<br>2. 시장가 하락 < 지정가 시뮬레이션. | - 주문 상태 변경: `wait` -> `done`.<br>- **포지션 생성됨** (`PositionManager`).<br>- KRW 잔고 감소, BTC 잔고 증가. | ✅ |
| **B-04** | **잔고 부족** | 1. KRW 잔고보다 큰 금액으로 매수 시도. | - 주문 거부됨.<br>- 대시보드에 에러 로그 출력. | ✅ |
| **B-05** | **매수 금액 오버 체크** | 1. `maru buy KRW-BTC <price> <amount>` 실행 (amount > available_krw)<br>2. 예상 수수료 포함 체크. | - "Insufficient Balance" 에러 발생.<br>- 주문 생성 실패.<br>- 잔고 변동 없음. | ✅ |

## 2. 매도 주문 테스트 (Sell Order)

| ID | 테스트 케이스 | 단계 (Steps) | 예상 결과 (Expected Result) | 검증됨? |
| :--- | :--- | :--- | :--- | :--- |
| **S-01** | **지정가 매도 (CLI)** | 1. `maru sell KRW-BTC 60000 0.5` 실행<br>2. 대시보드 확인 | - 주문 상태 `wait`로 생성됨.<br>- 가격: 60,000 KRW<br>- 수량: 0.5 BTC<br>- BTC 잠금(Locked) 증가. | ✅ |
| **S-02** | **매도 체결 (가상)**| 1. 지정가 매도 주문 생성.<br>2. 시장가 상승 > 지정가 시뮬레이션. | - 주문 상태 변경: `wait` -> `done`.<br>- **포지션 종료** (부분/전체) (`PositionManager`).<br>- BTC 잔고 감소, KRW 잔고 증가. | ✅ |
| **S-03** | **전량 매도 (시장가)** | 1. `maru sell KRW-BTC -1 -1` 실행 (로직 의존) | - 보유 수량 전량을 시장가로 매도.<br>- 포지션 완전 종료. | ✅ |
| **S-04** | **보유 수량 초과 매도** | 1. 보유 수량보다 많은 양 매도 시도.<br>2. `maru sell KRW-BTC <price> <excess_vol>` | - "Insufficient Asset" 에러 발생.<br>- 주문 생성 실패.<br>- 잔고 변동 없음. | ✅ |

## 3. 취소 주문 테스트 (Cancel Order)

| ID | 테스트 케이스 | 단계 (Steps) | 예상 결과 (Expected Result) | 검증됨? |
| :--- | :--- | :--- | :--- | :--- |
| **C-01** | **활성 주문 취소** | 1. 매수/매도 지정가 주문 생성 (상태 `wait` 확인).<br>2. 로그에서 UUID 확인 (`maru status` 대기열).<br>3. `maru cancel <UUID>` 실행. | - MQTT로 명령 전송됨.<br>- 주문 상태 `cancel`로 변경.<br>- 잠긴 자산(KRW/BTC)이 잔고로 반환됨.<br>- 대시보드에 "Order Cancelled" 로그 출력. | ✅ |
| **C-02** | **잘못된 UUID 취소** | 1. `maru cancel invalid-uuid` 실행. | - 시스템이 "Order Not Found" 로그 출력.<br>- 상태 변경 없음. | ✅ |
| **C-03** | **이미 체결된 주문 취소**| 1. `done` 상태인 주문 취소 시도. | - 실패 / "Not Active Order" 메시지. | ✅ |

## 4. CLI 명령어 참고

| 명령어 | 사용 예시 | 설명 |
| :--- | :--- | :--- |
| **Buy** | `maru buy KRW-BTC <가격> <KRW금액>` | 지정가 매수 주문을 생성합니다. |
| **Sell** | `maru sell KRW-BTC <가격> <수량>` | 지정가 매도 주문을 생성합니다. |
| **Cancel**| `maru cancel <UUID>` | 특정 UUID의 주문을 취소합니다. |
| **Status**| `maru status` | 현재 잔고와 활성 포지션을 보여줍니다. |

---

**참고:** 가상 계좌 로직(`DBUpbit`)이 수정되어 `myOrder` 이벤트가 모든 상태 변경(`wait`, `done`, `cancel`)에 대해 정상적으로 발생하며, 이를 통해 대시보드와 포지션 로직이 올바르게 업데이트됨을 확인했습니다.
