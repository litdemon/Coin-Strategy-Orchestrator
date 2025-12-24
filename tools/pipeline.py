from abc import ABC, abstractmethod
from typing import Any, Callable, List, Optional, Dict
from dataclasses import dataclass, field
from enum import Enum
import time
import asyncio
from collections import deque
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# 시그널 타입 정의
class SignalType(Enum):
    ADD_PROCESSOR = "add_processor"
    REMOVE_PROCESSOR = "remove_processor"
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"
    CHANGE_ROUTE = "change_route"
    UPDATE_CONFIG = "update_config"
    CLEAR_METRICS = "clear_metrics"


@dataclass
class Signal:
    """사용자 시그널"""
    type: SignalType
    target_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


@dataclass
class NodeMetrics:
    """노드 처리 메트릭스"""
    processed_count: int = 0
    error_count: int = 0
    dropped_count: int = 0
    last_processed_time: float = 0
    total_processing_time: float = 0
    
    @property
    def avg_processing_time(self) -> float:
        """평균 처리 시간"""
        if self.processed_count == 0:
            return 0
        return self.total_processing_time / self.processed_count
    
    def reset(self):
        """메트릭스 초기화"""
        self.processed_count = 0
        self.error_count = 0
        self.dropped_count = 0
        self.last_processed_time = 0
        self.total_processing_time = 0


@dataclass
class DataItem:
    """플로우를 통과하는 데이터 아이템"""
    value: Any
    timestamp: float = None
    metadata: Dict[str, Any] = None
    route_id: str = "default"
    item_id: str = None  # 추적을 위한 고유 ID
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
        if self.metadata is None:
            self.metadata = {}
        if self.item_id is None:
            self.item_id = f"{id(self)}_{self.timestamp}"
    
    def clone(self, **kwargs) -> 'DataItem':
        """데이터 아이템 복제"""
        return DataItem(
            value=kwargs.get('value', self.value),
            timestamp=kwargs.get('timestamp', self.timestamp),
            metadata=kwargs.get('metadata', self.metadata.copy()),
            route_id=kwargs.get('route_id', self.route_id),
            item_id=kwargs.get('item_id', self.item_id)
        )


