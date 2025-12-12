Coin Trading Agent PRD
(Messaging-Pluggable, Strategy-Based, MQTT/Redis/Telegram 명령 실행 시스템)
# 1 목적(Purpose)
제1조(목적) 본 문서는 Coin Trading Agent(이하 “Agent”)가 다양한 메시징 인프라(MQTT, Redis Pub/Sub, Telegram)를 통해 사용자 명령을 수신하고, 실시간으로 암호화폐 거래를 수행하는 시스템의 요구사항을 규정함을 목적으로 한다.

# 2 정의(Definitions)
제2조(정의) 이 문서에서 사용하는 용어의 뜻은 다음과 같다.

**“Agent”**(main.Manager)란 메시지를 기반으로 매수·매도·전략 실행 등을 자동으로 수행하는 프로그램을 말한다.

**“Broker(메시지 브로커)”**란 MQTT, Redis Pub/Sub, Telegram Bot 등 외부 메시지 송수신 시스템을 말한다.

**“Adapter”**란 특정 Broker와의 통신 기능을 캡슐화한 모듈을 말한다.

**“Messaging Interface”**란 모든 Adapter가 준수해야 하는 공통 인터페이스를 말한다.

**“Position”**이란 보유 종목, 수량, 매입가 등을 포함하는 거래 단위를 말한다.

**“Strategy(전략)”**란 Trailing Stop, Take Profit 등 Position에 부착되는 정책 객체를 말한다.

# 3 시스템 개요(System Overview)
제3조(개요) Agent는 Broker로부터 명령을 수신하여 이를 거래소 API에 전달하고, 수행 결과를 다시 Broker로 응답하는 구조로 한다.

User → Broker(MQTT/Redis/Telegram) → Agent → Exchange API
                                      ↑ Response
                                      |
                                   Position/Strategy Engine

# 4 기능 요구사항(Functional Requirements)
제4조(명령 수신 기능)

① Agent는 설정된 Broker에 지속적으로 연결되어 있어야 한다.
② Agent는 다음 Topic을 통해 명령을 수신한다.

예: trading/command/+ (MQTT 기준)

③ 메시지 데이터 형식은 아래 JSON 구조를 표준으로 한다.

{
  "action": "buy",
  "ticker": "KRW-BTC",
  "price": 120000000,
  "volume": 0.001,
  "params": {}
}

# 5 명령 종류

Agent는 다음의 명령을 지원한다.

Buy

Sell

Trailing Stop 설정

Take Profit 설정

Cancel Order

Status Query

# 6 전략 및 포지션 관리

① 각 Position은 단일 책임 원칙(SRP)에 따라 독립 객체로 관리한다.
② 각 전략은 별도 Class로 구현하고 Position에 부착할 수 있어야 한다.
③ 전략 예시는 다음과 같다.

TrailingStopStrategy

TakeProfitStrategy

④ Agent 재시작 시 Position 및 전략 설정은 복구되어야 한다.

# 7 거래소 API 연동

① Account를 통해 거래 실행을 기본으로 한다.
② 모든 주문 요청은 로깅해야 한다.
③ 거래 실패 시 Backoff-Retry를 수행해야 한다.

# 8 응답 제공

① Agent는 명령 처리 결과를 Broker를 통해 사용자에게 회신한다.
예:

{
  "status": "success",
  "action": "buy",
  "order_id": "abc123"
}

# 9 메시징 인프라 추상화(Pluggable Broker Architecture)

## 1.MQTT 외에도 Redis Pub/Sub 또는 Telegram으로 쉽게 변경할 수 있도록 Messaging Layer를 추상화하여 관리한다.

## 2.Messaging Interface 정의

모든 Adapter는 다음 인터페이스를 구현해야 한다.

class MessagingClient:
    def connect(self): ...
    def subscribe(self, topic: str): ...
    def publish(self, topic: str, message: dict): ...
    def set_message_handler(self, callback): ...
    def disconnect(self): ...

## 3.Adapter 구현 규칙

① 각 Adapter는 외부 메시징 시스템의 로직을 내부에 완전히 캡슐화해야 한다.
② Agent는 Adapter의 내부 구조를 알지 않아야 한다(DI 적용).
③ Broker 선택은 config 또는 ENV로 지정한다.

예:

{
  "broker_type": "mqtt",
  "mqtt": { "host": "127.0.0.1" },
  "redis": { "host": "127.0.0.1" },
  "telegram": { "bot_token": "xxxx" }
}

## 4.MQTT Adapter

① paho-mqtt 기반으로 구현한다.
② subscribe/publish는 MQTT topic을 그대로 사용한다.

## 5.Redis Adapter

① Redis Pub/Sub을 사용한다.
② Topic 매핑 예시는 다음과 같다:

trading:command

trading:response:{client_id}

## 6.Telegram Adapter

① Telegram Bot API 기반으로 한다.
② 사용자가 입력한 텍스트를 JSON 명령으로 변환하는 파서를 포함해야 한다.
예:

/buy KRW-BTC 0.001


→

{ "action": "buy", "ticker": "KRW-BTC", "volume": 0.001 }

## 7 비기능 요구사항(Non-functional Requirements)

## 15 성능

명령 수신 후 1초 이내 거래 요청을 수행해야 한다.

## 16 안정성

① Broker 연결 끊김 시 자동 재연결한다.
② 거래 실패 시 Retry를 적용한다.
③ 시스템 재부팅 시 상태는 100% 복구되어야 한다.

## 17 확장성

전략 및 메시징 모듈을 추가하더라도 Agent 핵심 로직 변경은 최소화해야 한다.

## 18 성공 기준

Broker 교체 시 코드 수정이 0줄이어야 한다(설정 파일 변경만으로 전환).

명령 처리 성공률 99% 이상.

메시징 연결 안정성 99.9% 이상.

Agent 재시작 후 Position & 전략 100% 복원.