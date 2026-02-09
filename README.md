# trace_claw

A comprehensive tracing tool for monitoring openclaw execution with detailed workflow tracking and system resource monitoring.

## Features

- **Workflow Tracing**: Track the execution flow of openclaw with timestamped events
- **Resource Monitoring**: Monitor CPU, memory, I/O, and thread usage in real-time
- **Statistical Analysis**: Automatic calculation of resource usage statistics
- **Output Capture**: Capture stdout and stderr from openclaw execution
- **Flexible Configuration**: Configurable monitoring intervals and output directories
- **JSON Export**: All trace data exported in structured JSON format for analysis

## Installation

### Prerequisites

- Python 3.6 or higher
- pip package manager

### Install Dependencies

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

Trace an openclaw execution with default settings:

```bash
python trace_claw.py openclaw input.claw
```

### Advanced Options

```bash
# Custom output directory
python trace_claw.py --output ./my_traces openclaw input.claw

# Custom monitoring interval (1 second)
python trace_claw.py --interval 1.0 openclaw input.claw

# Don't capture stdout/stderr (useful for interactive programs)
python trace_claw.py --no-capture openclaw input.claw

# Combine options
python trace_claw.py --output ./traces --interval 0.1 openclaw --verbose input.claw
```

### Command-Line Arguments

- `command`: The openclaw command and arguments to trace (required)
- `-o, --output`: Output directory for trace files (default: `./trace_output`)
- `-i, --interval`: Resource monitoring interval in seconds (default: 0.5)
- `--no-capture`: Skip capturing stdout/stderr from the process

## Output Files

The tracer generates several output files in the specified output directory:

### 1. Workflow Events (`workflow_YYYYMMDD_HHMMSS.json`)

Contains timestamped events tracking the execution flow:

```json
{
  "events": [
    {
      "timestamp": "2026-02-09T09:05:00.123456",
      "event_type": "START",
      "description": "Starting openclaw execution",
      "details": {
        "command": ["openclaw", "input.claw"]
      }
    },
    {
      "timestamp": "2026-02-09T09:05:00.234567",
      "event_type": "LAUNCH",
      "description": "Launching openclaw process"
    },
    {
      "timestamp": "2026-02-09T09:05:00.345678",
      "event_type": "PROCESS_CREATED",
      "description": "Process created with PID 12345",
      "details": {
        "pid": 12345
      }
    }
  ],
  "summary": {
    "total_events": 5,
    "start_time": "2026-02-09T09:05:00.123456",
    "end_time": "2026-02-09T09:05:30.456789"
  }
}
```

### 2. Resource Data (`resources_YYYYMMDD_HHMMSS.json`)

Contains resource usage statistics and raw monitoring data:

```json
{
  "statistics": {
    "total_snapshots": 60,
    "valid_snapshots": 60,
    "duration_seconds": 30.0,
    "cpu": {
      "average": 45.2,
      "max": 98.5,
      "min": 5.1
    },
    "memory_rss_mb": {
      "average": 125.6,
      "max": 156.8,
      "min": 98.2
    },
    "memory_percent": {
      "average": 1.5,
      "max": 1.9,
      "min": 1.2
    },
    "io": {
      "total_read_mb": 25.4,
      "total_write_mb": 12.3,
      "read_operations": 1250,
      "write_operations": 620
    }
  },
  "raw_data": [
    {
      "timestamp": "2026-02-09T09:05:00.500000",
      "cpu_percent": 45.2,
      "memory_rss_mb": 125.6,
      "memory_vms_mb": 450.3,
      "memory_percent": 1.5,
      "num_threads": 4,
      "num_fds": 15,
      "io_read_bytes": 26624000,
      "io_write_bytes": 12902400,
      "io_read_count": 1250,
      "io_write_count": 620
    }
  ]
}
```

### 3. Standard Output (`stdout_YYYYMMDD_HHMMSS.log`)

Captured stdout from openclaw execution.

### 4. Standard Error (`stderr_YYYYMMDD_HHMMSS.log`)

Captured stderr from openclaw execution.

## Resource Metrics

The tracer monitors the following system resources:

### CPU Usage
- Percentage of CPU time used by openclaw process
- Sampled at the specified interval
- Statistics: average, max, min

### Memory Usage
- **RSS (Resident Set Size)**: Physical memory used
- **VMS (Virtual Memory Size)**: Total virtual memory allocated
- **Memory Percent**: Percentage of system memory used
- Statistics: average, max, min for all metrics

### I/O Operations
- **Read Bytes**: Total bytes read from disk
- **Write Bytes**: Total bytes written to disk
- **Read Count**: Number of read operations
- **Write Count**: Number of write operations

### Process Information
- **Thread Count**: Number of active threads
- **File Descriptors**: Number of open file descriptors (Unix)

## Workflow Events

The tracer logs the following workflow events:

1. **START**: Openclaw execution begins
2. **LAUNCH**: Process launch initiated
3. **PROCESS_CREATED**: Process created with PID
4. **PROCESS_EXITED**: Process terminated with exit code
5. **END**: Complete execution finished
6. **INTERRUPTED**: Execution interrupted by user (Ctrl+C)
7. **ERROR**: Error during tracing

## Use Cases

### Performance Analysis
Monitor resource usage to identify performance bottlenecks:
```bash
python trace_claw.py --interval 0.1 openclaw large_input.claw
```

### Memory Leak Detection
Track memory usage over time to detect leaks:
```bash
python trace_claw.py --interval 1.0 openclaw long_running.claw
```

### I/O Profiling
Analyze disk I/O patterns:
```bash
python trace_claw.py openclaw io_intensive.claw
```

### Workflow Documentation
Document the execution flow for debugging:
```bash
python trace_claw.py --output ./debug_traces openclaw problematic.claw
```

## Technical Details

### Architecture

The tracer consists of three main components:

1. **WorkflowTracer**: Logs execution events with timestamps
2. **SystemResourceMonitor**: Monitors resource usage using psutil
3. **OpenClawTracer**: Orchestrates tracing and manages output

### Threading Model

- Main thread: Manages openclaw process execution
- Monitor thread: Samples resource usage at specified intervals
- Output threads: Capture stdout/stderr streams (when enabled)

### Data Collection

Resource snapshots are collected at the specified interval (default: 0.5s):
- Non-blocking I/O for stdout/stderr capture
- Asynchronous resource monitoring
- Minimal overhead on traced process

### Error Handling

- Graceful handling of process termination
- Capture of Ctrl+C interruptions
- Partial data saving on errors
- Informative error messages

## Limitations

- Requires Python 3.6+
- `psutil` library must be installed
- Some metrics may not be available on all platforms
- File descriptor counts not available on Windows
- Root/admin privileges may be required for some metrics

## Troubleshooting

### Process Not Found
If you get a "Process not found" error, the openclaw process may be starting and exiting too quickly. Try increasing the monitoring interval or check if openclaw is installed correctly.

### Permission Denied
Some resource metrics require elevated privileges. Run with sudo/admin if needed:
```bash
sudo python trace_claw.py openclaw input.claw
```

### High Overhead
If monitoring overhead is too high, increase the interval:
```bash
python trace_claw.py --interval 2.0 openclaw input.claw
```

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

This project is open source and available for use with openclaw tracing needs.