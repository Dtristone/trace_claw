# Quick Start Guide for trace_claw

## Installation

```bash
# Clone the repository
git clone https://github.com/Dtristone/trace_claw.git
cd trace_claw

# Install dependencies
pip install -r requirements.txt
```

## Basic Usage

### 1. Trace OpenClaw Execution

The simplest way to trace an openclaw process:

```bash
python3 trace_claw.py openclaw input.claw
```

This will:
- Start monitoring before openclaw launches
- Track all workflow events with timestamps
- Monitor CPU, memory, I/O, and thread usage
- Save all data to `./trace_output/` directory

### 2. View Trace Results

After tracing completes, view the results:

```bash
python3 visualize_trace.py
```

For visual charts:

```bash
python3 visualize_trace.py --charts
```

### 3. Test with Simulator

Test the tracer using the included simulator:

```bash
# Run the simulator with tracing
python3 trace_claw.py python3 example_openclaw_simulator.py

# View the results
python3 visualize_trace.py --charts
```

## Advanced Usage

### Custom Output Directory

```bash
python3 trace_claw.py --output ./my_analysis openclaw input.claw
```

### Adjust Monitoring Frequency

For high-frequency monitoring (every 0.1 seconds):

```bash
python3 trace_claw.py --interval 0.1 openclaw input.claw
```

For low-frequency monitoring (every 2 seconds):

```bash
python3 trace_claw.py --interval 2.0 openclaw input.claw
```

### Skip Output Capture

If openclaw is interactive or you don't need output:

```bash
python3 trace_claw.py --no-capture openclaw input.claw
```

### Pass Arguments to OpenClaw

```bash
python3 trace_claw.py openclaw --verbose --config myconfig.ini input.claw
```

## Understanding the Output

### Trace Files

After tracing, you'll find these files in the output directory:

1. **workflow_TIMESTAMP.json** - Event timeline
2. **resources_TIMESTAMP.json** - Resource usage data and statistics
3. **stdout_TIMESTAMP.log** - Standard output (if captured)
4. **stderr_TIMESTAMP.log** - Standard error (if captured)

### Resource Metrics

The tracer collects these metrics:

- **CPU Usage**: Percentage of CPU time
- **Memory RSS**: Physical memory used (in MB)
- **Memory VMS**: Virtual memory size (in MB)
- **I/O Read/Write**: Disk operations (bytes and count)
- **Thread Count**: Number of active threads
- **File Descriptors**: Open file handles

### Statistics Calculated

For each metric, the tracer calculates:
- Average value
- Maximum value
- Minimum value
- Total duration

## Interpreting Results

### High CPU Usage

If average CPU is > 80%:
- OpenClaw is CPU-bound
- Consider optimizing computational algorithms
- Look for parallelization opportunities

### Memory Growth

If memory increases steadily:
- Potential memory leak
- Check for unbounded data structures
- Review resource cleanup

### I/O Bottlenecks

If I/O operations are high:
- Consider buffering strategies
- Review file access patterns
- Use async I/O if possible

## Troubleshooting

### "Process not found" error

OpenClaw may be exiting too quickly. Check:
1. Is openclaw installed and in PATH?
2. Are input files valid?
3. Try running openclaw directly first

### High monitoring overhead

If tracing impacts performance:
1. Increase interval: `--interval 1.0` or higher
2. Use `--no-capture` to skip output capture
3. Monitor on a separate machine if possible

### Permission denied

Some metrics require elevated privileges:

```bash
sudo python3 trace_claw.py openclaw input.claw
```

## Examples

### Performance Profiling

```bash
# High-frequency monitoring for detailed profiling
python3 trace_claw.py --interval 0.1 --output ./profile openclaw input.claw
python3 visualize_trace.py --charts ./profile
```

### Long-Running Process

```bash
# Low-frequency monitoring for long runs
python3 trace_claw.py --interval 5.0 --output ./longrun openclaw large.claw
```

### Production Monitoring

```bash
# Minimal overhead monitoring
python3 trace_claw.py --interval 2.0 --no-capture --output ./prod openclaw prod.claw
```

## Integration Tips

### Automated Testing

```bash
#!/bin/bash
for input in test_cases/*.claw; do
    echo "Testing $input"
    python3 trace_claw.py --output "./traces/$(basename $input)" openclaw "$input"
done
```

### Continuous Monitoring

```bash
# Monitor multiple runs and compare
for i in {1..10}; do
    python3 trace_claw.py --output "./run_$i" openclaw input.claw
done
```

### CI/CD Integration

Add to your CI pipeline:

```yaml
- name: Profile OpenClaw
  run: |
    pip install -r requirements.txt
    python3 trace_claw.py openclaw test_input.claw
    python3 visualize_trace.py --charts > profile_report.txt
```

## Best Practices

1. **Choose appropriate interval**: Balance between detail and overhead
2. **Use consistent output directories**: Organize traces by date/test
3. **Archive important traces**: Save traces for later comparison
4. **Compare baselines**: Track performance changes over time
5. **Document findings**: Add notes about unusual patterns

## Getting Help

For issues or questions:
1. Check README.md for detailed documentation
2. Review example_openclaw_simulator.py for usage patterns
3. Run test_trace.sh to verify installation
4. Open an issue on GitHub with trace output

## Next Steps

- Review the full README.md for complete documentation
- Explore the JSON output for programmatic analysis
- Integrate tracing into your development workflow
- Share findings with the OpenClaw community
