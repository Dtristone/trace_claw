"""Base interface for system resource collectors."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any


@dataclass
class MetricSample:
    """A single metric data point."""

    name: str
    value: float
    unit: str
    timestamp: float
    labels: dict[str, str]
    description: str = ""


class BaseCollector(abc.ABC):
    """Abstract base class for system resource collectors."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Collector name used in configuration and output."""

    @abc.abstractmethod
    def collect(self) -> list[MetricSample]:
        """Collect current resource metrics. Returns a list of samples."""

    def to_dict(self, samples: list[MetricSample]) -> list[dict[str, Any]]:
        """Serialize samples to plain dictionaries."""
        return [
            {
                "name": s.name,
                "value": s.value,
                "unit": s.unit,
                "timestamp": s.timestamp,
                "labels": s.labels,
                "description": s.description,
            }
            for s in samples
        ]
