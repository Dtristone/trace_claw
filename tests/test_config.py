"""Tests for the configuration module."""

import os
import tempfile
from pathlib import Path

import yaml

from trace_claw.config import (
    TraceClawConfig,
    load_config,
)


def test_load_config_defaults():
    """Loading from a non-existent file returns defaults."""
    cfg = load_config("/tmp/nonexistent_trace_claw.yaml")
    assert isinstance(cfg, TraceClawConfig)
    assert cfg.mode == "local"
    assert cfg.collector.enabled is True
    assert cfg.collector.cpu is True
    assert cfg.collector.memory is True
    assert cfg.collector.network is True
    assert cfg.otel.endpoint == "http://localhost:4318"
    assert cfg.local_exporter.format == "jsonl"


def test_load_config_from_yaml():
    """Loading from a YAML file populates values."""
    data = {
        "mode": "online",
        "collector": {
            "interval_seconds": 5.0,
            "cpu": True,
            "memory": True,
            "network": False,
        },
        "otel": {
            "endpoint": "http://otel:4318",
            "service_name": "my-service",
        },
    }
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        yaml.dump(data, fh)
        path = fh.name

    try:
        cfg = load_config(path)
        assert cfg.mode == "online"
        assert cfg.collector.interval_seconds == 5.0
        assert cfg.collector.network is False
        assert cfg.otel.endpoint == "http://otel:4318"
        assert cfg.otel.service_name == "my-service"
    finally:
        os.unlink(path)


def test_env_override():
    """Environment variables override YAML values."""
    data = {"mode": "local"}
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        yaml.dump(data, fh)
        path = fh.name

    try:
        os.environ["TRACE_CLAW_MODE"] = "online"
        os.environ["TRACE_CLAW_OTEL_ENDPOINT"] = "http://env-otel:4318"
        cfg = load_config(path)
        assert cfg.mode == "online"
        assert cfg.otel.endpoint == "http://env-otel:4318"
    finally:
        os.environ.pop("TRACE_CLAW_MODE", None)
        os.environ.pop("TRACE_CLAW_OTEL_ENDPOINT", None)
        os.unlink(path)
