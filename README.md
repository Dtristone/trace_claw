# trace_claw

Trace and analyze [OpenClaw](https://github.com/openclaw/openclaw) AI assistant workflows with aligned system resource monitoring.

trace_claw provides:

- **Full processing traces** – LLM input/output tokens, latency, cost, status; tool/webhook details; session and queue lifecycle events, all captured via OpenClaw's built-in `diagnostics-otel` plugin.
- **System resource collection** – Modular, configurable CPU / Memory / Network collectors that run alongside OpenClaw and export to OpenTelemetry (or local JSONL files). Designed for reuse in other projects.
- **Per-process resource tracing** – Track CPU, memory (RSS/VMS), and I/O for a specific target process by name (e.g. `node` for OpenClaw). The collector resolves process names to PIDs automatically and handles restarts.
- **Summary analysis** – Per-session and multi-session statistics (latency percentiles, token counts, cost, error rates, resource peaks).
- **Unified timeline** – Aligns OpenClaw events and resource samples on a single time axis so you can correlate each stage's latency with its resource footprint.
- **Local + Online modes** – Run everything locally (JSONL files + CLI analysis), or use the provided Docker Compose stack (OpenTelemetry Collector → Prometheus → Grafana + Jaeger).

---

## Architecture & Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        trace_claw system                           │
│                                                                     │
│  ┌──────────────┐    ┌──────────────────────────────────────────┐  │
│  │   OpenClaw    │    │          CollectorManager                │  │
│  │   Gateway     │    │                                          │  │
│  │              │    │  ┌────────────┐  ┌───────────────┐       │  │
│  │  diagnostics- │    │  │CpuCollector│  │MemoryCollector│       │  │
│  │  otel plugin  │    │  └─────┬──────┘  └──────┬────────┘       │  │
│  │       │       │    │        │                 │                │  │
│  │       │       │    │  ┌─────┴──────┐  ┌──────┴────────┐       │  │
│  │       ▼       │    │  │  Network   │  │   Process     │       │  │
│  │   OTLP/HTTP   │    │  │  Collector │  │   Collector   │       │  │
│  │   (traces,    │    │  └─────┬──────┘  └──────┬────────┘       │  │
│  │    metrics,   │    │        │                 │                │  │
│  │    logs)      │    │        ▼                 ▼                │  │
│  └───────┬───────┘    │     MetricSamples (unified)              │  │
│          │            │        │                                  │  │
│          │            └────────┼──────────────────────────────────┘  │
│          │                     │                                     │
│          │            ┌────────┼──────────────────────┐              │
│          │            │   Sinks (exporters)           │              │
│          │            │  ┌─────▼──────┐ ┌────────────┐│              │
│          │            │  │LocalExporter│ │OtelExporter││              │
│          │            │  │  (JSONL)    │ │ (OTLP/HTTP)││              │
│          │            │  └─────┬──────┘ └─────┬──────┘│              │
│          │            └────────┼───────────────┼──────┘              │
│          │                     │               │                     │
│          ▼                     ▼               ▼                     │
│  ┌───────────────┐    ┌──────────────┐  ┌──────────────┐            │
│  │ OTel Collector │    │  JSONL files  │  │ OTel Collector│            │
│  │  (receives     │    │  ./trace_data │  │  (receives    │            │
│  │   OpenClaw     │    └──────┬───────┘  │   resources)  │            │
│  │   telemetry)   │           │          └──────┬───────┘            │
│  └───────┬───────┘           │                 │                     │
│          │                    ▼                 │                     │
│          │           ┌────────────────┐         │                     │
│          │           │    Analyzer     │         │                     │
│          │           │  ┌──────────┐  │         │                     │
│          │           │  │  Parser  │  │         │                     │
│          │           │  └────┬─────┘  │         │                     │
│          │           │  ┌────▼─────┐  │         │                     │
│          │           │  │ Summary  │  │         │                     │
│          │           │  └────┬─────┘  │         │                     │
│          │           │  ┌────▼─────┐  │         │                     │
│          │           │  │ Timeline │  │         │                     │
│          │           │  └──────────┘  │         │                     │
│          │           └────────────────┘         │                     │
│          ▼                                      ▼                     │
│  ┌─────────────┐                     ┌─────────────────┐             │
│  │ Prometheus   │                     │   Prometheus     │             │
│  └──────┬──────┘                     └────────┬────────┘             │
│         └──────────────┬──────────────────────┘                      │
│                        ▼                                             │
│               ┌─────────────────┐                                    │
│               │     Grafana     │                                    │
│               │   (dashboards)  │                                    │
│               └─────────────────┘                                    │
└─────────────────────────────────────────────────────────────────────┘
```

### Data flow summary

1. **OpenClaw** emits diagnostic events (model usage, webhooks, messages, sessions) via its `diagnostics-otel` plugin over OTLP/HTTP.
2. **trace_claw `collect`** runs alongside OpenClaw, collecting system-wide and per-process resource metrics at a configurable interval.
3. **Exporters** write data to local JSONL files (local mode) and/or push to an OpenTelemetry Collector (online mode).
4. **trace_claw `analyze`** reads JSONL files, parses OpenClaw events and resource samples, computes summaries, and generates a unified timeline.
5. **Online stack** (Grafana + Prometheus + Jaeger) provides real-time dashboards and trace inspection.

---

## Quick start

### 1. Install trace_claw

```bash
pip install -e .
```

### 2. Fully local workflow (no Docker / no servers)

trace_claw works entirely locally – no OpenTelemetry Collector, Docker, Prometheus or Grafana needed.

**a) Log LLM/tool events locally** (via CLI or Python API):

```bash
# Log an LLM call
trace-claw log-event llm --model gpt-4 --provider openai \
    --tokens-input 100 --tokens-output 50 --duration-ms 1200 --cost-usd 0.005

# Log a tool invocation
trace-claw log-event tool --tool-name web_search --duration-ms 350

# Log another LLM call
trace-claw log-event llm --model claude-3 --provider anthropic \
    --tokens-input 200 --tokens-output 100 --duration-ms 800 --cost-usd 0.003
```

Or use the Python API directly:

```python
from trace_claw.exporter.event_logger import LocalEventLogger

logger = LocalEventLogger("./trace_data")
logger.log_llm_call(model="gpt-4", provider="openai",
                     tokens_input=100, tokens_output=50,
                     duration_ms=1200, cost_usd=0.005)
logger.log_tool_call(tool_name="web_search", duration_ms=350)
logger.shutdown()
```

**b) Collect system resources** (in a separate terminal while your app runs):

```bash
trace-claw -c configs/trace_claw.yaml collect
```

This writes JSONL files to `./trace_data/` with CPU, memory, network and per-process metrics.

**c) Analyze and view the action timeline:**

```bash
trace-claw analyze --trace-dir ./trace_data
```

Output includes:
- **Session summary** – model calls, tokens, cost, latency percentiles, error rate, resource peaks
- **Action timeline** – each LLM/tool action with correlated resource snapshots:
  `[action(llm/tool), time, tokens, cpu%, mem%, proc_cpu%, proc_rss]`
- **Full timeline** – all events and resource samples on a unified time axis

### 3. With OpenClaw (optional)

If you use OpenClaw, generate its diagnostics config:

```bash
trace-claw generate-config -o openclaw.diagnostics.json
```

Merge the output into `~/.openclaw/openclaw.json`, then:

```bash
openclaw plugins enable diagnostics-otel
openclaw gateway restart
```

Copy OpenClaw log files (from `/tmp/openclaw/openclaw-*.log`) into the same `trace_data/` directory, then analyze as above.

---

## Per-process resource tracing

trace_claw can monitor a specific process by name (e.g. `node` for the OpenClaw gateway). Enable this in `trace_claw.yaml`:

```yaml
collector:
  process_filter_enabled: true
  process_name: "node"  # matches any process whose name or cmdline contains "node"
```

### How it works

1. On each collection interval the `ProcessCollector` calls `find_pids_by_name(process_name)`.
2. This scans `psutil.process_iter()` and returns every PID whose process name **or** first cmdline argument contains the target string (case-insensitive).
3. For each matching PID, the collector records:
   - `process.cpu.usage_percent` – CPU % used by this process
   - `process.memory.rss_bytes` – Resident Set Size
   - `process.memory.vms_bytes` – Virtual Memory Size
   - `process.memory.usage_percent` – % of total system memory
   - `process.io.read_bytes` / `process.io.write_bytes` – disk I/O (Linux)
4. Every sample is tagged with `pid` and `process_name` labels.
5. If the process restarts (new PID), the collector detects it automatically; stale cached entries are evicted.

### Per-process metrics in analysis

The analyzer summary includes:
- `avg_process_cpu_percent` / `max_process_cpu_percent`
- `avg_process_rss_bytes` / `max_process_rss_bytes`

The timeline tags process metrics under the `process` category so they align with OpenClaw events on the same time axis.

### Environment override

```bash
TRACE_CLAW_COLLECTOR_PROCESS=openclaw trace-claw collect
```

---

## Online mode (OpenTelemetry + Prometheus + Grafana)

Start the observability stack:

```bash
docker compose up -d
```

This launches:

| Service              | Port  | Purpose                                  |
|----------------------|-------|------------------------------------------|
| OTel Collector       | 4318  | Receives OTLP/HTTP from OpenClaw + trace_claw |
| Prometheus           | 9090  | Scrapes metrics from the collector       |
| Grafana              | 3000  | Dashboards (admin/admin)                 |
| Jaeger               | 16686 | Distributed tracing UI                   |

Configure OpenClaw to export to `http://<host>:4318` (see `configs/openclaw/openclaw.diagnostics.json`), then run trace_claw in online mode:

```bash
# Edit configs/trace_claw.yaml and set mode: online
trace-claw -c configs/trace_claw.yaml collect
```

Open Grafana at `http://localhost:3000` → **OpenClaw Tracing** folder → **OpenClaw Trace Dashboard**.

Open Jaeger at `http://localhost:16686` to inspect individual trace spans.

---

## Configuration

trace_claw is configured via `trace_claw.yaml` (see `configs/trace_claw.yaml` for the full reference):

```yaml
mode: local  # or "online"

collector:
  enabled: true
  interval_seconds: 2.0
  cpu: true
  memory: true
  network: true
  process_filter_enabled: true   # enable per-process tracing
  process_name: "node"           # target process to monitor

otel:
  endpoint: "http://localhost:4318"
  service_name: "trace-claw-resources"

openclaw:
  otel_endpoint: "http://localhost:4318"
  service_name: "openclaw-gateway"
  traces: true
  metrics: true
  logs: true
  sample_rate: 1.0
```

Environment variable overrides (prefix `TRACE_CLAW_`):

| Variable                        | Maps to                      |
|---------------------------------|------------------------------|
| `TRACE_CLAW_MODE`              | `mode`                       |
| `TRACE_CLAW_OTEL_ENDPOINT`    | `otel.endpoint`              |
| `TRACE_CLAW_COLLECTOR_INTERVAL`| `collector.interval_seconds` |
| `TRACE_CLAW_COLLECTOR_PROCESS` | `collector.process_name`     |

---

## CLI reference

```
trace-claw [--config <path>] <command>

Commands:
  collect          Start system resource collection
  analyze          Analyze trace data and generate timeline
  log-event        Log an LLM/tool event to local JSONL file
  generate-config  Generate OpenClaw diagnostics configuration
  version          Print version
```

### Examples

```bash
# Collect with default config (looks for trace_claw.yaml in current dir)
trace-claw collect

# Collect with custom config
trace-claw -c configs/trace_claw.yaml collect

# Log LLM and tool events locally
trace-claw log-event llm --model gpt-4 --tokens-input 100 --tokens-output 50 --duration-ms 1200
trace-claw log-event tool --tool-name web_search --duration-ms 350
trace-claw log-event llm --model claude-3 --tokens-input 200 --tokens-output 100 --duration-ms 800

# Analyze trace data (shows action timeline + full timeline)
trace-claw analyze --trace-dir ./trace_data

# Analyze without rich table output (e.g. for piping)
trace-claw analyze --trace-dir ./trace_data --no-table

# Generate OpenClaw diagnostics config
trace-claw generate-config -o openclaw.diagnostics.json

# Print version
trace-claw version
```

---

## Key modules & functions

### Collectors (`src/trace_claw/collector/`)

| Module | Class | Key function | Description |
|--------|-------|-------------|-------------|
| `base.py` | `BaseCollector` | `collect() → list[MetricSample]` | Abstract interface; all collectors return `MetricSample` dataclasses |
| `cpu.py` | `CpuCollector` | `collect()` | System-wide CPU % (total + per-core) and load averages |
| `memory.py` | `MemoryCollector` | `collect()` | System RAM usage %, used/available/total bytes, swap % |
| `network.py` | `NetworkCollector` | `collect()` | Per-interface bytes sent/received (total + rate) |
| `process.py` | `ProcessCollector` | `collect()` | Per-process CPU %, RSS, VMS, memory %, I/O bytes |
| `process.py` | — | `find_pids_by_name(name)` | Resolve process name → list of PIDs via `psutil.process_iter()` |
| `manager.py` | `CollectorManager` | `start()` / `stop()` / `collect_once()` | Runs collectors on a background thread, dispatches samples to registered sinks |

### Exporters (`src/trace_claw/exporter/`)

| Module | Class | Key function | Description |
|--------|-------|-------------|-------------|
| `local.py` | `LocalExporter` | `export(samples)` | Writes metric samples to daily JSONL files |
| `event_logger.py` | `LocalEventLogger` | `log_llm_call()`, `log_tool_call()`, `log_event()` | Writes LLM/tool action events to daily JSONL files (fully local, no servers) |
| `otel.py` | `OtelExporter` | `export(samples)` | Pushes metrics as OTel gauge observations via OTLP/HTTP |

### Analyzer (`src/trace_claw/analyzer/`)

| Module | Function | Description |
|--------|----------|-------------|
| `parser.py` | `parse_openclaw_log(path)` | Parse OpenClaw/event JSONL log → `list[OpenClawEvent]` |
| `parser.py` | `parse_resource_file(path)` | Parse trace_claw JSONL → `list[ResourceSample]` |
| `parser.py` | `load_trace_dir(dir)` | Scan directory, auto-classify files, return `(events, resources)` |
| `summary.py` | `summarize_session(events, resources)` | Compute latency percentiles, token counts, cost, error rate, resource peaks (system + process) |
| `summary.py` | `summarize_multi_session(sessions)` | Aggregate stats across multiple sessions |
| `timeline.py` | `build_timeline(events, resources)` | Merge events + resources into a unified `TimelineEntry` list sorted by time |
| `timeline.py` | `build_action_timeline(events, resources)` | Build action-oriented timeline correlating each LLM/tool action with nearby resource snapshots |
| `timeline.py` | `print_timeline(entries)` | Pretty-print full timeline to terminal with Rich |
| `timeline.py` | `print_action_timeline(rows)` | Pretty-print action timeline: `[action, time, tokens, cpu%, mem%, ...]` |

### Configuration (`src/trace_claw/config.py`)

| Function | Description |
|----------|-------------|
| `load_config(path)` | Load YAML file → `TraceClawConfig` dataclass with env var overrides |

---

## OpenClaw diagnostic events captured

trace_claw leverages OpenClaw's `diagnostics-otel` extension which exports:

**Metrics**: `openclaw.tokens`, `openclaw.cost.usd`, `openclaw.run.duration_ms`, `openclaw.context.tokens`, `openclaw.webhook.received`, `openclaw.webhook.error`, `openclaw.webhook.duration_ms`, `openclaw.message.queued`, `openclaw.message.processed`, `openclaw.message.duration_ms`, `openclaw.queue.depth`, `openclaw.queue.wait_ms`, `openclaw.session.state`, `openclaw.session.stuck`, `openclaw.run.attempt`

**Trace spans**: `openclaw.model.usage`, `openclaw.webhook.processed`, `openclaw.webhook.error`, `openclaw.message.processed`, `openclaw.session.stuck`

**System resources** (collected by trace_claw): `system.cpu.usage_percent`, `system.cpu.load_avg_*`, `system.memory.usage_percent`, `system.memory.*_bytes`, `system.swap.usage_percent`, `system.network.bytes_*_total`, `system.network.bytes_*_rate`

**Process resources** (collected by trace_claw): `process.cpu.usage_percent`, `process.memory.rss_bytes`, `process.memory.vms_bytes`, `process.memory.usage_percent`, `process.io.read_bytes`, `process.io.write_bytes`

---

## Project structure

```
trace_claw/
├── src/trace_claw/
│   ├── cli.py                  # CLI entry point
│   ├── config.py               # YAML + env config loader
│   ├── collector/              # Modular resource collectors
│   │   ├── base.py             # BaseCollector interface + MetricSample
│   │   ├── cpu.py              # System CPU metrics
│   │   ├── memory.py           # System memory metrics
│   │   ├── network.py          # Network I/O metrics
│   │   ├── process.py          # Per-process CPU/memory/IO metrics
│   │   └── manager.py          # Orchestrates collectors + sinks
│   ├── exporter/               # Data exporters
│   │   ├── base.py             # BaseExporter interface
│   │   ├── otel.py             # OTLP/HTTP exporter
│   │   ├── local.py            # JSONL file exporter (resources)
│   │   └── event_logger.py     # JSONL event logger (LLM/tool actions, fully local)
│   └── analyzer/               # Trace analysis
│       ├── parser.py           # Parse OpenClaw + resource files
│       ├── summary.py          # Session/multi-session statistics
│       └── timeline.py         # Unified timeline builder
├── configs/
│   ├── trace_claw.yaml         # Main config (with process filter settings)
│   ├── openclaw/               # OpenClaw diagnostics config
│   ├── otel-collector/         # OTel Collector config
│   ├── prometheus/             # Prometheus scrape config
│   └── grafana/                # Grafana provisioning + dashboards
├── docker-compose.yaml         # Online observability stack
├── tests/
│   ├── test_config.py          # Config loading tests
│   ├── test_collector.py       # Collector unit tests
│   ├── test_analyzer.py        # Analyzer unit tests
│   ├── test_local_tracing.py   # Local event logger + action timeline tests
│   └── test_e2e.py             # End-to-end functional tests
└── pyproject.toml              # Python packaging
```

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run only e2e tests
python -m pytest tests/test_e2e.py -v

# Run only process collector tests
python -m pytest tests/test_e2e.py::TestProcessCollector -v
```

## License

MIT