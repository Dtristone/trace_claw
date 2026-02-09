"""Summary analysis for OpenClaw trace sessions."""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .parser import OpenClawEvent, ResourceSample


@dataclass
class SessionSummary:
    """Summary statistics for a single tracing session."""

    session_id: str
    start_time: float = 0.0
    end_time: float = 0.0
    total_duration_ms: float = 0.0
    event_count: int = 0
    model_calls: int = 0
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    error_count: int = 0
    error_rate: float = 0.0
    models_used: list[str] = field(default_factory=list)
    providers_used: list[str] = field(default_factory=list)
    avg_cpu_percent: float = 0.0
    max_cpu_percent: float = 0.0
    avg_memory_percent: float = 0.0
    max_memory_percent: float = 0.0
    avg_network_recv_rate: float = 0.0
    max_network_recv_rate: float = 0.0


@dataclass
class MultiSessionSummary:
    """Aggregate summary across multiple sessions."""

    session_count: int = 0
    total_events: int = 0
    total_model_calls: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    overall_error_rate: float = 0.0
    avg_session_duration_ms: float = 0.0
    sessions: list[SessionSummary] = field(default_factory=list)


def _percentile(data: list[float], pct: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = (pct / 100.0) * (len(sorted_data) - 1)
    low = int(idx)
    high = min(low + 1, len(sorted_data) - 1)
    frac = idx - low
    return sorted_data[low] * (1 - frac) + sorted_data[high] * frac


def summarize_session(
    events: list[OpenClawEvent],
    resources: list[ResourceSample],
    session_id: str = "",
) -> SessionSummary:
    """Compute summary statistics for a single session."""
    summary = SessionSummary(session_id=session_id or "default")
    if not events:
        return summary

    summary.event_count = len(events)
    summary.start_time = events[0].timestamp
    summary.end_time = events[-1].timestamp
    summary.total_duration_ms = (summary.end_time - summary.start_time) * 1000

    latencies: list[float] = []
    models: set[str] = set()
    providers: set[str] = set()

    for evt in events:
        if evt.event_type == "model.usage":
            summary.model_calls += 1
            summary.total_tokens_input += evt.tokens_input
            summary.total_tokens_output += evt.tokens_output
            summary.total_tokens += evt.tokens_total
            summary.total_cost_usd += evt.cost_usd
            if evt.duration_ms > 0:
                latencies.append(evt.duration_ms)
            if evt.model:
                models.add(evt.model)
            if evt.provider:
                providers.add(evt.provider)
        if evt.status == "error":
            summary.error_count += 1

    if latencies:
        summary.avg_latency_ms = statistics.mean(latencies)
        summary.p50_latency_ms = _percentile(latencies, 50)
        summary.p95_latency_ms = _percentile(latencies, 95)
        summary.p99_latency_ms = _percentile(latencies, 99)
        summary.max_latency_ms = max(latencies)

    if summary.event_count > 0:
        summary.error_rate = summary.error_count / summary.event_count

    summary.models_used = sorted(models)
    summary.providers_used = sorted(providers)

    # resource stats
    cpu_vals = [r.value for r in resources
                if r.name == "system.cpu.usage_percent" and r.labels.get("cpu") == "total"]
    mem_vals = [r.value for r in resources if r.name == "system.memory.usage_percent"]
    net_recv = [r.value for r in resources if r.name == "system.network.bytes_recv_rate"]

    if cpu_vals:
        summary.avg_cpu_percent = statistics.mean(cpu_vals)
        summary.max_cpu_percent = max(cpu_vals)
    if mem_vals:
        summary.avg_memory_percent = statistics.mean(mem_vals)
        summary.max_memory_percent = max(mem_vals)
    if net_recv:
        summary.avg_network_recv_rate = statistics.mean(net_recv)
        summary.max_network_recv_rate = max(net_recv)

    return summary


def summarize_multi_session(
    sessions: list[tuple[list[OpenClawEvent], list[ResourceSample], str]],
) -> MultiSessionSummary:
    """Aggregate summaries across multiple sessions."""
    multi = MultiSessionSummary()
    for events, resources, sid in sessions:
        s = summarize_session(events, resources, session_id=sid)
        multi.sessions.append(s)
        multi.total_events += s.event_count
        multi.total_model_calls += s.model_calls
        multi.total_tokens += s.total_tokens
        multi.total_cost_usd += s.total_cost_usd

    multi.session_count = len(multi.sessions)
    durations = [s.total_duration_ms for s in multi.sessions if s.total_duration_ms > 0]
    if durations:
        multi.avg_session_duration_ms = statistics.mean(durations)
    errors = sum(s.error_count for s in multi.sessions)
    total = sum(s.event_count for s in multi.sessions)
    multi.overall_error_rate = errors / total if total > 0 else 0.0
    return multi


def save_summary(summary: SessionSummary | MultiSessionSummary, path: str | Path) -> None:
    """Write summary to a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(asdict(summary), fh, indent=2)
