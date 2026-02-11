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
