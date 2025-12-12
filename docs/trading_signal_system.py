"""
MQTT 기반 Trading Signal 시스템
"""

import json
import uuid
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, Callable
import paho.mqtt.client as mqtt
import asyncio
from threading import Thread
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============= Signal 정의 =============

class SignalType(Enum):
    BUY = "buy"
    SELL = "sell"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    APPLY_STRATEGY = "apply_strategy"
    PAUSE_STRATEGY = "pause_strategy"
    REBALANCE = "rebalance"
    EMERGENCY_STOP = "emergency_stop"


class Priority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class TradingSignal:
    signal_id: str
    signal_type: SignalType
    priority: Priority
    timestamp: str
    symbol: str
    amount: Optional[float] = None
    price: Optional[float] = None
    percentage: Optional[float] = None
    strategy_name: Optional[str] = None
    strategy_params: Optional[Dict[str, Any]] = None
    conditions: Optional[Dict[str, Any]] = None
    expire_at: Optional[str] = None
    source: str = "manual"
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self):
        data = asdict(self)
        data['signal_type'] = self.signal_type.value
        data['priority'] = self.priority.value
        return data

    @classmethod
    def from_dict(cls, data: dict):
        data['signal_type'] = SignalType(data['signal_type'])
        data['priority'] = Priority(data['priority'])
        return cls(**data)


# ============= MQTT Broker 설정 =============

class MQTTBroker:
    """MQTT 브로커 연결 및 메시지 처리"""
    
    def __init__(self, broker_host="localhost", broker_port=1883, 
                 username=None, password=None, client_id=None):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client_id = client_id or f"trading_client_{uuid.uuid4().hex[:8]}"
        
        self.client = mqtt.Client(client_id=self.client_id)
        
        if username and password:
            self.client.username_pw_set(username, password)
        
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        
        self.message_callbacks: Dict[str, Callable] = {}
        self.is_connected = False
        
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"✅ MQTT Connected: {self.client_id}")
            self.is_connected = True
        else:
            logger.error(f"❌ MQTT Connection failed with code {rc}")
            self.is_connected = False
    
    def _on_disconnect(self, client, userdata, rc):
        logger.warning(f"⚠️  MQTT Disconnected: {self.client_id}")
        self.is_connected = False
    
    def _on_message(self, client, userdata, msg):
        """메시지 수신 시 등록된 콜백 실행"""
        topic = msg.topic
        payload = msg.payload.decode()
        
        logger.info(f"📨 Received message on {topic}")
        
        # 토픽 패턴 매칭
        for pattern, callback in self.message_callbacks.items():
            if self._topic_matches(topic, pattern):
                try:
                    callback(topic, payload)
                except Exception as e:
                    logger.error(f"❌ Callback error: {e}")
    
    def _topic_matches(self, topic: str, pattern: str) -> bool:
        """MQTT 토픽 패턴 매칭 (+는 단일 레벨, #는 다중 레벨)"""
        topic_parts = topic.split('/')
        pattern_parts = pattern.split('/')
        
        if len(pattern_parts) > len(topic_parts):
            return False
        
        for i, pattern_part in enumerate(pattern_parts):
            if pattern_part == '#':
                return True
            if i >= len(topic_parts):
                return False
            if pattern_part != '+' and pattern_part != topic_parts[i]:
                return False
        
        return len(pattern_parts) == len(topic_parts)
    
    def connect(self):
        """브로커에 연결"""
        try:
            self.client.connect(self.broker_host, self.broker_port, 60)
            self.client.loop_start()
            
            # 연결 대기
            timeout = 5
            while not self.is_connected and timeout > 0:
                import time
                time.sleep(0.1)
                timeout -= 0.1
            
            return self.is_connected
        except Exception as e:
            logger.error(f"❌ Connection error: {e}")
            return False
    
    def disconnect(self):
        """브로커 연결 해제"""
        self.client.loop_stop()
        self.client.disconnect()
    
    def publish(self, topic: str, message: dict, qos=1, retain=False):
        """메시지 발행"""
        payload = json.dumps(message)
        result = self.client.publish(topic, payload, qos=qos, retain=retain)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info(f"📤 Published to {topic}")
            return True
        else:
            logger.error(f"❌ Publish failed: {result.rc}")
            return False
    
    def subscribe(self, topic: str, callback: Callable, qos=1):
        """토픽 구독 및 콜백 등록"""
        self.message_callbacks[topic] = callback
        self.client.subscribe(topic, qos=qos)
        logger.info(f"📥 Subscribed to {topic}")
    
    def unsubscribe(self, topic: str):
        """토픽 구독 해제"""
        if topic in self.message_callbacks:
            del self.message_callbacks[topic]
        self.client.unsubscribe(topic)
        logger.info(f"🔕 Unsubscribed from {topic}")


