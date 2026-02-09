"""Collector manager that orchestrates resource collection."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from ..config import CollectorConfig
from .base import BaseCollector, MetricSample
from .cpu import CpuCollector
from .memory import MemoryCollector
from .network import NetworkCollector

logger = logging.getLogger(__name__)


class CollectorManager:
    """Manages multiple resource collectors and runs them on an interval.

    This class is designed to be reusable: instantiate it with a
    :class:`CollectorConfig`, register one or more sinks via
    :meth:`add_sink`, then call :meth:`start` / :meth:`stop`.
    """

    def __init__(self, config: CollectorConfig) -> None:
        self._config = config
        self._collectors: list[BaseCollector] = []
        self._sinks: list[Callable[[list[MetricSample]], None]] = []
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        if config.cpu:
            self._collectors.append(CpuCollector())
        if config.memory:
            self._collectors.append(MemoryCollector())
        if config.network:
            self._collectors.append(NetworkCollector(interface=config.network_interface))

    def add_sink(self, sink: Callable[[list[MetricSample]], None]) -> None:
        """Register a callback to receive collected samples."""
        self._sinks.append(sink)

    def collect_once(self) -> list[MetricSample]:
        """Run all collectors once and return aggregated samples."""
        all_samples: list[MetricSample] = []
        for collector in self._collectors:
            try:
                all_samples.extend(collector.collect())
            except Exception:
                logger.exception("Collector %s failed", collector.name)
        return all_samples

    def _run(self) -> None:
        """Background thread loop."""
        while not self._stop_event.is_set():
            samples = self.collect_once()
            for sink in self._sinks:
                try:
                    sink(samples)
                except Exception:
                    logger.exception("Sink failed")
            self._stop_event.wait(self._config.interval_seconds)

    def start(self) -> None:
        """Start collecting in the background."""
        if not self._config.enabled:
            return
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("CollectorManager started (interval=%.1fs)", self._config.interval_seconds)

    def stop(self) -> None:
        """Stop background collection."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("CollectorManager stopped")
