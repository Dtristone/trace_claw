"""Base interface for data exporters."""

from __future__ import annotations

import abc

from ..collector.base import MetricSample


class BaseExporter(abc.ABC):
    """Abstract base for exporters that receive metric samples."""

    @abc.abstractmethod
    def export(self, samples: list[MetricSample]) -> None:
        """Export a batch of metric samples."""

    @abc.abstractmethod
    def shutdown(self) -> None:
        """Flush and release resources."""
