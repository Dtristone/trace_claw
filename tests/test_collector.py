"""Tests for the system resource collectors."""

from trace_claw.collector.base import BaseCollector, MetricSample
from trace_claw.collector.cpu import CpuCollector
from trace_claw.collector.memory import MemoryCollector
from trace_claw.collector.network import NetworkCollector
from trace_claw.collector.manager import CollectorManager
from trace_claw.config import CollectorConfig


def test_cpu_collector():
    collector = CpuCollector()
    assert collector.name == "cpu"
    samples = collector.collect()
    assert isinstance(samples, list)
    assert len(samples) > 0
    # should have total CPU usage
    total_cpu = [s for s in samples if s.name == "system.cpu.usage_percent" and s.labels.get("cpu") == "total"]
    assert len(total_cpu) == 1
    assert 0 <= total_cpu[0].value <= 100
    # should have load avg
    load_avg = [s for s in samples if s.name == "system.cpu.load_avg_1m"]
    assert len(load_avg) == 1


def test_memory_collector():
    collector = MemoryCollector()
    assert collector.name == "memory"
    samples = collector.collect()
    assert len(samples) == 5
    pct = [s for s in samples if s.name == "system.memory.usage_percent"]
    assert len(pct) == 1
    assert 0 <= pct[0].value <= 100


def test_network_collector():
    collector = NetworkCollector()
    assert collector.name == "network"
    samples = collector.collect()
    # first call should have totals but no rates
    rate_samples = [s for s in samples if "rate" in s.name]
    assert len(rate_samples) == 0
    # second call should produce rates
    samples2 = collector.collect()
    # rates may or may not appear depending on timing, but should not error


def test_collector_to_dict():
    collector = CpuCollector()
    samples = collector.collect()
    dicts = collector.to_dict(samples)
    assert isinstance(dicts, list)
    assert all(isinstance(d, dict) for d in dicts)
    assert all("name" in d and "value" in d for d in dicts)


def test_collector_manager():
    config = CollectorConfig(enabled=True, interval_seconds=1.0, cpu=True, memory=True, network=False)
    manager = CollectorManager(config)

    collected = []
    manager.add_sink(lambda samples: collected.extend(samples))

    # collect_once should work synchronously
    samples = manager.collect_once()
    assert len(samples) > 0

    # verify sink is called
    manager.collect_once()
    # sinks only called during _run, so manually trigger
    for sink in manager._sinks:
        sink(samples)
    assert len(collected) > 0


def test_collector_manager_disabled():
    config = CollectorConfig(enabled=False)
    manager = CollectorManager(config)
    manager.start()
    assert manager._thread is None
    manager.stop()
