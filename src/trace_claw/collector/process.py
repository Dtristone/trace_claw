"""Per-process resource collector – tracks CPU/memory/IO for a target process."""

from __future__ import annotations

import logging
import time

import psutil

from .base import BaseCollector, MetricSample

logger = logging.getLogger(__name__)


def find_pids_by_name(process_name: str) -> list[int]:
    """Return a list of PIDs whose process name or cmdline contains *process_name*.

    The match is case-insensitive and checks both ``psutil.Process.name()``
    and the first element of ``cmdline()``.
    """
    pids: list[int] = []
    target = process_name.lower()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            pname = (proc.info.get("name") or "").lower()
            cmdline = proc.info.get("cmdline") or []
            cmd0 = cmdline[0].lower() if cmdline else ""
            if target in pname or target in cmd0:
                pids.append(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return pids


class ProcessCollector(BaseCollector):
    """Collects per-process CPU, memory and I/O metrics.

    The collector resolves *process_name* to PIDs on each call so it
    handles process restarts gracefully.  Metrics are tagged with
    ``pid`` and ``process_name`` labels.
    """

    def __init__(self, process_name: str) -> None:
        self._process_name = process_name
        # Cache psutil.Process objects keyed by pid so cpu_percent works
        self._proc_cache: dict[int, psutil.Process] = {}

    @property
    def name(self) -> str:
        return "process"

    def _get_proc(self, pid: int) -> psutil.Process | None:
        """Return a cached Process object, creating one if necessary."""
        proc = self._proc_cache.get(pid)
        if proc is None:
            try:
                proc = psutil.Process(pid)
                # prime cpu_percent so the next call returns non-zero
                proc.cpu_percent(interval=0)
                self._proc_cache[pid] = proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return None
        return proc

    def collect(self) -> list[MetricSample]:
        now = time.time()
        samples: list[MetricSample] = []

        pids = find_pids_by_name(self._process_name)
        if not pids:
            logger.debug("No process found matching %r", self._process_name)
            return samples

        # Evict stale entries from cache
        live_set = set(pids)
        for stale_pid in list(self._proc_cache):
            if stale_pid not in live_set:
                self._proc_cache.pop(stale_pid, None)

        for pid in pids:
            proc = self._get_proc(pid)
            if proc is None:
                continue

            labels = {"pid": str(pid), "process_name": self._process_name}

            try:
                cpu = proc.cpu_percent(interval=0)
                samples.append(MetricSample(
                    name="process.cpu.usage_percent",
                    value=cpu,
                    unit="%",
                    timestamp=now,
                    labels=labels,
                    description=f"CPU usage for {self._process_name} (pid {pid})",
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self._proc_cache.pop(pid, None)
                continue

            try:
                mem = proc.memory_info()
                samples.append(MetricSample(
                    name="process.memory.rss_bytes",
                    value=float(mem.rss),
                    unit="bytes",
                    timestamp=now,
                    labels=labels,
                    description=f"RSS for {self._process_name} (pid {pid})",
                ))
                samples.append(MetricSample(
                    name="process.memory.vms_bytes",
                    value=float(mem.vms),
                    unit="bytes",
                    timestamp=now,
                    labels=labels,
                    description=f"VMS for {self._process_name} (pid {pid})",
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self._proc_cache.pop(pid, None)
                continue

            try:
                mem_pct = proc.memory_percent()
                samples.append(MetricSample(
                    name="process.memory.usage_percent",
                    value=mem_pct,
                    unit="%",
                    timestamp=now,
                    labels=labels,
                    description=f"Memory % for {self._process_name} (pid {pid})",
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

            try:
                io = proc.io_counters()
                samples.append(MetricSample(
                    name="process.io.read_bytes",
                    value=float(io.read_bytes),
                    unit="bytes",
                    timestamp=now,
                    labels=labels,
                    description=f"IO read bytes for {self._process_name} (pid {pid})",
                ))
                samples.append(MetricSample(
                    name="process.io.write_bytes",
                    value=float(io.write_bytes),
                    unit="bytes",
                    timestamp=now,
                    labels=labels,
                    description=f"IO write bytes for {self._process_name} (pid {pid})",
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                # io_counters() may not be available on all platforms
                pass

        return samples
