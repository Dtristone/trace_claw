# trace_claw

Trace and analyze [OpenClaw](https://github.com/openclaw/openclaw) AI assistant workflows with aligned system resource monitoring.

trace_claw provides:

- **Full processing traces** – LLM input/output tokens, latency, cost, status; tool/webhook details; session and queue lifecycle events, all captured via OpenClaw's built-in `diagnostics-otel` plugin.
- **System resource collection** – Modular, configurable CPU / Memory / Network collectors that run alongside OpenClaw and export to OpenTelemetry (or local JSONL files). Designed for reuse in other projects.
- **Summary analysis** – Per-session and multi-session statistics (latency percentiles, token counts, cost, error rates, resource peaks).
- **Unified timeline** – Aligns OpenClaw events and resource samples on a single time axis so you can correlate each stage's latency with its resource footprint.
- **Local + Online modes** – Run everything locally (JSONL files + CLI analysis), or use the provided Docker Compose stack (OpenTelemetry Collector → Prometheus → Grafana + Jaeger).

---

## Quick start

### 1. Install trace_claw

```bash
pip install -e .
```

### 2. Generate OpenClaw diagnostics config

```bash
trace-claw generate-config -o openclaw.diagnostics.json
```

Merge the output into `~/.openclaw/openclaw.json`, then:

```bash
openclaw plugins enable diagnostics-otel
openclaw gateway restart
```

### 3. Collect system resources (local mode)

```bash
trace-claw -c configs/trace_claw.yaml collect
```

This writes JSONL files to `./trace_data/` while OpenClaw is running.

### 4. Analyze traces

Copy OpenClaw log files (from `/tmp/openclaw/openclaw-*.log`) into the same `trace_data/` directory, then:

```bash
trace-claw analyze --trace-dir ./trace_data
```

Output includes a summary report and a unified timeline table in the terminal.

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

---

## CLI reference

```
trace-claw [--config <path>] <command>

Commands:
  collect          Start system resource collection
  analyze          Analyze trace data and generate timeline
  generate-config  Generate OpenClaw diagnostics configuration
  version          Print version
```

---

## OpenClaw diagnostic events captured

trace_claw leverages OpenClaw's `diagnostics-otel` extension which exports:

**Metrics**: `openclaw.tokens`, `openclaw.cost.usd`, `openclaw.run.duration_ms`, `openclaw.context.tokens`, `openclaw.webhook.received`, `openclaw.webhook.error`, `openclaw.webhook.duration_ms`, `openclaw.message.queued`, `openclaw.message.processed`, `openclaw.message.duration_ms`, `openclaw.queue.depth`, `openclaw.queue.wait_ms`, `openclaw.session.state`, `openclaw.session.stuck`, `openclaw.run.attempt`

**Trace spans**: `openclaw.model.usage`, `openclaw.webhook.processed`, `openclaw.webhook.error`, `openclaw.message.processed`, `openclaw.session.stuck`

**System resources** (collected by trace_claw): `system.cpu.usage_percent`, `system.cpu.load_avg_*`, `system.memory.usage_percent`, `system.memory.*_bytes`, `system.swap.usage_percent`, `system.network.bytes_*_total`, `system.network.bytes_*_rate`

---

## Project structure

```
trace_claw/
├── src/trace_claw/
│   ├── cli.py                  # CLI entry point
│   ├── config.py               # YAML + env config loader
│   ├── collector/              # Modular resource collectors
│   │   ├── base.py             # BaseCollector interface
│   │   ├── cpu.py              # CPU metrics
│   │   ├── memory.py           # Memory metrics
│   │   ├── network.py          # Network I/O metrics
│   │   └── manager.py          # Orchestrates collectors + sinks
│   ├── exporter/               # Data exporters
│   │   ├── base.py             # BaseExporter interface
│   │   ├── otel.py             # OTLP/HTTP exporter
│   │   └── local.py            # JSONL file exporter
│   └── analyzer/               # Trace analysis
│       ├── parser.py           # Parse OpenClaw + resource files
│       ├── summary.py          # Session/multi-session statistics
│       └── timeline.py         # Unified timeline builder
├── configs/
│   ├── trace_claw.yaml         # Main config
│   ├── openclaw/               # OpenClaw diagnostics config
│   ├── otel-collector/         # OTel Collector config
│   ├── prometheus/             # Prometheus scrape config
│   └── grafana/                # Grafana provisioning + dashboards
├── docker-compose.yaml         # Online observability stack
├── tests/                      # pytest test suite
└── pyproject.toml              # Python packaging
```

## License

MIT