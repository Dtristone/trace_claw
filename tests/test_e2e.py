"""End-to-end functional tests for trace_claw.

These tests exercise the full pipeline:
  collect → export (local JSONL) → parse → analyze → timeline
They use real system metrics and a real subprocess to validate
per-process resource tracing.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from trace_claw.analyzer.parser import (
    ResourceSample,
    load_trace_dir,
    parse_openclaw_log,
    parse_resource_file,
)
from trace_claw.analyzer.summary import save_summary, summarize_session
from trace_claw.analyzer.timeline import build_timeline, save_timeline
from trace_claw.collector.manager import CollectorManager
from trace_claw.collector.process import ProcessCollector, find_pids_by_name
from trace_claw.config import CollectorConfig, LocalExporterConfig, load_config
from trace_claw.exporter.local import LocalExporter


# ---------------------------------------------------------------------------
# ProcessCollector unit tests
# ---------------------------------------------------------------------------

class TestProcessCollector:
    """Tests for the per-process resource collector."""

    def test_find_pids_by_name_self(self):
        """find_pids_by_name can find the current Python process."""
        pids = find_pids_by_name("python")
        assert len(pids) > 0
        assert os.getpid() in pids

    def test_find_pids_nonexistent(self):
        """Returns empty list for a process name that does not exist."""
        pids = find_pids_by_name("__nonexistent_process_xyz__")
        assert pids == []

    def test_process_collector_with_self(self):
        """ProcessCollector returns metrics for the current python process."""
        collector = ProcessCollector("python")
        samples = collector.collect()
        assert len(samples) > 0

        cpu_samples = [s for s in samples if s.name == "process.cpu.usage_percent"]
        assert len(cpu_samples) > 0
        for s in cpu_samples:
            assert s.labels["process_name"] == "python"
            assert "pid" in s.labels

        rss_samples = [s for s in samples if s.name == "process.memory.rss_bytes"]
        assert len(rss_samples) > 0
        for s in rss_samples:
            assert s.value > 0  # running process must use memory

        mem_pct = [s for s in samples if s.name == "process.memory.usage_percent"]
        assert len(mem_pct) > 0

    def test_process_collector_no_match(self):
        """Collector returns empty list when process name does not exist."""
        collector = ProcessCollector("__nonexistent_process_xyz__")
        samples = collector.collect()
        assert samples == []

    def test_process_collector_handles_restart(self):
        """Collector handles a process disappearing (stale PID eviction)."""
        collector = ProcessCollector("python")
        samples1 = collector.collect()
        assert len(samples1) > 0

        # Inject a fake stale PID into cache
        collector._proc_cache[999999] = None  # type: ignore[assignment]
        samples2 = collector.collect()
        assert len(samples2) > 0
        # stale PID 999999 should be evicted
        assert 999999 not in collector._proc_cache

    def test_collector_name(self):
        collector = ProcessCollector("python")
        assert collector.name == "process"


# ---------------------------------------------------------------------------
# CollectorManager with process filter
# ---------------------------------------------------------------------------

class TestCollectorManagerWithProcess:
    """Tests that CollectorManager integrates ProcessCollector correctly."""

    def test_process_filter_enabled(self):
        """When process_filter_enabled, manager includes ProcessCollector."""
        config = CollectorConfig(
            enabled=True,
            cpu=False,
            memory=False,
            network=False,
            process_filter_enabled=True,
            process_name="python",
        )
        manager = CollectorManager(config)
        names = [c.name for c in manager._collectors]
        assert "process" in names

    def test_process_filter_disabled(self):
        """When process_filter_enabled=False, no ProcessCollector."""
        config = CollectorConfig(
            enabled=True,
            cpu=True,
            memory=False,
            network=False,
            process_filter_enabled=False,
            process_name="python",
        )
        manager = CollectorManager(config)
        names = [c.name for c in manager._collectors]
        assert "process" not in names

    def test_collect_once_with_process(self):
        """collect_once gathers process metrics alongside system metrics."""
        config = CollectorConfig(
            enabled=True,
            cpu=True,
            memory=True,
            network=False,
            process_filter_enabled=True,
            process_name="python",
        )
        manager = CollectorManager(config)
        samples = manager.collect_once()
        metric_names = {s.name for s in samples}
        assert "system.cpu.usage_percent" in metric_names
        assert "system.memory.usage_percent" in metric_names
        assert "process.cpu.usage_percent" in metric_names
        assert "process.memory.rss_bytes" in metric_names


# ---------------------------------------------------------------------------
# End-to-end: collect → local JSONL → parse → analyze → timeline
# ---------------------------------------------------------------------------

class TestE2ECollectAndAnalyze:
    """Full pipeline: collect real metrics, write JSONL, parse, summarize, timeline."""

    def test_full_pipeline_system_only(self):
        """Collect system metrics → write JSONL → parse → summarize → timeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Collect system resources
            config = CollectorConfig(
                enabled=True,
                interval_seconds=0.5,
                cpu=True,
                memory=True,
                network=True,
                process_filter_enabled=False,
            )
            local_cfg = LocalExporterConfig(enabled=True, output_dir=tmpdir)
            exporter = LocalExporter(local_cfg)
            manager = CollectorManager(config)
            manager.add_sink(exporter.export)

            # Run 3 collection cycles
            for _ in range(3):
                samples = manager.collect_once()
                for sink in manager._sinks:
                    sink(samples)
                time.sleep(0.1)

            exporter.shutdown()

            # 2. Verify JSONL files were written
            jsonl_files = list(Path(tmpdir).glob("*.jsonl"))
            assert len(jsonl_files) >= 1

            # 3. Parse them back
            resources = parse_resource_file(jsonl_files[0])
            assert len(resources) > 0
            names = {r.name for r in resources}
            assert "system.cpu.usage_percent" in names
            assert "system.memory.usage_percent" in names

            # 4. Summarize (with empty events)
            summary = summarize_session([], resources)
            assert summary.avg_cpu_percent >= 0
            assert summary.avg_memory_percent >= 0

            # 5. Build timeline
            timeline = build_timeline([], resources)
            assert len(timeline) > 0
            categories = {e.category for e in timeline}
            assert "cpu" in categories
            assert "memory" in categories

    def test_full_pipeline_with_process_tracing(self):
        """Collect system + process metrics → write JSONL → parse → summarize → timeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Collect with process filter targeting current python process
            config = CollectorConfig(
                enabled=True,
                interval_seconds=0.5,
                cpu=True,
                memory=True,
                network=False,
                process_filter_enabled=True,
                process_name="python",
            )
            local_cfg = LocalExporterConfig(enabled=True, output_dir=tmpdir)
            exporter = LocalExporter(local_cfg)
            manager = CollectorManager(config)
            manager.add_sink(exporter.export)

            for _ in range(3):
                samples = manager.collect_once()
                for sink in manager._sinks:
                    sink(samples)
                time.sleep(0.1)

            exporter.shutdown()

            # 2. Parse
            jsonl_files = list(Path(tmpdir).glob("*.jsonl"))
            assert len(jsonl_files) >= 1
            resources = parse_resource_file(jsonl_files[0])

            # 3. Verify process metrics
            proc_cpu = [r for r in resources if r.name == "process.cpu.usage_percent"]
            proc_rss = [r for r in resources if r.name == "process.memory.rss_bytes"]
            assert len(proc_cpu) > 0
            assert len(proc_rss) > 0
            for r in proc_cpu:
                assert r.labels.get("process_name") == "python"
                assert "pid" in r.labels

            # 4. Summarize
            summary = summarize_session([], resources)
            assert summary.avg_process_cpu_percent >= 0
            assert summary.max_process_rss_bytes > 0

            # 5. Timeline includes process category
            timeline = build_timeline([], resources)
            categories = {e.category for e in timeline}
            assert "process" in categories

    def test_full_pipeline_with_subprocess(self):
        """Launch a real subprocess, trace it by name, verify metrics collected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Launch a subprocess that runs briefly
            proc = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(5)"],
            )
            time.sleep(0.5)  # let it start

            try:
                config = CollectorConfig(
                    enabled=True,
                    interval_seconds=0.5,
                    cpu=False,
                    memory=False,
                    network=False,
                    process_filter_enabled=True,
                    process_name="python",
                )
                local_cfg = LocalExporterConfig(enabled=True, output_dir=tmpdir)
                exporter = LocalExporter(local_cfg)
                manager = CollectorManager(config)
                manager.add_sink(exporter.export)

                # Collect twice
                for _ in range(2):
                    samples = manager.collect_once()
                    for sink in manager._sinks:
                        sink(samples)
                    time.sleep(0.3)

                exporter.shutdown()
            finally:
                proc.terminate()
                proc.wait(timeout=5)

            # Parse and verify we captured the subprocess PID
            jsonl_files = list(Path(tmpdir).glob("*.jsonl"))
            assert len(jsonl_files) >= 1
            resources = parse_resource_file(jsonl_files[0])
            all_pids = {r.labels.get("pid") for r in resources if "pid" in r.labels}
            assert str(proc.pid) in all_pids

    def test_full_pipeline_openclaw_events_and_resources(self):
        """Simulate a full trace with OpenClaw events + resource data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Write fake openclaw events
            openclaw_records = [
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
                {
                    "type": "model.usage",
                    "timestamp": 1700000002.0,
                    "channel": "telegram",
                    "provider": "anthropic",
                    "model": "claude-3",
                    "durationMs": 800,
                    "costUsd": 0.003,
                    "usage": {"input": 200, "output": 100, "total": 300},
                },
                {
                    "type": "message.processed",
                    "timestamp": 1700000003.0,
                    "channel": "telegram",
                    "outcome": "success",
                    "durationMs": 2500,
                },
            ]
            with open(tmppath / "openclaw-trace.jsonl", "w") as fh:
                for rec in openclaw_records:
                    fh.write(json.dumps(rec) + "\n")

            # Write fake resource data (system + process)
            resource_records = [
                {"name": "system.cpu.usage_percent", "value": 45.0, "unit": "%", "timestamp": 1700000000.0, "labels": {"cpu": "total"}},
                {"name": "system.memory.usage_percent", "value": 60.0, "unit": "%", "timestamp": 1700000000.5, "labels": {}},
                {"name": "process.cpu.usage_percent", "value": 12.5, "unit": "%", "timestamp": 1700000000.0, "labels": {"pid": "1234", "process_name": "node"}},
                {"name": "process.memory.rss_bytes", "value": 104857600, "unit": "bytes", "timestamp": 1700000000.0, "labels": {"pid": "1234", "process_name": "node"}},
                {"name": "system.cpu.usage_percent", "value": 80.0, "unit": "%", "timestamp": 1700000001.0, "labels": {"cpu": "total"}},
                {"name": "process.cpu.usage_percent", "value": 30.0, "unit": "%", "timestamp": 1700000001.0, "labels": {"pid": "1234", "process_name": "node"}},
                {"name": "process.memory.rss_bytes", "value": 157286400, "unit": "bytes", "timestamp": 1700000001.0, "labels": {"pid": "1234", "process_name": "node"}},
                {"name": "system.cpu.usage_percent", "value": 30.0, "unit": "%", "timestamp": 1700000003.0, "labels": {"cpu": "total"}},
                {"name": "system.network.bytes_recv_rate", "value": 1024000.0, "unit": "bytes/s", "timestamp": 1700000001.0, "labels": {"interface": "eth0"}},
            ]
            with open(tmppath / "resources-2024-01-01.jsonl", "w") as fh:
                for rec in resource_records:
                    fh.write(json.dumps(rec) + "\n")

            # Load all trace data
            events, resources = load_trace_dir(tmppath)
            assert len(events) == 4
            assert len(resources) == 9

            # Summarize
            summary = summarize_session(events, resources)
            assert summary.model_calls == 2
            assert summary.total_tokens == 450
            assert summary.total_cost_usd == 0.008
            assert summary.error_count == 0
            assert summary.avg_cpu_percent > 0
            assert summary.avg_process_cpu_percent == 21.25
            assert summary.max_process_cpu_percent == 30.0
            assert summary.max_process_rss_bytes == 157286400

            # Save summary
            summary_path = tmppath / "summary" / "session_summary.json"
            save_summary(summary, summary_path)
            assert summary_path.exists()
            saved = json.loads(summary_path.read_text())
            assert saved["model_calls"] == 2
            assert saved["avg_process_cpu_percent"] == 21.25

            # Build and save timeline
            timeline = build_timeline(events, resources)
            assert len(timeline) == 13  # 4 events + 9 resources
            categories = {e.category for e in timeline}
            assert "openclaw" in categories
            assert "cpu" in categories
            assert "memory" in categories
            assert "process" in categories
            assert "network" in categories

            timeline_path = tmppath / "summary" / "timeline.json"
            save_timeline(timeline, timeline_path)
            assert timeline_path.exists()
            timeline_data = json.loads(timeline_path.read_text())
            assert len(timeline_data) == 13

    def test_background_collection_and_stop(self):
        """Test start/stop lifecycle with background thread."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = CollectorConfig(
                enabled=True,
                interval_seconds=0.3,
                cpu=True,
                memory=False,
                network=False,
                process_filter_enabled=True,
                process_name="python",
            )
            local_cfg = LocalExporterConfig(enabled=True, output_dir=tmpdir)
            exporter = LocalExporter(local_cfg)
            manager = CollectorManager(config)
            manager.add_sink(exporter.export)

            manager.start()
            assert manager._thread is not None
            assert manager._thread.is_alive()

            time.sleep(1.0)  # let background thread run ~3 cycles

            manager.stop()
            assert manager._thread is None
            exporter.shutdown()

            # Verify data was written
            jsonl_files = list(Path(tmpdir).glob("*.jsonl"))
            assert len(jsonl_files) >= 1
            resources = parse_resource_file(jsonl_files[0])
            assert len(resources) > 0


