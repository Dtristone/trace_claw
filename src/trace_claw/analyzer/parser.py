"""Parse OpenClaw trace data and local resource data."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class OpenClawEvent:
    """Parsed OpenClaw diagnostic event from log files."""

    timestamp: float
    event_type: str
    channel: str = ""
    provider: str = ""
    model: str = ""
    session_key: str = ""
    session_id: str = ""
    duration_ms: float = 0.0
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_total: int = 0
    cost_usd: float = 0.0
    status: str = "ok"
    error: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class ResourceSample:
    """Parsed resource metric sample."""

    timestamp: float
    name: str
    value: float
    unit: str
    labels: dict[str, str] = field(default_factory=dict)


def parse_openclaw_log(path: str | Path) -> list[OpenClawEvent]:
    """Parse an OpenClaw JSONL log file and extract diagnostic events.

    Looks for log lines that contain OpenClaw diagnostic event markers
    (``model.usage``, ``webhook.*``, ``message.*``, etc.).
    """
    events: list[OpenClawEvent] = []
    path = Path(path)
    if not path.exists():
        logger.warning("OpenClaw log file not found: %s", path)
        return events

    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            evt_type = obj.get("type") or obj.get("event_type") or ""
            if not evt_type:
                # look for OTel-style span names
                evt_type = obj.get("name", "")

            if not evt_type:
                continue

            ts = obj.get("timestamp") or obj.get("time") or 0
            if isinstance(ts, str):
                from datetime import datetime, timezone
                try:
                    ts = datetime.fromisoformat(ts).timestamp()
                except ValueError:
                    ts = 0

            usage = obj.get("usage", {})
            event = OpenClawEvent(
                timestamp=float(ts),
                event_type=evt_type,
                channel=obj.get("channel", ""),
                provider=obj.get("provider", ""),
                model=obj.get("model", ""),
                session_key=obj.get("sessionKey", ""),
                session_id=obj.get("sessionId", ""),
                duration_ms=float(obj.get("durationMs", obj.get("duration_ms", 0))),
                tokens_input=int(usage.get("input", 0)),
                tokens_output=int(usage.get("output", 0)),
                tokens_total=int(usage.get("total", 0)),
                cost_usd=float(obj.get("costUsd", obj.get("cost_usd", 0))),
                status="error" if obj.get("error") else "ok",
                error=str(obj.get("error", "")),
                raw=obj,
            )
            events.append(event)

    events.sort(key=lambda e: e.timestamp)
    return events


def parse_resource_file(path: str | Path) -> list[ResourceSample]:
    """Parse a local JSONL resource file produced by trace_claw."""
    samples: list[ResourceSample] = []
    path = Path(path)
    if not path.exists():
        logger.warning("Resource file not found: %s", path)
        return samples

    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            samples.append(ResourceSample(
                timestamp=float(obj.get("timestamp", 0)),
                name=obj.get("name", ""),
                value=float(obj.get("value", 0)),
                unit=obj.get("unit", ""),
                labels=obj.get("labels", {}),
            ))
    return samples


def load_trace_dir(trace_dir: str | Path) -> tuple[list[OpenClawEvent], list[ResourceSample]]:
    """Load all trace and resource data from a directory.

    Scans for ``*.jsonl`` files and classifies them as OpenClaw events
    (filenames containing ``openclaw``) or resource samples.
    """
    trace_dir = Path(trace_dir)
    events: list[OpenClawEvent] = []
    resources: list[ResourceSample] = []

    if not trace_dir.exists():
        logger.warning("Trace directory does not exist: %s", trace_dir)
        return events, resources

    for fp in sorted(trace_dir.glob("*.jsonl")):
        if "resource" in fp.stem.lower():
            resources.extend(parse_resource_file(fp))
        else:
            events.extend(parse_openclaw_log(fp))

    events.sort(key=lambda e: e.timestamp)
    resources.sort(key=lambda r: r.timestamp)
    return events, resources
