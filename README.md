# Coin Strategy Orchestrator

Upbit 거래소 기반 자동화 트레이딩 시스템. 가상 계좌로 전략을 테스트하거나 실계좌에 연동하여 운용합니다.
AI Agent(Claude Desktop 등)를 MCP로 연결하면 자연어 명령으로 전략 생성·매수·매도를 제어할 수 있습니다.

> ⚠️ 본 소프트웨어는 투자 자문이나 수익을 보장하지 않습니다. 모든 거래 판단과 책임은 사용자에게 있습니다.

---

## 시스템 요구사항

| 항목 | 최소 요건 |
|------|-----------|
| Python | **3.11 이상** (3.10 이하 미지원) |
| MQTT 브로커 | 필수 — `mosquitto` 등 로컬 또는 원격 브로커 |
| 운영체제 | macOS / Linux (Windows 미검증) |

### 의존성 패키지

```
pyupbit, python-dotenv, pandas, numpy, pydantic
mcp, fastapi, uvicorn, websockets
```

---

## 빠른 시작

### 1. 가상환경 생성 및 패키지 설치

```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. API 키 설정 (가상 모드는 선택)

```bash
mkdir -p ~/.config
cat > ~/.config/upbit.env <<EOF
UPBIT_ACCESS_KEY=your_access_key
UPBIT_SECRET_KEY=your_secret_key
EOF
```

가상 계좌로만 테스트할 경우 이 단계를 건너뛸 수 있습니다.

### 3. 설정 파일 확인 (`default.json`)

```json
{
  "messaging": {
    "broker_type": "mqtt",
    "mqtt": { "host": "mqtt.example.com", "port": 1883, "client_id": "" }
  },
  "account": {
    "initial_balance": 10000000,
    "fees": { "KRW": 0.0005 }
  },
  "dashboard": {
    "host": "127.0.0.1",
    "port": 8765,
    "token": "",
    "mode": "web"
  },
  "mcp": {
    "host": "127.0.0.1",
    "port": 8000
  }
}
```

| 항목 | 설명 |
|------|------|
| `messaging.broker_type` | `"mqtt"` \| `"redis"` \| `"socket"` — 외부 명령 채널 |
| `messaging.mqtt.host` | MQTT 브로커 주소 (MQTT 모드 필수) |
| `account.initial_balance` | 가상 계좌 초기 잔고 (KRW) |
| `account.fees.KRW` | 거래 수수료율 (0.05% = `0.0005`) |
| `dashboard.port` | Web UI 포트 |
| `dashboard.token` | 대시보드 접근 토큰 (빈 문자열이면 인증 없음) |
| `dashboard.mode` | `"web"` (기본) \| `"tui"` \| `"both"` \| `"off"` |
| `mcp.port` | AI Agent MCP 서버 포트 |

### 4. 실행

```bash
python app.py
```

시작 시 콘솔 출력:

```
  Dashboard  → http://127.0.0.1:8765
  MCP Server → http://127.0.0.1:8000/mcp
```

---

## Web 대시보드

브라우저에서 `http://127.0.0.1:8765` 접속.

| 섹션 | 내용 |
|------|------|
| Assets | 보유 코인별 잔고·평균 매수가·현재가·손익률 |
| Pockets | 활성 포지션 목록 (진입가·수량·상태) |
| Strategies | 실행 중인 전략 목록 |
| Pending Orders | 미체결 주문 |
| Recent Logs | 실시간 시스템 로그 |
| AI Agent 연결 가이드 | MCP 설정 안내 (접기/펼치기) |

> 토큰이 설정된 경우 `http://127.0.0.1:8765?token=<토큰값>` 으로 접속합니다.

---

## AI Agent 연동 (MCP)

앱이 실행되면 MCP 서버가 `http://127.0.0.1:8000/mcp` 에서 대기합니다.
대시보드 하단 **AI Agent 연결 가이드** 패널에서 설정 JSON을 복사할 수 있습니다.

**Claude Desktop 설정 예시** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "coin-strategy": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

사용 가능한 MCP 도구:

| 도구 | 설명 | 주요 파라미터 |
|------|------|--------------|
| `buy` | 시장가·지정가 매수 | `ticker`, `won`(KRW금액) 또는 `volume`+`price` |
| `sell` | 시장가·지정가 매도 | `ticker`, `volume`(`-1`=전량) |
| `account` | 잔고 조회 | — |
| `status` | 서버 상태 조회 | — |
| `pockets` | 활성 포켓 목록 | — |
| `orders` | 미체결 주문 목록 | — |
| `cancel` | 주문 취소 | `ticker` 또는 `order_uuid` |
| `price` | 현재가 조회 | `ticker` |
| `manage_strategy` | 전략 생성·삭제·조회 | `action`, `name`, `ticker`, `budget` |

자연어 명령 예시:
- "BTC 10만원어치 시장가로 사줘"
- "현재 잔고 알려줘"
- "KRW-BTC에 scalping_strategy 전략을 50만원 예산으로 실행해줘"
- "활성 포켓 목록 보여줘"

---

## 전략 목록

| 전략명 | 클래스 | 설명 |
|--------|--------|------|
| `scalping_strategy` | `ScalpingStrategy` | 단기 가격 상승 신호 매수 |
| `volume_spike_strategy` | `VolumeSpikeStrategy` | 거래량 급등 감지 (60초 주기) |
| `anomaly_detection` | `AnomalyStrategy` | 통계적 이상치 감지 |
| `dl_anomaly_detection` | `DeepAnomalyStrategy` | 딥러닝 이상치 감지 |
| `trailing_stop` | `TrailingStopStrategy` | 트레일링 스탑 (포켓 연결) |
| `default` | `DefaultStrategy` | 매수 완료 후 자동 할당되는 기본 전략 |

---

## 테스트

```bash
# 전체 유닛 테스트 (53개)
python -m unittest discover tests

# 시나리오 검증 (ad-hoc, CI 미포함)
python verify/verify_all_feature.py
python verify/verify_buy_strategy.py
```

---

## 로그

일별 로테이션: `logs/coin-stratege.log` (30일 보관)

---

## MQTT 없이 실행 (제한적 동작)

현재 버전은 **MQTT 브로커가 필수**입니다. 브로커 없이 시작하면 메시징 초기화 오류가 발생합니다.
로컬 테스트용 MQTT 브로커 설치:

```bash
# macOS
brew install mosquitto && brew services start mosquitto

# Ubuntu/Debian
sudo apt install mosquitto && sudo systemctl start mosquitto
```

`default.json`의 `messaging.mqtt.host`를 `"127.0.0.1"`로 설정하면 로컬 브로커에 연결됩니다.