# ============= Signal Publisher (클라이언트) =============

class SignalPublisher:
    """Signal 발행 클라이언트"""
    
    def __init__(self, broker: MQTTBroker):
        self.broker = broker
        self.base_topic = "trading/signals"
    
    def publish_signal(self, signal: TradingSignal) -> bool:
        """Signal을 MQTT로 발행"""
        topic = f"{self.base_topic}/{signal.priority.name.lower()}/{signal.signal_type.value}"
        message = signal.to_dict()
        
        return self.broker.publish(topic, message, qos=1)
    
    def buy(self, symbol: str, amount: float, price: float = None, 
            priority: Priority = Priority.NORMAL):
        """매수 신호 발행"""
        signal = TradingSignal(
            signal_id=str(uuid.uuid4()),
            signal_type=SignalType.BUY,
            priority=priority,
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
            amount=amount,
            price=price,
            source="api"
        )
        return self.publish_signal(signal)
    
    def sell(self, symbol: str, amount: float, price: float = None,
             priority: Priority = Priority.NORMAL):
        """매도 신호 발행"""
        signal = TradingSignal(
            signal_id=str(uuid.uuid4()),
            signal_type=SignalType.SELL,
            priority=priority,
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
            amount=amount,
            price=price,
            source="api"
        )
        return self.publish_signal(signal)
    
    def apply_strategy(self, strategy_name: str, percentage: float,
                      params: dict, priority: Priority = Priority.NORMAL):
        """전략 적용 신호 발행"""
        signal = TradingSignal(
            signal_id=str(uuid.uuid4()),
            signal_type=SignalType.APPLY_STRATEGY,
            priority=priority,
            timestamp=datetime.now().isoformat(),
            symbol="*",
            percentage=percentage,
            strategy_name=strategy_name,
            strategy_params=params,
            source="strategy_manager"
        )
        return self.publish_signal(signal)
    
    def emergency_stop(self):
        """긴급 정지 신호 발행"""
        signal = TradingSignal(
            signal_id=str(uuid.uuid4()),
            signal_type=SignalType.EMERGENCY_STOP,
            priority=Priority.URGENT,
            timestamp=datetime.now().isoformat(),
            symbol="*",
            source="manual"
        )
        return self.publish_signal(signal)


# ============= Trading Agent (구독자) =============

