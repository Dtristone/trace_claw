"""Memory resource collector."""

from __future__ import annotations

import time

import psutil

from .base import BaseCollector, MetricSample


class MemoryCollector(BaseCollector):
    """Collects memory usage metrics."""

    @property
    def name(self) -> str:
        return "memory"

    def collect(self) -> list[MetricSample]:
        now = time.time()
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        return [
            MetricSample(
                name="system.memory.usage_percent",
                value=mem.percent,
                unit="%",
                timestamp=now,
                labels={},
                description="Memory usage percentage",
            ),
            MetricSample(
                name="system.memory.used_bytes",
                value=float(mem.used),
                unit="bytes",
                timestamp=now,
                labels={},
                description="Memory used in bytes",
            ),
            MetricSample(
                name="system.memory.available_bytes",
                value=float(mem.available),
                unit="bytes",
                timestamp=now,
                labels={},
                description="Memory available in bytes",
            ),
            MetricSample(
                name="system.memory.total_bytes",
                value=float(mem.total),
                unit="bytes",
                timestamp=now,
                labels={},
                description="Total memory in bytes",
            ),
            MetricSample(
                name="system.swap.usage_percent",
                value=swap.percent,
                unit="%",
                timestamp=now,
                labels={},
                description="Swap usage percentage",
            ),
        ]
