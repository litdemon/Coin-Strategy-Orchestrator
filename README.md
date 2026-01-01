* # Coin Strategy Orchestrator

  **Coin Strategy Orchestrator**는 Upbit 거래소를 기반으로 다양한 매매 전략(Trailing Stop, Scalping 등)을 실행하고 관리하는 자동 매매 시스템입니다. 예산 단위로 전략을 병렬 적용하며, 시스템 중단 시에도 전략 상태가 유지(Persistence)되도록 설계되었습니다.

  ## 📝 Project Overview

  Coin Strategy Orchestrator는 Upbit 시세를 기준으로 포켓(Pocket) 단위 자산을 관리하고, 지정된 예산·전략 조합을 지속 운용하도록 설계된 로컬 실행형 트레이딩 시스템입니다. 실시간 Price Feed를 수신해 전략이 요구하는 신호를 계산하고, 체결 내역과 상태를 로컬 DB에 보존하여 중단 이후에도 복구가 가능합니다.

  시스템은 KRW 기반 Spot 자산을 지원하며, Virtual(시뮬레이션) 모드와 Real(Upbit 실계좌) 모드가 동일한 전략 파이프라인을 공유합니다. Price Feed → Pocket Manager → Strategy Engine → Account Manager → Messaging → Dashboard/Data Export 단계로 이어지는 파이프라인을 통해 시세·전략·거래·모니터링이 하나의 루프로 묶입니다. 이를 통해 전략 검증부터 실계좌 운용까지 일관된 경험을 제공합니다.

  ### Key Features
  *   **Strategy Orchestration**: 여러 코인에 대해 다수의 전략을 동시에 병렬 실행
  *   **Strategy Persistence**: 전략 상태(진입가, 목표가, 현재 상태 등)를 로컬 DB에 저장하여 재시작 시 자동 복구
  *   **Dual Mode**:
      *   **Virtual Mode**: 가상 자산으로 전략 테스트 (수수료 및 체결 시뮬레이션 포함)
      *   **Real Mode**: Upbit API를 연동한 실전 매매
  *   **Strategy Types**:
      *   Default Strategy (기본 매매)
      *   Scalping Strategy (스캘핑)
      *   (확장 가능)
  *   **Dashboard**: 실시간 상태 로그 및 자산/전략 현황 모니터링
  *   **Messaging**: MQTT를 통한 외부 명령 수신 및 상태 제어

  ## 🧱 Architecture & Data Flow

  ```mermaid
  flowchart LR
      
      PF -- [Price Feed(Upbit WebSocket)] --> PM[Pocket Manager]
      PM --> SE[Strategy Engine]
      SE --> AM[Account Manager]
      AM --> MSG[Messaging Layer]
      MSG --> DBX[Dashboard / Data Export]
  
      AM <-->|Orders & Balances| UPT[Upbit API / Real Account]
      AM -->|Simulated fills| VIRT[Virtual Ledger]
  ```

  - **Price Feed**: Upbit WebSocket/REST로부터 틱·호가 데이터를 수집해 Pocket/전략에 전달.
  - **Pocket Manager**: 전략별 포지션, 예산, 포켓 라이프사이클을 관리하며 Strategy Engine의 상태 저장소 역할 수행.
  - **Strategy Engine**: 신호 생성, 진입/청산 조건 판별, Account Manager로 주문 의사결정 전달.
  - **Account Manager**: Virtual/Real 인터페이스를 단일 추상화로 제공하며 체결, 수수료, 잔고 업데이트를 담당.
  - **Messaging Layer**: MQTT/Redis 등 외부 명령 채널과 상태 브로드캐스트를 연결.
  - **Dashboard/Data Export**: 운영자에게 실시간 상태를 시각화하고 로그·리포트를 생성.

  ## 📂 Directory Structure

  ```
  /
  ├── app.py                  # 메인 실행 파일
  ├── account/                # 계좌 관리 (Upbit/Virtual)
  ├── docs/                   # 프로젝트 문서 (PRD, 개발 가이드)
  ├── messaging/              # 메시징 시스템 (MQTT 등)
  ├── models/                 # 데이터 모델 (Trade, Order, Pocket 등)
  ├── src/
  │   ├── main.py             # 핵심 로직 (Manager)
  │   ├── dashboard.py        # 대시보드 UI
  │   ├── pocket_manager.py   # 포켓(개별 매매 단위) 관리
  │   └── ...
  ├── strategy/               # 전략 엔진 및 구현체
  ├── tools/                  # 유틸리티 (Ticker, Converter 등)
  ├── upbit/                  # Upbit WebSocket 연동
  └── verify/                 # 검증 및 테스트 스크립트
  ```

  ## 📦 Module Responsibilities

  | Module | Role | Main Entry Points | External Dependencies |
  | --- | --- | --- | --- |
  | `account/` | Upbit/Virtual 계좌 상태, 주문 실행, 체결 반영 | `manager.py`, `repositories.py` | `pyupbit`, Upbit REST/WS |
  | `messaging/` | MQTT/Redis/Socket 어댑터 관리 및 명령 라우팅 | `factory.py`, `adapters/*` | `paho-mqtt`, Redis client |
  | `strategy/` | 전략 추상화 및 구현(Default/Volume) | `manager.py`, `buy_strategy.py` 등 | PyTorch |
  | `src/` | 메인 런타임, 대시보드, 포켓 매니저, 파이프라인 어댑터 | `main.py`, `dashboard.py`, `pocket_manager.py` | `rich`, `websocket-client` 등 |
  | `tools/` | 가격 변환, 티커 헬퍼, 파이프라인 유틸 | `pipeline.py`, `ticker.py` | `pandas`, 기타 유틸 |
  | `verify/` | 시나리오 검증 스크립트(실거래 흐름 리허설) | `verify_all_feature.py` 등 | 테스트 대상 모듈 직접 참조 |
  | `docs/` | PRD·가이드·TODO 등 문서 자산 | `docs/*.md` | 없음 |

  ## ⚙️ Setup & Configuration

  ### a. Python 가상환경 생성
  - `python -m venv .venv && source .venv/bin/activate`
  - Windows PowerShell: `.venv\Scripts\Activate.ps1`

  ### b. Requirements 설치
  - `pip install -r requirements.txt`
  - 개별 패키지 업데이트 시 `pip list --outdated`로 확인 후 `pip install --upgrade <package>`

  ### c. 환경 변수 정의
  필수 ENV는 아래와 같으며 `.env`, OS 환경 변수, CI Secret 등 선호 방식으로 주입합니다.

  | Key | Description |
  | --- | --- |
  | `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY` | Upbit REST 거래 키 (Real 모드 필수) |
  | `MQTT_HOST`, `MQTT_PORT` | Messaging 브로커 연결 정보 |
  | `DASHBOARD_PORT` | 대시보드 웹소켓/HTTP 포트 |
  | `REDIS_URL` | Redis 기반 Messaging/캐시를 사용하는 경우 |

  ### d. 구성 파일 참고
  - `default.json`: 메시징 브로커, 기본 전략 파라미터, 초기 포트 설정 등 런타임 기본값을 제공합니다.
  - `requirements.txt`: 배포 환경 동기화를 위한 의존성 잠금 목록입니다.

  ### e. Real Mode 체크리스트
  - Upbit API 키에 거래 권한이 활성화되어 있는지 확인.
  - 계좌 KRW 잔액 및 최소 주문 단위 확보.
  - `UPBIT_*`, 메시징, 대시보드 관련 ENV가 프로덕션 값으로 세팅되었는지 점검.
  - 실거래 시작 전 `verify/` 시나리오 중 핵심 플로우를 Virtual 모드로 재검증.

  ## 🚀 Running the System

  ### Step-by-step Runbook
  1. **Config 준비**: `default.json` 검토, 필요 시 override 파일/ENV 작성.
  2. **프로세스 실행**: `python app.py --mode <virtual|real>`
  3. **대시보드 접속**: `http://localhost:${DASHBOARD_PORT}` 또는 설정된 원격 주소로 접속해 상태 확인.
  4. **종료 절차**: CLI에서 `Ctrl+C`로 안전 종료 → 로그 확인 → 필요 시 `account/` 저장소 상태 점검.

  ### Virtual vs Real 모드 비교

  | 구분 | Virtual Mode | Real Mode |
  | --- | --- | --- |
  | 데이터 소스 | Upbit 시세 + 시뮬레이션 체결 | Upbit 시세 + 실계좌 체결 |
  | 잔고/체결 | 가상 원장(`models/`)에서 처리 | Upbit REST/WS로 실시간 반영 |
  | 위험도 | 금전적 손실 없음, 전략 디버깅용 | 실자산 사용, 주문 한도·오류에 주의 |
  | 권장 사용 | 신규 전략 개발, 회귀 테스트 | 운영 배포, 실거래 |

  - Real 모드에서는 주문 최소 수량/금액, API Rate Limit, 네트워크 이슈를 별도로 모니터링하세요.

  ## 🧪 Testing & Verification

  - **유닛/통합 테스트 (`tests/`)**
    - 실행: `python -m unittest discover tests`
    - 기대 출력: 각 전략/모듈별 PASS 결과와 실패 시 스택트레이스. 실패 시 최근 코드 변경과 테스트 픽스처(`tests/test_*`)를 교차 확인합니다.
  - **시나리오 검증 (`verify/`)**
    - 실행: `python verify/verify_all_feature.py` 또는 개별 스크립트(예: `verify_buy_strategy.py`).
    - 기대 출력: 단계별 `[VERIFY]` 로그와 주문/포켓 상태 요약. 실패 시 로그 타임라인을 기준으로 메시징·전략·계좌 레이어를 순서대로 점검합니다.

  ## 📄 Documentation & Roadmap

  - `docs/Trading_signal_system.md`: 메시징/에이전트 요구사항과 본 README의 Architecture 섹션을 연결합니다.
  - `docs/Strategy_PRD.md`: Strategy Manager 동작을 상세히 설명하며, README의 Module Responsibilities 표와 1:1 매핑됩니다.
  - `docs/TODO.md`: 단기 개선 과제를 추적하며 README Roadmap과 우선순위를 공유합니다.
  - `docs/dev_guide.md`: 디렉터리/코딩 가이드라인을 제공해 Setup 절차를 보완합니다.

  **향후 우선순위 과제**
  1. Strategy Manager 리팩터링으로 웹소켓·메시징 책임 분리.
  2. Messaging 인증/암호화 도입 및 다중 브로커 지원 강화.
  3. Dashboard 실시간 통계(총 자산, 전략 별 Sharpe 등) 확장.

  ## 📚 Additional References

  자세한 내용은 `docs/` 폴더를 참고하세요.
  *   [Coin Strategy PRD](docs/Coin%20strategy%20PRD.md)
  *   [Developer Guide](docs/dev_guide.md)
  *   [Trading Signal System](docs/Trading_signal_system.md)
  *   [TODO](docs/TODO.md)
