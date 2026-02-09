"""OpenTelemetry exporter – pushes system resource metrics via OTLP/HTTP."""

from __future__ import annotations

import logging
from typing import Any

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME

from ..collector.base import MetricSample
from ..config import OtelExporterConfig
from .base import BaseExporter

logger = logging.getLogger(__name__)


class OtelExporter(BaseExporter):
    """Exports system resource metrics to an OpenTelemetry endpoint.

    Each call to :meth:`export` records gauge observations via the OTel SDK;
    the SDK's ``PeriodicExportingMetricReader`` flushes them to the configured
    OTLP/HTTP endpoint.
    """

    def __init__(self, config: OtelExporterConfig) -> None:
        self._config = config
        resource = Resource.create({SERVICE_NAME: config.service_name})

        exporter_kwargs: dict[str, Any] = {
            "endpoint": f"{config.endpoint.rstrip('/')}/v1/metrics",
        }
        if config.headers:
            exporter_kwargs["headers"] = config.headers

        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(**exporter_kwargs),
            export_interval_millis=config.export_interval_ms,
        )
        self._provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(self._provider)
        self._meter = metrics.get_meter("trace_claw.resources")
        self._gauges: dict[str, Any] = {}

        logger.info(
            "OtelExporter initialized → %s (service=%s)",
            config.endpoint,
            config.service_name,
        )

    def _get_gauge(self, name: str, unit: str, description: str) -> Any:
        key = name
        if key not in self._gauges:
            self._gauges[key] = self._meter.create_gauge(
                name=name,
                unit=unit,
                description=description,
            )
        return self._gauges[key]

    def export(self, samples: list[MetricSample]) -> None:
        for s in samples:
            gauge = self._get_gauge(s.name, s.unit, s.description)
            gauge.set(s.value, attributes=s.labels)

    def shutdown(self) -> None:
        self._provider.shutdown()
        logger.info("OtelExporter shut down")
