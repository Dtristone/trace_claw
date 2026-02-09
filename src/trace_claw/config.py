"""Configuration loading and validation for trace_claw."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class OtelExporterConfig:
    """OpenTelemetry exporter settings."""

    endpoint: str = "http://localhost:4318"
    service_name: str = "trace-claw-resources"
    headers: dict[str, str] = field(default_factory=dict)
    export_interval_ms: int = 10000


@dataclass
class CollectorConfig:
    """System resource collector settings."""

    enabled: bool = True
    interval_seconds: float = 2.0
    cpu: bool = True
    memory: bool = True
    network: bool = True
    network_interface: str = ""
    process_name: str = "node"
    process_filter_enabled: bool = False


@dataclass
class LocalExporterConfig:
    """Local file exporter settings."""

    enabled: bool = True
    output_dir: str = "./trace_data"
    format: str = "jsonl"


@dataclass
class OpenClawConfig:
    """OpenClaw diagnostics configuration reference."""

    config_path: str = "~/.openclaw/openclaw.json"
    otel_endpoint: str = "http://localhost:4318"
    service_name: str = "openclaw-gateway"
    traces: bool = True
    metrics: bool = True
    logs: bool = True
    sample_rate: float = 1.0
    flush_interval_ms: int = 10000


@dataclass
class AnalyzerConfig:
    """Analyzer settings."""

    trace_dir: str = "./trace_data"
    summary_output: str = "./trace_data/summary"


@dataclass
class TraceClawConfig:
    """Top-level trace_claw configuration."""

    mode: str = "local"
    otel: OtelExporterConfig = field(default_factory=OtelExporterConfig)
    collector: CollectorConfig = field(default_factory=CollectorConfig)
    local_exporter: LocalExporterConfig = field(default_factory=LocalExporterConfig)
    openclaw: OpenClawConfig = field(default_factory=OpenClawConfig)
    analyzer: AnalyzerConfig = field(default_factory=AnalyzerConfig)


def _merge_dict(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *source* into *target*."""
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_dict(target[key], value)
        else:
            target[key] = value
    return target


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides using TRACE_CLAW_ prefix."""
    env_map = {
        "TRACE_CLAW_MODE": ("mode",),
        "TRACE_CLAW_OTEL_ENDPOINT": ("otel", "endpoint"),
        "TRACE_CLAW_OTEL_SERVICE_NAME": ("otel", "service_name"),
        "TRACE_CLAW_COLLECTOR_INTERVAL": ("collector", "interval_seconds"),
        "TRACE_CLAW_COLLECTOR_PROCESS": ("collector", "process_name"),
        "TRACE_CLAW_LOCAL_OUTPUT_DIR": ("local_exporter", "output_dir"),
    }
    for env_key, path in env_map.items():
        value = os.environ.get(env_key)
        if value is not None:
            obj = data
            for part in path[:-1]:
                obj = obj.setdefault(part, {})
            final_key = path[-1]
            # coerce numeric values
            if final_key == "interval_seconds":
                obj[final_key] = float(value)
            else:
                obj[final_key] = value
    return data


def _dict_to_config(data: dict[str, Any]) -> TraceClawConfig:
    """Convert a raw dictionary to a TraceClaw Config dataclass."""
    otel_data = data.get("otel", {})
    collector_data = data.get("collector", {})
    local_data = data.get("local_exporter", {})
    openclaw_data = data.get("openclaw", {})
    analyzer_data = data.get("analyzer", {})

    return TraceClawConfig(
        mode=data.get("mode", "local"),
        otel=OtelExporterConfig(**{
            k: v for k, v in otel_data.items()
            if k in OtelExporterConfig.__dataclass_fields__
        }),
        collector=CollectorConfig(**{
            k: v for k, v in collector_data.items()
            if k in CollectorConfig.__dataclass_fields__
        }),
        local_exporter=LocalExporterConfig(**{
            k: v for k, v in local_data.items()
            if k in LocalExporterConfig.__dataclass_fields__
        }),
        openclaw=OpenClawConfig(**{
            k: v for k, v in openclaw_data.items()
            if k in OpenClawConfig.__dataclass_fields__
        }),
        analyzer=AnalyzerConfig(**{
            k: v for k, v in analyzer_data.items()
            if k in AnalyzerConfig.__dataclass_fields__
        }),
    )


def load_config(path: str | Path | None = None) -> TraceClawConfig:
    """Load configuration from a YAML file with environment overrides.

    Looks for ``trace_claw.yaml`` in the current directory if *path* is None.
    """
    data: dict[str, Any] = {}
    if path is None:
        path = Path("trace_claw.yaml")
    else:
        path = Path(path)

    if path.exists():
        with open(path, encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)
            if isinstance(loaded, dict):
                data = loaded

    data = _apply_env_overrides(data)
    return _dict_to_config(data)
