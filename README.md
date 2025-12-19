# Coin Strategy Orchestrator

**Coin Strategy Orchestrator**는 Upbit 거래소를 기반으로 다양한 매매 전략(Trailing Stop, Scalping 등)을 실행하고 관리하는 자동 매매 시스템입니다. 예산 단위로 전략을 병렬 적용하며, 시스템 중단 시에도 전략 상태가 유지(Persistence)되도록 설계되었습니다.

## 📝 Project Overview

이 프로젝트는 실시간 시세 데이터를 기반으로 사전 정의된 전략에 따라 자동으로 매수/매도 주문을 실행합니다. 가상 매매(Virtual)와 실전 매매(Real) 모드를 모두 지원하여 전략을 안전하게 검증할 수 있습니다.

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

## ⚙️ Installation & Setup

### 1. Prerequisites
*   Python 3.9+
*   Upbit 계정 (실전 매매 시)

### 2. Install Dependencies
필요한 라이브러리를 설치합니다.
```bash
pip install pyupbit python-dotenv paho-mqtt
```
*(참고: 프로젝트 루트에 `requirements.txt`가 있다면 `pip install -r requirements.txt`를 사용하세요.)*

### 3. Configuration
**Upbit API Key** 설정이 필요합니다.
홈 디렉토리의 `.config/upbit.env` 파일 또는 환경 변수로 설정합니다.

`~/.config/upbit.env` 예시:
```env
UPBIT_ACCESS_KEY=your_access_key_here
UPBIT_SECRET_KEY=your_secret_key_here
```

## 🚀 Usage

`app.py`를 실행하여 봇을 시작합니다.

### Virtual Mode (기본값)
가상 자산(1,000만원)으로 모의 투자를 진행합니다.
```bash
python app.py --mode virtual
```

### Real Mode
실제 Upbit 계좌와 연동하여 매매를 진행합니다. **(주의: 실제 자산이 사용됩니다.)**
```bash
python app.py --mode real
```

## 🧪 Testing

프로젝트의 기능 검증을 위한 테스트 스크립트는 `verify/` 디렉토리에 있습니다.
```bash
# 예: Buy Strategy 검증
python verify/verify_buy_strategy.py
```

유닛 테스트는 `tests/` 디렉토리에 위치합니다.
```bash
python -m unittest discover tests
```

## 📄 Documentation
자세한 내용은 `docs/` 폴더를 참고하세요.
*   [Coin Strategy PRD](docs/Coin%20strategy%20PRD.md)
*   [Developer Guide](docs/dev_guide.md)
