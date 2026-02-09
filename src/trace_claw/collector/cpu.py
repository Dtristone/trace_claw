"""CPU resource collector."""

from __future__ import annotations

import time

import psutil

from .base import BaseCollector, MetricSample


class CpuCollector(BaseCollector):
    """Collects CPU usage metrics."""

    @property
    def name(self) -> str:
        return "cpu"

    def collect(self) -> list[MetricSample]:
        now = time.time()
        samples: list[MetricSample] = []

        overall = psutil.cpu_percent(interval=0)
        samples.append(MetricSample(
            name="system.cpu.usage_percent",
            value=overall,
            unit="%",
            timestamp=now,
            labels={"cpu": "total"},
            description="Overall CPU usage percentage",
        ))

        per_cpu = psutil.cpu_percent(interval=0, percpu=True)
        for idx, pct in enumerate(per_cpu):
            samples.append(MetricSample(
                name="system.cpu.usage_percent",
                value=pct,
                unit="%",
                timestamp=now,
                labels={"cpu": str(idx)},
                description=f"CPU core {idx} usage percentage",
            ))

        load1, load5, load15 = psutil.getloadavg()
        samples.append(MetricSample(
            name="system.cpu.load_avg_1m",
            value=load1,
            unit="1",
            timestamp=now,
            labels={},
            description="Load average 1 minute",
        ))
        samples.append(MetricSample(
            name="system.cpu.load_avg_5m",
            value=load5,
            unit="1",
            timestamp=now,
            labels={},
            description="Load average 5 minutes",
        ))

        return samples
