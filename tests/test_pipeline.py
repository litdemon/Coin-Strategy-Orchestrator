import unittest
import asyncio
import time
from typing import Any, List
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.pipeline import (
    Source, Processor, Sink, RouterProcessor, 
    FilterProcessor, AggregatorProcessor, PipelineManager,
    DataItem, Signal, SignalType
)

class TestPipeline(unittest.IsolatedAsyncioTestCase):
    
    async def test_simple_flow(self):
        """Source -> Sink basic flow test"""
        source = Source("source1")
        sink = Sink("sink1")
        
        source.connect(sink)
        
        await source.start()
        await sink.start()
        
        test_value = "hello"
        await source.push_data(test_value)
        
        # Wait for processing
        await asyncio.sleep(0.1)
        
        collected = sink.get_collected()
        self.assertEqual(len(collected), 1)
        self.assertEqual(collected[0], test_value)
        
        await source.stop()
        await sink.stop()

    async def test_processor_tranformation(self):
        """Source -> Processor -> Sink transformation test"""
        source = Source("source")
        # Processor that adds 1 to input
        processor = Processor("add_one", func=lambda x: x + 1)
        sink = Sink("sink")
        
        source.connect(processor).connect(sink)
        
        await source.start()
        await processor.start()
        await sink.start()
        
        await source.push_data(10)
        await asyncio.sleep(0.1)
        
        collected = sink.get_collected()
        self.assertEqual(collected[0], 11)
        
        await source.stop()
        await processor.stop()
        await sink.stop()

    async def test_router(self):
        """Source -> Router -> (Sink A, Sink B) routing test"""
        source = Source("source")
        
        # Router: even -> route_a, odd -> route_b
        def route_func(x):
            return "route_a" if x % 2 == 0 else "route_b"
            
        router = RouterProcessor("router", router_func=route_func)
        
        sink_a = Sink("sink_a")
        sink_b = Sink("sink_b")
        
        source.connect(router)
        router.connect(sink_a, route_id="route_a")
        router.connect(sink_b, route_id="route_b")
        
        for node in [source, router, sink_a, sink_b]:
            await node.start()
            
        await source.push_data(2) # Even -> A
        await source.push_data(3) # Odd -> B
        
        await asyncio.sleep(0.1)
        
        self.assertEqual(sink_a.get_collected(), [2])
        self.assertEqual(sink_b.get_collected(), [3])
        
        for node in [source, router, sink_a, sink_b]:
            await node.stop()

    async def test_filter(self):
        """Source -> Filter -> Sink filtering test"""
        source = Source("source")
        # Filter: allow only values > 5
        filter_node = FilterProcessor("filter", filter_func=lambda x: x > 5)
        sink = Sink("sink")
        
        source.connect(filter_node).connect(sink)
        
        for node in [source, filter_node, sink]:
            await node.start()
            
        await source.push_data(3) # Should be blocked
        await source.push_data(8) # Should pass
        
        await asyncio.sleep(0.1)
        
        collected = sink.get_collected()
        self.assertEqual(collected, [8])
        
        for node in [source, filter_node, sink]:
            await node.stop()

    async def test_aggregator(self):
        """Source -> Aggregator -> Sink aggregation test"""
        source = Source("source")
        # Aggregator: size 3 or timeout
        aggregator = AggregatorProcessor("agg", window_size=3)
        sink = Sink("sink")
        
        source.connect(aggregator).connect(sink)
        
        for node in [source, aggregator, sink]:
            await node.start()
            
        # Push 2 items (buffer not full yet)
        await source.push_data(1)
        await source.push_data(2)
        await asyncio.sleep(0.1)
        self.assertEqual(len(sink.get_collected()), 0)
        
        # Push 3rd item (buffer full -> emit)
        await source.push_data(3)
        await asyncio.sleep(0.1)
        
        collected = sink.get_collected()
        self.assertEqual(len(collected), 1)
        self.assertEqual(collected[0], [1, 2, 3])
        
        for node in [source, aggregator, sink]:
            await node.stop()

    async def test_pipeline_manager(self):
        """PipelineManager integration test"""
        manager = PipelineManager()
        
        source = Source("src")
        sink = Sink("snk")
        
        manager.register_node(source)
        manager.register_node(sink)
        
        # Dynamic connect via Signal (or direct method for test setup)
        manager.connect_nodes("src", "snk")
        
        await manager.start()
        
        await source.push_data("msg1")
        await asyncio.sleep(0.1)
        
        self.assertEqual(sink.get_collected(), ["msg1"])
        
        # Test Pause Signal
        await manager.send_signal(Signal(SignalType.PAUSE, target_id="src"))
        await asyncio.sleep(0.1)
        
        self.assertFalse(source.is_active)
        
        # Test Resume Signal
        await manager.send_signal(Signal(SignalType.RESUME, target_id="src"))
        await asyncio.sleep(0.1)
        
        self.assertTrue(source.is_active)
        
        await manager.stop()

    async def test_metrics(self):
        """Metrics collection test"""
        source = Source("src")
        sink = Sink("snk")
        source.connect(sink)
        
        await source.start()
        await sink.start()
        
        # Send 5 messages
        for i in range(5):
            await source.push_data(i)
        
        await asyncio.sleep(0.1)
        
        metrics = source.get_metrics()
        # Source metric: processed 5
        self.assertEqual(metrics['processed_count'], 5)
        
        await source.stop()
        await sink.stop()

if __name__ == '__main__':
    unittest.main()
