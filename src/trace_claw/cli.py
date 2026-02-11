"""CLI interface for trace_claw."""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from pathlib import Path

from . import __version__
from .config import load_config


def _cmd_collect(args: argparse.Namespace) -> None:
    """Run system resource collection."""
    cfg = load_config(args.config)

    from .collector.manager import CollectorManager
    from .exporter.local import LocalExporter

    exporters = []

    if cfg.local_exporter.enabled:
        local_exp = LocalExporter(cfg.local_exporter)
        exporters.append(local_exp)

    if cfg.mode == "online":
        from .exporter.otel import OtelExporter
        otel_exp = OtelExporter(cfg.otel)
        exporters.append(otel_exp)

    manager = CollectorManager(cfg.collector)
    for exp in exporters:
        manager.add_sink(exp.export)

    stop = False

    def _handle_signal(_sig: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    manager.start()
    print(f"trace_claw collector running (mode={cfg.mode}, interval={cfg.collector.interval_seconds}s)")
    print("Press Ctrl+C to stop.\n")
    try:
        while not stop:
            time.sleep(0.5)
    finally:
        manager.stop()
        for exp in exporters:
            exp.shutdown()
    print("\nCollection stopped.")


def _cmd_analyze(args: argparse.Namespace) -> None:
    """Run trace analysis and print summary."""
    cfg = load_config(args.config)
    trace_dir = args.trace_dir or cfg.analyzer.trace_dir

    from .analyzer.parser import load_trace_dir
    from .analyzer.summary import save_summary, summarize_session
    from .analyzer.timeline import (
        build_action_timeline,
        build_timeline,
        print_action_timeline,
        print_timeline,
        save_action_timeline,
        save_timeline,
    )

    events, resources = load_trace_dir(trace_dir)

    if not events and not resources:
        print(f"No trace data found in {trace_dir}")
        return

    print(f"Loaded {len(events)} events, {len(resources)} resource samples\n")

    # Summary
    summary = summarize_session(events, resources)
    summary_path = Path(cfg.analyzer.summary_output) / "session_summary.json"
    save_summary(summary, summary_path)
    print(f"Session summary saved to {summary_path}")
    print(f"  Model calls:    {summary.model_calls}")
    print(f"  Total tokens:   {summary.total_tokens}")
    print(f"  Total cost:     ${summary.total_cost_usd:.4f}")
    print(f"  Avg latency:    {summary.avg_latency_ms:.1f} ms")
    print(f"  P95 latency:    {summary.p95_latency_ms:.1f} ms")
    print(f"  Error rate:     {summary.error_rate:.1%}")
    print(f"  Avg CPU:        {summary.avg_cpu_percent:.1f}%")
    print(f"  Max CPU:        {summary.max_cpu_percent:.1f}%")
    print(f"  Avg Memory:     {summary.avg_memory_percent:.1f}%")
    print()

    # Full timeline
    timeline = build_timeline(events, resources)
    timeline_path = Path(cfg.analyzer.summary_output) / "timeline.json"
    save_timeline(timeline, timeline_path)
    print(f"Timeline saved to {timeline_path} ({len(timeline)} entries)")

    # Action-oriented timeline (correlates actions with resources)
    if events:
        action_rows = build_action_timeline(events, resources)
        action_path = Path(cfg.analyzer.summary_output) / "action_timeline.json"
        save_action_timeline(action_rows, action_path)
        print(f"Action timeline saved to {action_path} ({len(action_rows)} rows)")

    if not args.no_table:
        print()
        if events:
            print_action_timeline(action_rows)
            print()
        print_timeline(timeline)


def _cmd_log_event(args: argparse.Namespace) -> None:
    """Log a single LLM or tool event to a local JSONL file."""
    cfg = load_config(args.config)
    output_dir = cfg.local_exporter.output_dir

    from .exporter.event_logger import LocalEventLogger

    logger = LocalEventLogger(output_dir)
    try:
        if args.event_type == "llm":
            logger.log_llm_call(
                model=args.model or "",
                provider=args.provider or "",
                tokens_input=args.tokens_input or 0,
                tokens_output=args.tokens_output or 0,
                duration_ms=args.duration_ms or 0.0,
                cost_usd=args.cost_usd or 0.0,
                status=args.status or "ok",
                error=args.error or "",
            )
            print(f"Logged LLM call: model={args.model or '(none)'} → {output_dir}")
        elif args.event_type == "tool":
            logger.log_tool_call(
                tool_name=args.tool_name or "",
                duration_ms=args.duration_ms or 0.0,
                status=args.status or "ok",
                error=args.error or "",
            )
            print(f"Logged tool call: tool={args.tool_name or '(none)'} → {output_dir}")
        else:
            logger.log_event(
                event_type=args.event_type,
                duration_ms=args.duration_ms or 0.0,
                status=args.status or "ok",
                error=args.error or "",
            )
            print(f"Logged event: type={args.event_type} → {output_dir}")
    finally:
        logger.shutdown()


def _cmd_generate_config(args: argparse.Namespace) -> None:
    """Generate OpenClaw diagnostics configuration."""
    cfg = load_config(args.config)

    openclaw_config = {
        "plugins": {
            "allow": ["diagnostics-otel"],
            "entries": {
                "diagnostics-otel": {
                    "enabled": True,
                },
            },
        },
        "diagnostics": {
            "enabled": True,
            "otel": {
                "enabled": True,
                "endpoint": cfg.openclaw.otel_endpoint,
                "protocol": "http/protobuf",
                "serviceName": cfg.openclaw.service_name,
                "traces": cfg.openclaw.traces,
                "metrics": cfg.openclaw.metrics,
                "logs": cfg.openclaw.logs,
                "sampleRate": cfg.openclaw.sample_rate,
                "flushIntervalMs": cfg.openclaw.flush_interval_ms,
            },
        },
        "logging": {
            "level": "debug",
        },
    }

    output = args.output or "openclaw.diagnostics.json"
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as fh:
        json.dump(openclaw_config, fh, indent=2)
    print(f"OpenClaw diagnostics config written to {output}")
    print()
    print("To apply, merge into your ~/.openclaw/openclaw.json or run:")
    print(f"  cp {output} ~/.openclaw/openclaw.json")
    print()
    print("Then enable the plugin:")
    print("  openclaw plugins enable diagnostics-otel")
    print("  openclaw gateway restart")


def _cmd_version(_args: argparse.Namespace) -> None:
    print(f"trace_claw {__version__}")


def main(argv: list[str] | None = None) -> None:
    """Entry point for the trace-claw CLI."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        prog="trace-claw",
        description="Trace and analyze OpenClaw AI assistant workflows",
    )
    parser.add_argument("--config", "-c", default=None, help="Path to trace_claw.yaml")
    sub = parser.add_subparsers(dest="command")

    # collect
    collect_p = sub.add_parser("collect", help="Start system resource collection")
    collect_p.set_defaults(func=_cmd_collect)

    # analyze
    analyze_p = sub.add_parser("analyze", help="Analyze trace data and generate timeline")
    analyze_p.add_argument("--trace-dir", default=None, help="Directory with trace JSONL files")
    analyze_p.add_argument("--no-table", action="store_true", help="Skip rich table output")
    analyze_p.set_defaults(func=_cmd_analyze)

    # generate-config
    gen_p = sub.add_parser("generate-config", help="Generate OpenClaw diagnostics configuration")
    gen_p.add_argument("--output", "-o", default=None, help="Output file path")
    gen_p.set_defaults(func=_cmd_generate_config)

    # log-event
    log_p = sub.add_parser("log-event", help="Log an LLM/tool event to local JSONL file")
    log_p.add_argument("event_type", help="Event type: 'llm', 'tool', or custom type")
    log_p.add_argument("--model", default=None, help="LLM model name (for llm events)")
    log_p.add_argument("--provider", default=None, help="LLM provider (for llm events)")
    log_p.add_argument("--tool-name", default=None, help="Tool name (for tool events)")
    log_p.add_argument("--tokens-input", type=int, default=None, help="Input tokens")
    log_p.add_argument("--tokens-output", type=int, default=None, help="Output tokens")
    log_p.add_argument("--duration-ms", type=float, default=None, help="Duration in milliseconds")
    log_p.add_argument("--cost-usd", type=float, default=None, help="Cost in USD")
    log_p.add_argument("--status", default=None, help="Status (ok or error)")
    log_p.add_argument("--error", default=None, help="Error message")
    log_p.set_defaults(func=_cmd_log_event)

    # version
    ver_p = sub.add_parser("version", help="Print version")
    ver_p.set_defaults(func=_cmd_version)

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
