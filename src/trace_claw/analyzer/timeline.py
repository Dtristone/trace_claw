"""Timeline generation – aligns OpenClaw events with system resources."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .parser import OpenClawEvent, ResourceSample


@dataclass
class TimelineEntry:
    """A single row in the unified timeline."""

    timestamp: float
    relative_ms: float
    category: str  # "openclaw" | "cpu" | "memory" | "network"
    event_type: str
    label: str
    value: float = 0.0
    unit: str = ""
    duration_ms: float = 0.0
    status: str = "ok"
    details: dict = field(default_factory=dict)


def build_timeline(
    events: list[OpenClawEvent],
    resources: list[ResourceSample],
) -> list[TimelineEntry]:
    """Merge OpenClaw events and resource samples into a single timeline.

    Every entry has a ``relative_ms`` offset from the earliest timestamp so
    that both traces and resource data can be visualised on the same axis.
    """
    if not events and not resources:
        return []

    # determine global start time
    timestamps = [e.timestamp for e in events] + [r.timestamp for r in resources]
    t0 = min(timestamps)

    entries: list[TimelineEntry] = []

    # OpenClaw events
    for evt in events:
        label_parts = [evt.event_type]
        if evt.model:
            label_parts.append(evt.model)
        details: dict = {}
        if evt.tokens_total:
            details["tokens_total"] = evt.tokens_total
            details["tokens_input"] = evt.tokens_input
            details["tokens_output"] = evt.tokens_output
        if evt.cost_usd:
            details["cost_usd"] = evt.cost_usd
        if evt.error:
            details["error"] = evt.error

        entries.append(TimelineEntry(
            timestamp=evt.timestamp,
            relative_ms=(evt.timestamp - t0) * 1000,
            category="openclaw",
            event_type=evt.event_type,
            label=" | ".join(label_parts),
            value=evt.duration_ms,
            unit="ms",
            duration_ms=evt.duration_ms,
            status=evt.status,
            details=details,
        ))

    # Resource samples – group by metric name for cleaner timeline
    _category_map = {
        "system.cpu": "cpu",
        "system.memory": "memory",
        "system.swap": "memory",
        "system.network": "network",
        "process.cpu": "process",
        "process.memory": "process",
        "process.io": "process",
    }

    for sample in resources:
        category = "resource"
        for prefix, cat in _category_map.items():
            if sample.name.startswith(prefix):
                category = cat
                break
        entries.append(TimelineEntry(
            timestamp=sample.timestamp,
            relative_ms=(sample.timestamp - t0) * 1000,
            category=category,
            event_type=sample.name,
            label=f"{sample.name} ({', '.join(f'{k}={v}' for k, v in sample.labels.items())})" if sample.labels else sample.name,
            value=sample.value,
            unit=sample.unit,
            status="ok",
        ))

    entries.sort(key=lambda e: e.timestamp)
    return entries


def save_timeline(entries: list[TimelineEntry], path: str | Path) -> None:
    """Write timeline entries to a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "timestamp": e.timestamp,
            "relative_ms": round(e.relative_ms, 2),
            "category": e.category,
            "event_type": e.event_type,
            "label": e.label,
            "value": e.value,
            "unit": e.unit,
            "duration_ms": e.duration_ms,
            "status": e.status,
            "details": e.details,
        }
        for e in entries
    ]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2)


@dataclass
class ActionTimelineRow:
    """A single row in the action-oriented timeline.

    Each row represents an LLM or tool action with its nearest resource
    snapshot, producing the format:
    ``[action(llm/tool), time, tokens, cpu%, mem%, ...]``
    """

    timestamp: float
    relative_ms: float
    action: str  # e.g. "llm:gpt-4" or "tool:web_search"
    duration_ms: float = 0.0
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_total: int = 0
    cost_usd: float = 0.0
    status: str = "ok"
    cpu_percent: float | None = None
    memory_percent: float | None = None
    process_cpu_percent: float | None = None
    process_rss_bytes: float | None = None
    net_recv_rate: float | None = None


def build_action_timeline(
    events: list[OpenClawEvent],
    resources: list[ResourceSample],
    *,
    window_seconds: float = 2.0,
) -> list[ActionTimelineRow]:
    """Build an action-oriented timeline with correlated resource snapshots.

    For each event (LLM call, tool invocation, etc.) the function finds the
    nearest resource samples within *window_seconds* and attaches the resource
    values to the action row.  This produces the format:

        ``[action(llm/tool), time, tokens, cpu%, mem%, ...]``
    """
    if not events:
        return []

    timestamps = [e.timestamp for e in events] + [r.timestamp for r in resources]
    t0 = min(timestamps)

    # Index resources by metric name for fast lookup.
    # For system.cpu.usage_percent, only include the "total" aggregate.
    from bisect import bisect_left, bisect_right

    resource_by_name: dict[str, list[tuple[float, float]]] = {}
    for r in resources:
        # Skip per-core CPU entries; keep only cpu=total
        if r.name == "system.cpu.usage_percent" and r.labels.get("cpu") != "total":
            continue
        resource_by_name.setdefault(r.name, []).append((r.timestamp, r.value))
    for v in resource_by_name.values():
        v.sort()

    def _nearest(metric_name: str, ts: float) -> float | None:
        """Find the nearest resource value to *ts* within *window_seconds*."""
        series = resource_by_name.get(metric_name)
        if not series:
            return None
        times = [t for t, _ in series]
        lo = bisect_left(times, ts - window_seconds)
        hi = bisect_right(times, ts + window_seconds)
        if lo >= hi:
            return None
        # pick the closest
        best = min(range(lo, hi), key=lambda i: abs(series[i][0] - ts))
        return series[best][1]

    rows: list[ActionTimelineRow] = []
    for evt in events:
        if evt.event_type == "model.usage":
            action = f"llm:{evt.model}" if evt.model else "llm"
        elif evt.event_type == "tool.call":
            # tool name may be in raw.name
            tool_name = evt.raw.get("name", "")
            action = f"tool:{tool_name}" if tool_name else "tool"
        else:
            action = evt.event_type

        row = ActionTimelineRow(
            timestamp=evt.timestamp,
            relative_ms=(evt.timestamp - t0) * 1000,
            action=action,
            duration_ms=evt.duration_ms,
            tokens_input=evt.tokens_input,
            tokens_output=evt.tokens_output,
            tokens_total=evt.tokens_total,
            cost_usd=evt.cost_usd,
            status=evt.status,
            cpu_percent=_nearest("system.cpu.usage_percent", evt.timestamp),
            memory_percent=_nearest("system.memory.usage_percent", evt.timestamp),
            process_cpu_percent=_nearest("process.cpu.usage_percent", evt.timestamp),
            process_rss_bytes=_nearest("process.memory.rss_bytes", evt.timestamp),
            net_recv_rate=_nearest("system.network.bytes_recv_rate", evt.timestamp),
        )
        rows.append(row)

    rows.sort(key=lambda r: r.timestamp)
    return rows


