"""Local file exporter – writes metric samples to JSONL files."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from ..collector.base import MetricSample
from ..config import LocalExporterConfig
from .base import BaseExporter

logger = logging.getLogger(__name__)


class LocalExporter(BaseExporter):
    """Writes metric samples to JSONL files on disk.

    One file per day is created inside the configured *output_dir*.
    """

    def __init__(self, config: LocalExporterConfig) -> None:
        self._config = config
        self._output_dir = Path(config.output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._fh = None
        self._current_date: str | None = None
        logger.info("LocalExporter initialized → %s", self._output_dir)

    def _ensure_file(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._current_date != today or self._fh is None:
            if self._fh is not None:
                self._fh.close()
            filepath = self._output_dir / f"resources-{today}.jsonl"
            self._fh = open(filepath, "a", encoding="utf-8")  # noqa: SIM115
            self._current_date = today

    def export(self, samples: list[MetricSample]) -> None:
        self._ensure_file()
        assert self._fh is not None
        for s in samples:
            record = {
                "name": s.name,
                "value": s.value,
                "unit": s.unit,
                "timestamp": s.timestamp,
                "labels": s.labels,
            }
            self._fh.write(json.dumps(record) + "\n")
        self._fh.flush()

    def shutdown(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
        logger.info("LocalExporter shut down")
