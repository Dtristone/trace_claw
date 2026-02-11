"""Local event logger – writes LLM/tool action events to JSONL files.

This enables fully local tracing of LLM calls and tool invocations without
requiring OpenClaw's diagnostics-otel plugin or any server infrastructure.
Events are written in the same JSONL format that the analyzer can parse.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class LocalEventLogger:
    """Logs LLM and tool action events to local JSONL files.

    Events are written in a format compatible with :func:`parse_openclaw_log`
    so the analyzer, summary and timeline tools work seamlessly.

    Usage::

        logger = LocalEventLogger("./trace_data")
        logger.log_llm_call(
            model="gpt-4", provider="openai",
            tokens_input=100, tokens_output=50,
            duration_ms=1200, cost_usd=0.005,
        )
        logger.log_tool_call(tool_name="web_search", duration_ms=350)
        logger.shutdown()
    """

    def __init__(self, output_dir: str | Path = "./trace_data") -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._fh = None
        self._current_date: str | None = None
        logger.info("LocalEventLogger initialized → %s", self._output_dir)

    def _ensure_file(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._current_date != today or self._fh is None:
            if self._fh is not None:
                self._fh.close()
            filepath = self._output_dir / f"events-{today}.jsonl"
            self._fh = open(filepath, "a", encoding="utf-8")  # noqa: SIM115
            self._current_date = today

    def log_llm_call(
        self,
        *,
        model: str = "",
        provider: str = "",
        tokens_input: int = 0,
        tokens_output: int = 0,
        duration_ms: float = 0.0,
        cost_usd: float = 0.0,
        status: str = "ok",
        error: str = "",
        session_id: str = "",
        extra: dict | None = None,
    ) -> None:
        """Log an LLM call event."""
        record = {
            "type": "model.usage",
            "timestamp": time.time(),
            "provider": provider,
            "model": model,
            "durationMs": duration_ms,
            "costUsd": cost_usd,
            "usage": {
                "input": tokens_input,
                "output": tokens_output,
                "total": tokens_input + tokens_output,
            },
            "sessionId": session_id,
        }
        if status == "error" or error:
            record["error"] = error or "unknown error"
        if extra:
            record.update(extra)
        self._write(record)

    def log_tool_call(
        self,
        *,
        tool_name: str,
        duration_ms: float = 0.0,
        status: str = "ok",
        error: str = "",
        session_id: str = "",
        extra: dict | None = None,
    ) -> None:
        """Log a tool invocation event."""
        record = {
            "type": "tool.call",
            "timestamp": time.time(),
            "name": tool_name,
            "durationMs": duration_ms,
            "sessionId": session_id,
        }
        if status == "error" or error:
            record["error"] = error or "unknown error"
        if extra:
            record.update(extra)
        self._write(record)

    def log_event(
        self,
        *,
        event_type: str,
        duration_ms: float = 0.0,
        status: str = "ok",
        error: str = "",
        extra: dict | None = None,
    ) -> None:
        """Log a generic event."""
        record: dict = {
            "type": event_type,
            "timestamp": time.time(),
            "durationMs": duration_ms,
        }
        if status == "error" or error:
            record["error"] = error or "unknown error"
        if extra:
            record.update(extra)
        self._write(record)

    def _write(self, record: dict) -> None:
        self._ensure_file()
        assert self._fh is not None
        self._fh.write(json.dumps(record) + "\n")
        self._fh.flush()

    def shutdown(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
        logger.info("LocalEventLogger shut down")