def save_action_timeline(rows: list[ActionTimelineRow], path: str | Path) -> None:
    """Write the action-oriented timeline to a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [
        {
            "timestamp": r.timestamp,
            "relative_ms": round(r.relative_ms, 2),
            "action": r.action,
            "duration_ms": r.duration_ms,
            "tokens_input": r.tokens_input,
            "tokens_output": r.tokens_output,
            "tokens_total": r.tokens_total,
            "cost_usd": r.cost_usd,
            "status": r.status,
            "cpu_percent": r.cpu_percent,
            "memory_percent": r.memory_percent,
            "process_cpu_percent": r.process_cpu_percent,
            "process_rss_bytes": r.process_rss_bytes,
            "net_recv_rate": r.net_recv_rate,
        }
        for r in rows
    ]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def print_timeline(entries: list[TimelineEntry], *, max_rows: int = 200) -> None:
    """Pretty-print a timeline to the terminal using Rich."""
    from rich.console import Console
    from rich.table import Table

    table = Table(title="OpenClaw + Resource Timeline", show_lines=True)
    table.add_column("Offset (ms)", justify="right", style="cyan", width=12)
    table.add_column("Category", style="magenta", width=10)
    table.add_column("Event", style="green", width=28)
    table.add_column("Value", justify="right", width=14)
    table.add_column("Duration", justify="right", width=12)
    table.add_column("Status", width=8)
    table.add_column("Details", width=36)

    for entry in entries[:max_rows]:
        status_style = "red" if entry.status == "error" else ""
        details_str = ""
        if entry.details:
            details_str = ", ".join(f"{k}={v}" for k, v in entry.details.items())
        table.add_row(
            f"{entry.relative_ms:.1f}",
            entry.category,
            entry.label,
            f"{entry.value:.2f} {entry.unit}" if entry.value else "",
            f"{entry.duration_ms:.1f} ms" if entry.duration_ms else "",
            f"[{status_style}]{entry.status}[/{status_style}]" if status_style else entry.status,
            details_str,
        )

    console = Console()
    console.print(table)
    if len(entries) > max_rows:
        console.print(f"  ... ({len(entries) - max_rows} more entries)")


def print_action_timeline(rows: list[ActionTimelineRow], *, max_rows: int = 200) -> None:
    """Pretty-print the action-oriented timeline.

    Each row shows: action, time, tokens, and nearby system resource values.
    """
    from rich.console import Console
    from rich.table import Table

    table = Table(title="Action Timeline (local)", show_lines=True)
    table.add_column("Offset (ms)", justify="right", style="cyan", width=12)
    table.add_column("Action", style="green", width=22)
    table.add_column("Duration (ms)", justify="right", width=13)
    table.add_column("Tokens (in/out)", justify="right", width=16)
    table.add_column("Cost ($)", justify="right", width=10)
    table.add_column("Status", width=8)
    table.add_column("CPU %", justify="right", width=8)
    table.add_column("Mem %", justify="right", width=8)
    table.add_column("Proc CPU %", justify="right", width=10)
    table.add_column("Proc RSS", justify="right", width=12)

    def _fmt(val: float | None, unit: str = "") -> str:
        if val is None:
            return "-"
        if unit == "bytes":
            if val >= 1_073_741_824:
                return f"{val / 1_073_741_824:.1f} GB"
            if val >= 1_048_576:
                return f"{val / 1_048_576:.1f} MB"
            return f"{val / 1024:.0f} KB"
        return f"{val:.1f}"

    for row in rows[:max_rows]:
        status_style = "red" if row.status == "error" else ""
        tokens_str = f"{row.tokens_input}/{row.tokens_output}" if row.tokens_total else ""
        table.add_row(
            f"{row.relative_ms:.1f}",
            row.action,
            f"{row.duration_ms:.1f}" if row.duration_ms else "",
            tokens_str,
            f"{row.cost_usd:.4f}" if row.cost_usd else "",
            f"[{status_style}]{row.status}[/{status_style}]" if status_style else row.status,
            _fmt(row.cpu_percent),
            _fmt(row.memory_percent),
            _fmt(row.process_cpu_percent),
            _fmt(row.process_rss_bytes, "bytes"),
        )

    console = Console()
    console.print(table)
    if len(rows) > max_rows:
        console.print(f"  ... ({len(rows) - max_rows} more entries)")
