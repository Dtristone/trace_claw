"""Tests for the analyzer module."""

import json
import tempfile
from pathlib import Path

from trace_claw.analyzer.parser import (
    OpenClawEvent,
    ResourceSample,
    load_trace_dir,
    parse_openclaw_log,
    parse_resource_file,
)
from trace_claw.analyzer.summary import (
    save_summary,
    summarize_multi_session,
    summarize_session,
)
from trace_claw.analyzer.timeline import build_timeline, save_timeline


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with open(path, "w") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


def test_parse_openclaw_log():
    records = [
        {
            "type": "model.usage",
            "timestamp": 1700000000.0,
            "channel": "telegram",
            "provider": "anthropic",
            "model": "claude-3",
            "durationMs": 1200,
            "costUsd": 0.005,
            "usage": {"input": 100, "output": 50, "total": 150},
        },
        {
            "type": "webhook.received",
            "timestamp": 1700000001.0,
            "channel": "telegram",
        },
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
        path = fh.name

    events = parse_openclaw_log(path)
    assert len(events) == 2
    assert events[0].event_type == "model.usage"
    assert events[0].tokens_input == 100
    assert events[0].duration_ms == 1200
    assert events[1].event_type == "webhook.received"


def test_parse_resource_file():
    records = [
        {"name": "system.cpu.usage_percent", "value": 45.0, "unit": "%", "timestamp": 1700000000.0, "labels": {"cpu": "total"}},
        {"name": "system.memory.usage_percent", "value": 60.0, "unit": "%", "timestamp": 1700000000.0, "labels": {}},
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
        path = fh.name

    samples = parse_resource_file(path)
    assert len(samples) == 2
    assert samples[0].name == "system.cpu.usage_percent"
    assert samples[0].value == 45.0


def test_load_trace_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # resource file
        _write_jsonl(tmppath / "resources-2024-01-01.jsonl", [
            {"name": "system.cpu.usage_percent", "value": 30.0, "unit": "%", "timestamp": 1700000000.0, "labels": {"cpu": "total"}},
        ])

        # openclaw events file
        _write_jsonl(tmppath / "openclaw-events.jsonl", [
            {"type": "model.usage", "timestamp": 1700000000.0, "channel": "test", "usage": {"input": 10, "output": 5, "total": 15}},
        ])

        events, resources = load_trace_dir(tmppath)
        assert len(events) == 1
        assert len(resources) == 1


def test_summarize_session():
    events = [
        OpenClawEvent(
            timestamp=1700000000.0, event_type="model.usage", model="claude-3",
            provider="anthropic", duration_ms=500, tokens_input=100, tokens_output=50,
            tokens_total=150, cost_usd=0.005,
        ),
        OpenClawEvent(
            timestamp=1700000001.0, event_type="model.usage", model="claude-3",
            provider="anthropic", duration_ms=800, tokens_input=200, tokens_output=100,
            tokens_total=300, cost_usd=0.01,
        ),
        OpenClawEvent(
            timestamp=1700000002.0, event_type="webhook.error", status="error", error="timeout",
        ),
    ]
    resources = [
        ResourceSample(timestamp=1700000000.0, name="system.cpu.usage_percent", value=45.0, unit="%", labels={"cpu": "total"}),
        ResourceSample(timestamp=1700000001.0, name="system.cpu.usage_percent", value=80.0, unit="%", labels={"cpu": "total"}),
        ResourceSample(timestamp=1700000000.0, name="system.memory.usage_percent", value=60.0, unit="%"),
    ]

    summary = summarize_session(events, resources)
    assert summary.model_calls == 2
    assert summary.total_tokens == 450
    assert summary.total_cost_usd == 0.015
    assert summary.error_count == 1
    assert summary.error_rate > 0
    assert summary.avg_latency_ms == 650.0
    assert summary.avg_cpu_percent == 62.5
    assert summary.max_cpu_percent == 80.0
    assert summary.avg_memory_percent == 60.0
    assert "claude-3" in summary.models_used


def test_summarize_multi_session():
    events1 = [OpenClawEvent(timestamp=1700000000.0, event_type="model.usage", tokens_total=100, duration_ms=500)]
    events2 = [OpenClawEvent(timestamp=1700000010.0, event_type="model.usage", tokens_total=200, duration_ms=600)]

    sessions = [
        (events1, [], "session-1"),
        (events2, [], "session-2"),
    ]
    multi = summarize_multi_session(sessions)
    assert multi.session_count == 2
    assert multi.total_tokens == 300
    assert multi.total_model_calls == 2


def test_build_timeline():
    events = [
        OpenClawEvent(timestamp=1700000000.0, event_type="model.usage", model="claude-3", duration_ms=500),
    ]
    resources = [
        ResourceSample(timestamp=1700000000.5, name="system.cpu.usage_percent", value=45.0, unit="%", labels={"cpu": "total"}),
    ]

    timeline = build_timeline(events, resources)
    assert len(timeline) == 2
    # first entry should be the openclaw event (earlier timestamp)
    assert timeline[0].category == "openclaw"
    assert timeline[0].relative_ms == 0.0
    assert timeline[1].category == "cpu"
    assert timeline[1].relative_ms > 0


def test_save_timeline():
    events = [
        OpenClawEvent(timestamp=1700000000.0, event_type="model.usage"),
    ]
    timeline = build_timeline(events, [])

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "timeline.json"
        save_timeline(timeline, out_path)
        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert isinstance(data, list)
        assert len(data) == 1


def test_save_summary():
    summary = summarize_session([], [])
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "summary.json"
        save_summary(summary, out_path)
        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert data["session_id"] == "default"