# ---------------------------------------------------------------------------
# CLI end-to-end tests
# ---------------------------------------------------------------------------

class TestCLIE2E:
    """Tests that exercise CLI commands end-to-end."""

    def test_cli_version(self):
        result = subprocess.run(
            [sys.executable, "-m", "trace_claw.cli", "version"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "trace_claw" in result.stdout

    def test_cli_generate_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "test_openclaw.json"
            result = subprocess.run(
                [sys.executable, "-m", "trace_claw.cli", "generate-config", "-o", str(out_path)],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert out_path.exists()
            data = json.loads(out_path.read_text())
            assert data["diagnostics"]["otel"]["enabled"] is True
            assert data["plugins"]["allow"] == ["diagnostics-otel"]

    def test_cli_analyze_with_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Write test data
            with open(tmppath / "openclaw-events.jsonl", "w") as fh:
                fh.write(json.dumps({
                    "type": "model.usage", "timestamp": 1700000000.0,
                    "provider": "anthropic", "model": "claude-3",
                    "durationMs": 500, "costUsd": 0.005,
                    "usage": {"input": 100, "output": 50, "total": 150},
                }) + "\n")

            with open(tmppath / "resources-2024-01-01.jsonl", "w") as fh:
                fh.write(json.dumps({
                    "name": "system.cpu.usage_percent", "value": 45.0, "unit": "%",
                    "timestamp": 1700000000.0, "labels": {"cpu": "total"},
                }) + "\n")
                fh.write(json.dumps({
                    "name": "process.cpu.usage_percent", "value": 15.0, "unit": "%",
                    "timestamp": 1700000000.0, "labels": {"pid": "1234", "process_name": "node"},
                }) + "\n")

            result = subprocess.run(
                [sys.executable, "-m", "trace_claw.cli", "analyze",
                 "--trace-dir", str(tmppath), "--no-table"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert "Model calls:" in result.stdout
            assert "1" in result.stdout  # 1 model call
            assert "session_summary.json" in result.stdout

    def test_cli_analyze_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [sys.executable, "-m", "trace_claw.cli", "analyze",
                 "--trace-dir", str(tmpdir), "--no-table"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert "No trace data found" in result.stdout


# ---------------------------------------------------------------------------
# Config loading with process settings
# ---------------------------------------------------------------------------

class TestConfigProcessSettings:
    """Verify process_filter_enabled round-trips through config."""

    def test_config_process_filter_from_yaml(self):
        import yaml
        data = {
            "collector": {
                "process_filter_enabled": True,
                "process_name": "openclaw",
            },
        }
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            yaml.dump(data, fh)
            path = fh.name

        try:
            cfg = load_config(path)
            assert cfg.collector.process_filter_enabled is True
            assert cfg.collector.process_name == "openclaw"
        finally:
            os.unlink(path)

    def test_config_default_process_filter_disabled(self):
        cfg = load_config(Path(tempfile.gettempdir()) / "nonexistent.yaml")
        assert cfg.collector.process_filter_enabled is False
