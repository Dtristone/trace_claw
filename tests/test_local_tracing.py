"""Tests for the local event logger and action-oriented timeline."""

import json
import tempfile
import time
from pathlib import Path

from trace_claw.analyzer.parser import (
    OpenClawEvent,
    ResourceSample,
    load_trace_dir,
    parse_openclaw_log,
)
from trace_claw.analyzer.timeline import (
    build_action_timeline,
    save_action_timeline,
)
from trace_claw.exporter.event_logger import LocalEventLogger


# ---------------------------------------------------------------------------
# LocalEventLogger tests
# ---------------------------------------------------------------------------

class TestLocalEventLogger:
    """Tests for the local event logger."""

    def test_log_llm_call(self):
        """Log an LLM call and verify the JSONL file is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = LocalEventLogger(tmpdir)
            logger.log_llm_call(
                model="gpt-4",
                provider="openai",
                tokens_input=100,
                tokens_output=50,
                duration_ms=1200,
                cost_usd=0.005,
            )
            logger.shutdown()

            jsonl_files = list(Path(tmpdir).glob("events-*.jsonl"))
            assert len(jsonl_files) == 1
            with open(jsonl_files[0]) as fh:
                line = fh.readline()
                record = json.loads(line)
            assert record["type"] == "model.usage"
            assert record["model"] == "gpt-4"
            assert record["provider"] == "openai"
            assert record["usage"]["input"] == 100
            assert record["usage"]["output"] == 50
            assert record["usage"]["total"] == 150
            assert record["durationMs"] == 1200
            assert record["costUsd"] == 0.005
            assert record["timestamp"] > 0
            assert "error" not in record

    def test_log_tool_call(self):
        """Log a tool call and verify the JSONL output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = LocalEventLogger(tmpdir)
            logger.log_tool_call(
                tool_name="web_search",
                duration_ms=350,
            )
            logger.shutdown()

            jsonl_files = list(Path(tmpdir).glob("events-*.jsonl"))
            assert len(jsonl_files) == 1
            with open(jsonl_files[0]) as fh:
                record = json.loads(fh.readline())
            assert record["type"] == "tool.call"
            assert record["name"] == "web_search"
            assert record["durationMs"] == 350

    def test_log_event_generic(self):
        """Log a generic event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = LocalEventLogger(tmpdir)
            logger.log_event(
                event_type="webhook.received",
                duration_ms=100,
            )
            logger.shutdown()

            jsonl_files = list(Path(tmpdir).glob("events-*.jsonl"))
            assert len(jsonl_files) == 1
            with open(jsonl_files[0]) as fh:
                record = json.loads(fh.readline())
            assert record["type"] == "webhook.received"
            assert record["durationMs"] == 100

    def test_log_llm_error(self):
        """Log an LLM call with an error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = LocalEventLogger(tmpdir)
            logger.log_llm_call(
                model="gpt-4",
                status="error",
                error="rate_limit",
            )
            logger.shutdown()

            jsonl_files = list(Path(tmpdir).glob("events-*.jsonl"))
            with open(jsonl_files[0]) as fh:
                record = json.loads(fh.readline())
            assert record["error"] == "rate_limit"

    def test_log_multiple_events(self):
        """Log multiple events and verify all are written."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = LocalEventLogger(tmpdir)
            logger.log_llm_call(model="gpt-4", tokens_input=100, tokens_output=50)
            logger.log_tool_call(tool_name="calculator", duration_ms=10)
            logger.log_llm_call(model="claude-3", tokens_input=200, tokens_output=100)
            logger.shutdown()

            jsonl_files = list(Path(tmpdir).glob("events-*.jsonl"))
            assert len(jsonl_files) == 1
            with open(jsonl_files[0]) as fh:
                lines = [line.strip() for line in fh if line.strip()]
            assert len(lines) == 3

    def test_events_parseable_by_analyzer(self):
        """Events written by LocalEventLogger can be parsed by the analyzer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = LocalEventLogger(tmpdir)
            logger.log_llm_call(
                model="gpt-4",
                provider="openai",
                tokens_input=100,
                tokens_output=50,
                duration_ms=1200,
                cost_usd=0.005,
            )
            logger.log_tool_call(
                tool_name="web_search",
                duration_ms=350,
            )
            logger.shutdown()

            # Parse using the analyzer
            jsonl_files = list(Path(tmpdir).glob("events-*.jsonl"))
            events = parse_openclaw_log(jsonl_files[0])
            assert len(events) == 2
            assert events[0].event_type == "model.usage"
            assert events[0].model == "gpt-4"
            assert events[0].tokens_input == 100
            assert events[0].tokens_output == 50
            assert events[0].tokens_total == 150
            assert events[0].duration_ms == 1200
            assert events[0].cost_usd == 0.005
            assert events[1].event_type == "tool.call"

    def test_load_trace_dir_finds_event_files(self):
        """load_trace_dir discovers event files written by LocalEventLogger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = LocalEventLogger(tmpdir)
            logger.log_llm_call(model="gpt-4", tokens_input=100, tokens_output=50)
            logger.shutdown()

            events, resources = load_trace_dir(tmpdir)
            assert len(events) == 1
            assert events[0].event_type == "model.usage"
            assert len(resources) == 0


# ---------------------------------------------------------------------------
# Action timeline tests
# ---------------------------------------------------------------------------

class TestActionTimeline:
    """Tests for the action-oriented timeline."""

    def test_build_action_timeline_with_resources(self):
        """Action timeline correlates events with nearby resource samples."""
        events = [
            OpenClawEvent(
                timestamp=1700000000.0,
                event_type="model.usage",
                model="gpt-4",
                provider="openai",
                duration_ms=1200,
                tokens_input=100,
                tokens_output=50,
                tokens_total=150,
                cost_usd=0.005,
            ),
            OpenClawEvent(
                timestamp=1700000002.0,
                event_type="model.usage",
                model="claude-3",
                duration_ms=800,
                tokens_input=200,
                tokens_output=100,
                tokens_total=300,
            ),
        ]
        resources = [
            ResourceSample(timestamp=1700000000.0, name="system.cpu.usage_percent", value=45.0, unit="%", labels={"cpu": "total"}),
            ResourceSample(timestamp=1700000000.0, name="system.memory.usage_percent", value=60.0, unit="%"),
            ResourceSample(timestamp=1700000000.0, name="process.cpu.usage_percent", value=12.0, unit="%", labels={"pid": "1234", "process_name": "node"}),
            ResourceSample(timestamp=1700000000.0, name="process.memory.rss_bytes", value=104857600, unit="bytes", labels={"pid": "1234", "process_name": "node"}),
            ResourceSample(timestamp=1700000002.0, name="system.cpu.usage_percent", value=80.0, unit="%", labels={"cpu": "total"}),
            ResourceSample(timestamp=1700000002.0, name="system.memory.usage_percent", value=70.0, unit="%"),
        ]

        rows = build_action_timeline(events, resources)
        assert len(rows) == 2

        # First action
        assert rows[0].action == "llm:gpt-4"
        assert rows[0].duration_ms == 1200
        assert rows[0].tokens_total == 150
        assert rows[0].cost_usd == 0.005
        assert rows[0].cpu_percent is not None
        assert rows[0].memory_percent == 60.0
        assert rows[0].process_cpu_percent == 12.0
        assert rows[0].process_rss_bytes == 104857600

        # Second action
        assert rows[1].action == "llm:claude-3"
        assert rows[1].tokens_total == 300
        assert rows[1].cpu_percent is not None
        assert rows[1].memory_percent == 70.0

    def test_build_action_timeline_tool_event(self):
        """Action timeline handles tool events."""
        events = [
            OpenClawEvent(
                timestamp=1700000000.0,
                event_type="tool.call",
                duration_ms=350,
                raw={"type": "tool.call", "name": "web_search"},
            ),
        ]
        rows = build_action_timeline(events, [])
        assert len(rows) == 1
        assert rows[0].action == "tool:web_search"

    def test_build_action_timeline_no_events(self):
        """Empty events produce empty action timeline."""
        rows = build_action_timeline([], [])
        assert rows == []

    def test_build_action_timeline_no_resources(self):
        """Actions without resources still produce rows (resources = None)."""
        events = [
            OpenClawEvent(
                timestamp=1700000000.0,
                event_type="model.usage",
                model="gpt-4",
                tokens_total=150,
            ),
        ]
        rows = build_action_timeline(events, [])
        assert len(rows) == 1
        assert rows[0].action == "llm:gpt-4"
        assert rows[0].cpu_percent is None
        assert rows[0].memory_percent is None

    def test_save_action_timeline(self):
        """Save and verify the action timeline JSON file."""
        events = [
            OpenClawEvent(
                timestamp=1700000000.0,
                event_type="model.usage",
                model="gpt-4",
                duration_ms=1200,
                tokens_input=100,
                tokens_output=50,
                tokens_total=150,
            ),
        ]
        resources = [
            ResourceSample(timestamp=1700000000.0, name="system.cpu.usage_percent", value=45.0, unit="%", labels={"cpu": "total"}),
        ]
        rows = build_action_timeline(events, resources)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "action_timeline.json"
            save_action_timeline(rows, out_path)
            assert out_path.exists()
            data = json.loads(out_path.read_text())
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["action"] == "llm:gpt-4"
            assert data[0]["tokens_total"] == 150
            assert data[0]["cpu_percent"] is not None


# ---------------------------------------------------------------------------
# Full local pipeline test
# ---------------------------------------------------------------------------

class TestFullLocalPipeline:
    """End-to-end: log events locally → collect resources → analyze → action timeline."""

    def test_event_logger_plus_resources(self):
        """Log events + write resources → parse → build action timeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # 1. Log events using LocalEventLogger
            event_logger = LocalEventLogger(tmpdir)
            event_logger.log_llm_call(
                model="gpt-4", provider="openai",
                tokens_input=100, tokens_output=50,
                duration_ms=1200, cost_usd=0.005,
            )
            event_logger.log_tool_call(tool_name="web_search", duration_ms=350)
            event_logger.log_llm_call(
                model="claude-3", provider="anthropic",
                tokens_input=200, tokens_output=100,
                duration_ms=800, cost_usd=0.003,
            )
            event_logger.shutdown()

            # 2. Write resource data (as if collected by trace_claw)
            now = time.time()
            resource_records = [
                {"name": "system.cpu.usage_percent", "value": 45.0, "unit": "%", "timestamp": now, "labels": {"cpu": "total"}},
                {"name": "system.memory.usage_percent", "value": 60.0, "unit": "%", "timestamp": now, "labels": {}},
                {"name": "process.cpu.usage_percent", "value": 12.0, "unit": "%", "timestamp": now, "labels": {"pid": "1234", "process_name": "node"}},
            ]
            with open(tmppath / "resources-2024-01-01.jsonl", "w") as fh:
                for rec in resource_records:
                    fh.write(json.dumps(rec) + "\n")

            # 3. Parse all trace data
            events, resources = load_trace_dir(tmppath)
            assert len(events) == 3
            assert len(resources) == 3

            # 4. Build action timeline
            from trace_claw.analyzer.summary import summarize_session
            summary = summarize_session(events, resources)
            assert summary.model_calls == 2
            assert summary.total_tokens == 450

            rows = build_action_timeline(events, resources)
            assert len(rows) == 3
            # All should be actions
            actions = [r.action for r in rows]
            assert any("gpt-4" in a for a in actions)
            assert any("web_search" in a for a in actions)
            assert any("claude-3" in a for a in actions)