class TradingAgent:
    """Signal을 수신하고 처리하는 Agent"""
    
    def __init__(self, broker: MQTTBroker):
        self.broker = broker
        self.base_topic = "trading/signals"
        self.is_running = False
        self.active_strategies = {}
        self.signal_history = []
    
    def start(self):
        """Agent 시작 및 Signal 구독"""
        self.is_running = True
        
        # 우선순위별 토픽 구독
        self.broker.subscribe(
            f"{self.base_topic}/urgent/#",
            self._handle_urgent_signal,
            qos=2  # QoS 2 for critical messages
        )
        
        self.broker.subscribe(
            f"{self.base_topic}/high/#",
            self._handle_high_signal,
            qos=1
        )
        
        self.broker.subscribe(
            f"{self.base_topic}/normal/#",
            self._handle_normal_signal,
            qos=1
        )
        
        self.broker.subscribe(
            f"{self.base_topic}/low/#",
            self._handle_low_signal,
            qos=0
        )
        
        # 상태 리포트 발행
        self.broker.subscribe(
            "trading/commands/status",
            self._handle_status_request
        )
        
        logger.info("🚀 Trading Agent started")
    
    def stop(self):
        """Agent 정지"""
        self.is_running = False
        logger.info("🛑 Trading Agent stopped")
    
    def _handle_urgent_signal(self, topic: str, payload: str):
        """긴급 신호 처리"""
        try:
            data = json.loads(payload)
            signal = TradingSignal.from_dict(data)
            
            logger.warning(f"🚨 URGENT Signal: {signal.signal_type.value}")
            
            if signal.signal_type == SignalType.EMERGENCY_STOP:
                self._emergency_stop()
            else:
                self._execute_signal(signal, immediate=True)
        except Exception as e:
            logger.error(f"❌ Error handling urgent signal: {e}")
    
    def _handle_high_signal(self, topic: str, payload: str):
        """높은 우선순위 신호 처리"""
        try:
            data = json.loads(payload)
            signal = TradingSignal.from_dict(data)
            logger.info(f"⚡ HIGH Signal: {signal.signal_type.value}")
            self._execute_signal(signal, immediate=True)
        except Exception as e:
            logger.error(f"❌ Error handling high signal: {e}")
    
    def _handle_normal_signal(self, topic: str, payload: str):
        """일반 신호 처리"""
        try:
            data = json.loads(payload)
            signal = TradingSignal.from_dict(data)
            logger.info(f"📊 NORMAL Signal: {signal.signal_type.value}")
            self._execute_signal(signal)
        except Exception as e:
            logger.error(f"❌ Error handling normal signal: {e}")
    
    def _handle_low_signal(self, topic: str, payload: str):
        """낮은 우선순위 신호 처리"""
        try:
            data = json.loads(payload)
            signal = TradingSignal.from_dict(data)
            logger.info(f"💤 LOW Signal: {signal.signal_type.value}")
            self._execute_signal(signal)
        except Exception as e:
            logger.error(f"❌ Error handling low signal: {e}")
    
    def _execute_signal(self, signal: TradingSignal, immediate=False):
        """Signal 실행"""
        self.signal_history.append(signal)
        
        try:
            if signal.signal_type == SignalType.BUY:
                self._execute_buy(signal)
            elif signal.signal_type == SignalType.SELL:
                self._execute_sell(signal)
            elif signal.signal_type == SignalType.APPLY_STRATEGY:
                self._apply_strategy(signal)
            elif signal.signal_type == SignalType.PAUSE_STRATEGY:
                self._pause_strategy(signal)
            
            # 실행 결과 발행
            self._publish_execution_result(signal.signal_id, "completed")
            
        except Exception as e:
            logger.error(f"❌ Signal execution failed: {e}")
            self._publish_execution_result(signal.signal_id, "failed", str(e))
    
    def _execute_buy(self, signal: TradingSignal):
        """매수 실행"""
        logger.info(f"💰 Executing BUY: {signal.symbol} {signal.amount}")
        # 실제 거래소 API 호출 로직
        # exchange.create_market_buy_order(signal.symbol, signal.amount)
    
    def _execute_sell(self, signal: TradingSignal):
        """매도 실행"""
        logger.info(f"💸 Executing SELL: {signal.symbol} {signal.amount}")
        # 실제 거래소 API 호출 로직
        # exchange.create_market_sell_order(signal.symbol, signal.amount)
    
    def _apply_strategy(self, signal: TradingSignal):
        """전략 적용"""
        logger.info(f"🎯 Applying strategy: {signal.strategy_name}")
        
        self.active_strategies[signal.strategy_name] = {
            "signal_id": signal.signal_id,
            "percentage": signal.percentage,
            "params": signal.strategy_params,
            "started_at": datetime.now().isoformat()
        }
    
    def _pause_strategy(self, signal: TradingSignal):
        """전략 일시정지"""
        if signal.strategy_name in self.active_strategies:
            logger.info(f"⏸️  Pausing strategy: {signal.strategy_name}")
            del self.active_strategies[signal.strategy_name]
    
    def _emergency_stop(self):
        """긴급 정지"""
        logger.warning("🚨 EMERGENCY STOP - Canceling all orders and strategies")
        self.active_strategies.clear()
        # 모든 주문 취소 로직
    
    def _publish_execution_result(self, signal_id: str, status: str, 
                                  error: str = None):
        """실행 결과 발행"""
        result = {
            "signal_id": signal_id,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "error": error
        }
        self.broker.publish(f"trading/results/{signal_id}", result)
    
    def _handle_status_request(self, topic: str, payload: str):
        """상태 요청 처리"""
        status = {
            "agent_id": self.broker.client_id,
            "is_running": self.is_running,
            "active_strategies": list(self.active_strategies.keys()),
            "signals_processed": len(self.signal_history),
            "timestamp": datetime.now().isoformat()
        }
        self.broker.publish("trading/status/response", status)


# ============= 사용 예시 =============

if __name__ == "__main__":
    # MQTT 브로커 연결
    broker = MQTTBroker(
        broker_host="localhost",
        broker_port=1883,
        # username="your_username",
        # password="your_password"
    )
    
    if not broker.connect():
        print("Failed to connect to MQTT broker")
        exit(1)
    
    # Trading Agent 시작
    agent = TradingAgent(broker)
    agent.start()
    
    # Signal Publisher 생성
    publisher = SignalPublisher(broker)
    
    # 사용 예시들
    import time
    time.sleep(1)  # 연결 안정화 대기
    
    # 1. 매수 신호
    print("\n📤 Sending BUY signal...")
    publisher.buy("BTC/USDT", 0.1, price=45000)
    
    time.sleep(1)
    
    # 2. 전략 적용
    print("\n📤 Sending APPLY_STRATEGY signal...")
    publisher.apply_strategy(
        "grid_trading",
        percentage=30.0,
        params={
            "grid_size": 10,
            "price_range": [40000, 50000]
        }
    )
    
    time.sleep(1)
    
    # 3. 긴급 정지
    # print("\n📤 Sending EMERGENCY_STOP signal...")
    # publisher.emergency_stop()
    
    # 프로그램 실행 유지
    try:
        print("\n✅ System running... Press Ctrl+C to stop")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        agent.stop()
        broker.disconnect()