# 노드 인터페이스
class Node(ABC):
    """모든 플로우 노드의 기본 클래스"""
    
    def __init__(self, node_id: str, max_queue_size: int = 1000):
        self.node_id = node_id
        self.subscribers: Dict[str, List['Node']] = {}
        self.is_active = True
        self.config: Dict[str, Any] = {}
        self.input_queue = asyncio.Queue(maxsize=max_queue_size)
        self.metrics = NodeMetrics()
        self._task = None
        self._lock = asyncio.Lock()  # 상태 변경 보호
        self._running = False
    
    @abstractmethod
    async def process(self, item: DataItem) -> Optional[DataItem]:
        """실제 데이터 처리 로직 (서브클래스에서 구현)"""
        pass
    
    async def handle(self, item: DataItem) -> Optional[DataItem]:
        """데이터 처리 및 메트릭스 수집"""
        if not self.is_active:
            self.metrics.dropped_count += 1
            return None
        
        start_time = time.time()
        result = None
        
        try:
            result = await self.process(item)
            self.metrics.processed_count += 1
            
        except Exception as e:
            self.metrics.error_count += 1
            logger.error(f"Error in node {self.node_id}: {e}", exc_info=True)
            
            # 에러 정보를 metadata에 저장
            if result is None:
                result = item.clone()
            result.metadata['error'] = str(e)
            result.metadata['error_node'] = self.node_id
            
        finally:
            processing_time = time.time() - start_time
            self.metrics.total_processing_time += processing_time
            self.metrics.last_processed_time = time.time()
        
        # 결과가 있으면 다음 노드로 전달
        if result is not None:
            await self.emit(result)
        
        return result
    
    def connect(self, node: 'Node', route_id: str = "default") -> 'Node':
        """노드 연결 (라우팅 ID 지원). Multicast 지원"""
        if route_id not in self.subscribers:
            self.subscribers[route_id] = []
        if node not in self.subscribers[route_id]:
            self.subscribers[route_id].append(node)
        return node
    
    def disconnect(self, node: Optional['Node'] = None, route_id: str = "default"):
        """노드 연결 해제"""
        if route_id in self.subscribers:
            if node is None:
                # 특정 route의 모든 구독자 제거
                del self.subscribers[route_id]
            else:
                # 특정 노드만 제거
                if node in self.subscribers[route_id]:
                    self.subscribers[route_id].remove(node)
                # 빈 리스트면 route 자체를 제거
                if not self.subscribers[route_id]:
                    del self.subscribers[route_id]
    
    async def emit(self, item: DataItem):
        """데이터를 다음 노드로 전달 (Multicast)"""
        if not self.is_active:
            return
        
        # route_id에 따라 적절한 구독자(들)에게 전달
        targets = self.subscribers.get(item.route_id)
        
        # default fallback
        if targets is None and "default" in self.subscribers:
            targets = self.subscribers["default"]
        
        if targets:
            for target_node in targets:
                try:
                    await target_node.input_queue.put(item)
                except asyncio.QueueFull:
                    logger.warning(
                        f"Queue full for node {target_node.node_id}, "
                        f"dropping item {item.item_id}"
                    )
                    target_node.metrics.dropped_count += 1
    
    async def pause(self):
        """노드 일시 정지"""
        async with self._lock:
            self.is_active = False
            logger.info(f"Node {self.node_id} paused")
    
    async def resume(self):
        """노드 재개"""
        async with self._lock:
            self.is_active = True
            logger.info(f"Node {self.node_id} resumed")
    
    async def update_config(self, config: Dict[str, Any]):
        """설정 업데이트"""
        async with self._lock:
            self.config.update(config)
            logger.info(f"Node {self.node_id} config updated: {config}")
    
    async def start(self):
        """노드 처리 루프 시작"""
        if self._task is None or self._task.done():
            self._running = True
            self._task = asyncio.create_task(self._process_loop())
            logger.info(f"Node {self.node_id} started")
    
    async def stop(self):
        """노드 처리 루프 중지"""
        self._running = False
        
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        logger.info(f"Node {self.node_id} stopped")
    
    async def _process_loop(self):
        """입력 큐에서 데이터를 가져와 처리하는 루프"""
        while self._running:
            try:
                # timeout을 주어 주기적으로 _running 체크
                item = await asyncio.wait_for(
                    self.input_queue.get(), 
                    timeout=1.0
                )
                try:
                    await self.handle(item)
                finally:
                    self.input_queue.task_done()
                    
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    f"Unexpected error in process loop for {self.node_id}: {e}",
                    exc_info=True
                )
    
    def get_metrics(self) -> Dict[str, Any]:
        """노드 메트릭스 조회"""
        return {
            'node_id': self.node_id,
            'is_active': self.is_active,
            'processed_count': self.metrics.processed_count,
            'error_count': self.metrics.error_count,
            'dropped_count': self.metrics.dropped_count,
            'avg_processing_time': self.metrics.avg_processing_time,
            'queue_size': self.input_queue.qsize(),
        }
    
    def clear_metrics(self):
        """메트릭스 초기화"""
        self.metrics.reset()


