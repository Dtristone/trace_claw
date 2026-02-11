"""Network resource collector."""

from __future__ import annotations

import time

import psutil

from .base import BaseCollector, MetricSample


class NetworkCollector(BaseCollector):
    """Collects network I/O metrics."""

    def __init__(self, interface: str = "") -> None:
        self._interface = interface
        self._prev_counters: dict[str, tuple[int, int]] | None = None
        self._prev_time: float | None = None

    @property
    def name(self) -> str:
        return "network"

    def collect(self) -> list[MetricSample]:
        now = time.time()
        samples: list[MetricSample] = []

        counters = psutil.net_io_counters(pernic=True)
        interfaces = [self._interface] if self._interface and self._interface in counters else list(counters.keys())

        current: dict[str, tuple[int, int]] = {}
        for iface in interfaces:
            if iface == "lo":
                continue
            nio = counters.get(iface)
            if nio is None:
                continue
            current[iface] = (nio.bytes_sent, nio.bytes_recv)

            samples.append(MetricSample(
                name="system.network.bytes_sent_total",
                value=float(nio.bytes_sent),
                unit="bytes",
                timestamp=now,
                labels={"interface": iface},
                description=f"Total bytes sent on {iface}",
            ))
            samples.append(MetricSample(
                name="system.network.bytes_recv_total",
                value=float(nio.bytes_recv),
                unit="bytes",
                timestamp=now,
                labels={"interface": iface},
                description=f"Total bytes received on {iface}",
            ))

            if self._prev_counters and self._prev_time:
                dt = now - self._prev_time
                if dt > 0 and iface in self._prev_counters:
                    prev_sent, prev_recv = self._prev_counters[iface]
                    rate_sent = (nio.bytes_sent - prev_sent) / dt
                    rate_recv = (nio.bytes_recv - prev_recv) / dt
                    samples.append(MetricSample(
                        name="system.network.bytes_sent_rate",
                        value=rate_sent,
                        unit="bytes/s",
                        timestamp=now,
                        labels={"interface": iface},
                        description=f"Send rate on {iface}",
                    ))
                    samples.append(MetricSample(
                        name="system.network.bytes_recv_rate",
                        value=rate_recv,
                        unit="bytes/s",
                        timestamp=now,
                        labels={"interface": iface},
                        description=f"Receive rate on {iface}",
                    ))

        self._prev_counters = current
        self._prev_time = now
        return samples