# Source
class Source(Node):
    """데이터 소스 노드"""
    
    def __init__(self, node_id: str, max_queue_size: int = 1000):
        super().__init__(node_id, max_queue_size)
    
    async def process(self, item: DataItem) -> Optional[DataItem]:
        """Source는 받은 데이터를 그대로 반환"""
        return item
    
    async def push_data(self, value: Any, route_id: str = "default", metadata: Dict[str, Any] = None):
        """외부에서 데이터를 푸시"""
        item = DataItem(value=value, route_id=route_id, metadata=metadata or {})
        try:
            await asyncio.wait_for(self.input_queue.put(item), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning(f"Timeout pushing data to source {self.node_id}")
            self.metrics.dropped_count += 1


# Processor
class Processor(Node):
    """데이터 변환 프로세서"""
    
    def __init__(
        self, 
        node_id: str, 
        func: Callable[[Any], Any] = None,
        max_queue_size: int = 1000
    ):
        super().__init__(node_id, max_queue_size)
        self.func = func or (lambda x: x)
    
    async def process(self, item: DataItem) -> Optional[DataItem]:
        """데이터 변환 처리"""
        if asyncio.iscoroutinefunction(self.func):
            transformed_value = await self.func(item.value)
        else:
            # CPU 집약적 작업의 경우 thread pool 사용 고려
            transformed_value = self.func(item.value)
        
        return item.clone(value=transformed_value)
    
    async def update_function(self, func: Callable[[Any], Any]):
        """처리 함수 동적 변경"""
        async with self._lock:
            self.func = func
            logger.info(f"Processor {self.node_id} function updated")


# Router Processor
class RouterProcessor(Node):
    """조건부 라우팅 프로세서"""
    
    def __init__(
        self,
        node_id: str,
        router_func: Callable[[Any], str] = None,
        max_queue_size: int = 1000
    ):
        super().__init__(node_id, max_queue_size)
        self.router_func = router_func or (lambda x: "default")
    
    async def process(self, item: DataItem) -> Optional[DataItem]:
        """라우팅 결정"""
        if asyncio.iscoroutinefunction(self.router_func):
            route_id = await self.router_func(item.value)
        else:
            route_id = self.router_func(item.value)
        
        return item.clone(route_id=route_id)
    
    async def update_router(self, router_func: Callable[[Any], str]):
        """라우팅 함수 동적 변경"""
        async with self._lock:
            self.router_func = router_func
            logger.info(f"Router {self.node_id} function updated")


# Aggregator Processor
class AggregatorProcessor(Node):
    """데이터 집계 프로세서"""
    
    def __init__(
        self,
        node_id: str,
        window_size: int = 5,
        timeout: float = None,  # 타임아웃 (초)
        max_queue_size: int = 1000
    ):
        super().__init__(node_id, max_queue_size)
        self.window_size = window_size
        self.timeout = timeout
        self.buffer: deque[DataItem] = deque(maxlen=window_size * 2)  # 최대 크기 제한
        self.last_emit_time = time.time()
    
    async def process(self, item: DataItem) -> Optional[DataItem]:
        """데이터 집계"""
        self.buffer.append(item)
        current_time = time.time()
        
        # window_size에 도달하거나 timeout 초과 시 emit
        should_emit = (
            len(self.buffer) >= self.window_size or
            (self.timeout and (current_time - self.last_emit_time) >= self.timeout)
        )
        
        if should_emit and self.buffer:
            aggregated = DataItem(
                value=[i.value for i in self.buffer],
                metadata={
                    'aggregated_count': len(self.buffer),
                    'sources': list(set(
                        i.metadata.get('source', 'unknown') for i in self.buffer
                    )),
                    'time_window': current_time - self.buffer[0].timestamp
                },
                route_id=item.route_id
            )
            self.buffer.clear()
            self.last_emit_time = current_time
            return aggregated
        
        return None


# Filter Processor
class FilterProcessor(Node):
    """조건에 맞는 데이터만 통과시키는 필터"""
    
    def __init__(
        self,
        node_id: str,
        filter_func: Callable[[Any], bool] = None,
        max_queue_size: int = 1000
    ):
        super().__init__(node_id, max_queue_size)
        self.filter_func = filter_func or (lambda x: True)
    
    async def process(self, item: DataItem) -> Optional[DataItem]:
        """필터링"""
        if asyncio.iscoroutinefunction(self.filter_func):
            passes = await self.filter_func(item.value)
        else:
            passes = self.filter_func(item.value)
        
        return item if passes else None
    
    async def update_filter(self, filter_func: Callable[[Any], bool]):
        """필터 함수 동적 변경"""
        async with self._lock:
            self.filter_func = filter_func
            logger.info(f"Filter {self.node_id} function updated")


# Error Handler
class ErrorHandler(Node):
    """에러 처리 전용 노드"""
    
    def __init__(
        self,
        node_id: str,
        error_callback: Callable[[DataItem], None] = None,
        max_queue_size: int = 1000
    ):
        super().__init__(node_id, max_queue_size)
        self.error_callback = error_callback or self._default_error_handler
        self.error_log: deque[DataItem] = deque(maxlen=100)
    
    async def process(self, item: DataItem) -> Optional[DataItem]:
        """에러 처리"""
        if 'error' in item.metadata:
            self.error_log.append(item)
            
            if asyncio.iscoroutinefunction(self.error_callback):
                await self.error_callback(item)
            else:
                self.error_callback(item)
        
        # 에러가 있어도 downstream으로 전달 (선택적)
        return item
    
    def _default_error_handler(self, item: DataItem):
        """기본 에러 핸들러"""
        logger.error(
            f"Error in item {item.item_id}: {item.metadata.get('error')} "
            f"from node {item.metadata.get('error_node')}"
        )
    
    def get_error_log(self) -> List[DataItem]:
        """에러 로그 조회"""
        return list(self.error_log)


# Sink
class Sink(Node):
    """데이터 싱크 노드"""
    
    def __init__(
        self,
        node_id: str,
        consume_func: Callable[[Any], None] = None,
        max_history: int = 1000,
        max_queue_size: int = 1000
    ):
        super().__init__(node_id, max_queue_size)
        self.consume_func = consume_func or (lambda x: logger.info(f"Sink received: {x}"))
        self.collected: deque[Any] = deque(maxlen=max_history)
    
    async def process(self, item: DataItem) -> Optional[DataItem]:
        """데이터 소비"""
        if asyncio.iscoroutinefunction(self.consume_func):
            await self.consume_func(item.value)
        else:
            self.consume_func(item.value)
        
        self.collected.append(item.value)
        return None  # Sink는 downstream이 없음
    
    async def update_consumer(self, consume_func: Callable[[Any], None]):
        """소비 함수 동적 변경"""
        async with self._lock:
            self.consume_func = consume_func
            logger.info(f"Sink {self.node_id} consumer updated")
    
    def get_collected(self, limit: int = None) -> List[Any]:
        """수집된 데이터 조회"""
        if limit:
            return list(self.collected)[-limit:]
        return list(self.collected)
    
    def clear_collected(self):
        """수집된 데이터 초기화"""
        self.collected.clear()


# Pipeline Manager
class PipelineManager:
    """파이프라인을 동적으로 관리하는 매니저"""
    
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.signal_queue = asyncio.Queue()
        self.running = False
        self.signal_task = None
        self._lock = asyncio.Lock()
    
    def register_node(self, node: Node):
        """노드 등록"""
        self.nodes[node.node_id] = node
        logger.info(f"Node registered: {node.node_id}")
    
    async def unregister_node(self, node_id: str) -> bool:
        """노드 등록 해제"""
        async with self._lock:
            node = self.nodes.get(node_id)
            if not node:
                return False
            
            # 노드 중지
            await node.stop()
            
            # 모든 연결 해제
            for other_node in self.nodes.values():
                for route_id in list(other_node.subscribers.keys()):
                    other_node.disconnect(node, route_id)
            
            # 노드 제거
            del self.nodes[node_id]
            logger.info(f"Node unregistered: {node_id}")
            return True
    
    def get_node(self, node_id: str) -> Optional[Node]:
        """노드 조회"""
        return self.nodes.get(node_id)
    
    def connect_nodes(self, from_id: str, to_id: str, route_id: str = "default") -> bool:
        """노드 간 연결"""
        from_node = self.get_node(from_id)
        to_node = self.get_node(to_id)
        
        if from_node and to_node:
            from_node.connect(to_node, route_id)
            logger.info(f"Connected: {from_id} -> {to_id} (route: {route_id})")
            return True
        return False
    
    def disconnect_nodes(
        self,
        from_id: str,
        to_id: str = None,
        route_id: str = "default"
    ) -> bool:
        """노드 연결 해제"""
        node = self.get_node(from_id)
        if not node:
            return False
        
        if to_id:
            to_node = self.get_node(to_id)
            node.disconnect(to_node, route_id)
        else:
            node.disconnect(None, route_id)
        
        logger.info(f"Disconnected: {from_id} -> {to_id or 'all'} (route: {route_id})")
        return True
    
    async def send_signal(self, signal: Signal):
        """시그널 전송"""
        await self.signal_queue.put(signal)
    
    async def start(self):
        """파이프라인 및 시그널 처리 시작"""
        if self.running:
            logger.warning("Pipeline already running")
            return
        
        self.running = True
        
        # 모든 노드 시작
        for node in self.nodes.values():
            await node.start()
        
        # 시그널 처리 태스크 시작
        self.signal_task = asyncio.create_task(self._process_signals())
        logger.info("Pipeline started")
    
    async def stop(self):
        """파이프라인 및 시그널 처리 중지"""
        if not self.running:
            return
        
        self.running = False
        
        # 시그널 처리 중지
        if self.signal_task and not self.signal_task.done():
            self.signal_task.cancel()
            try:
                await self.signal_task
            except asyncio.CancelledError:
                pass
        
        # 모든 노드 중지
        for node in self.nodes.values():
            await node.stop()
        
        logger.info("Pipeline stopped")
    
    async def _process_signals(self):
        """백그라운드에서 시그널 처리"""
        while self.running:
            try:
                signal = await asyncio.wait_for(
                    self.signal_queue.get(),
                    timeout=1.0
                )
                try:
                    await self._handle_signal(signal)
                finally:
                    self.signal_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing signal: {e}", exc_info=True)
    
    async def _handle_signal(self, signal: Signal):
        """시그널 처리"""
        node = self.get_node(signal.target_id) if signal.target_id else None
        
        if signal.type == SignalType.PAUSE and node:
            await node.pause()
        
        elif signal.type == SignalType.RESUME and node:
            await node.resume()
        
        elif signal.type == SignalType.UPDATE_CONFIG and node and signal.data:
            await node.update_config(signal.data)
        
        elif signal.type == SignalType.CHANGE_ROUTE and signal.data:
            from_id = signal.data.get('from')
            to_id = signal.data.get('to')
            route_id = signal.data.get('route', 'default')
            self.connect_nodes(from_id, to_id, route_id)
        
        elif signal.type == SignalType.ADD_PROCESSOR and signal.data:
            processor = signal.data.get('processor')
            if processor and isinstance(processor, Node):
                self.register_node(processor)
                if self.running:
                    await processor.start()
        
        elif signal.type == SignalType.REMOVE_PROCESSOR and signal.target_id:
            await self.unregister_node(signal.target_id)
        
        elif signal.type == SignalType.CLEAR_METRICS and node:
            node.clear_metrics()
            logger.info(f"Metrics cleared for node: {signal.target_id}")
        
        elif signal.type == SignalType.STOP:
            await self.stop()
    
    def get_pipeline_status(self) -> Dict[str, Any]:
        """파이프라인 전체 상태 조회"""
        return {
            'running': self.running,
            'node_count': len(self.nodes),
            'nodes': {
                node_id: node.get_metrics()
                for node_id, node in self.nodes.items()
            }
        }
    
    def get_topology(self) -> Dict[str, List[str]]:
        """파이프라인 토폴로지 조회"""
        topology = {}
        for node_id, node in self.nodes.items():
            connections = []
            for route_id, subscribers in node.subscribers.items():
                for sub in subscribers:
                    connections.append(f"{sub.node_id} (route: {route_id})")
            topology[node_id] = connections
        return topology