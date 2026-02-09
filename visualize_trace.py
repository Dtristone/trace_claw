#!/usr/bin/env python3
"""
Visualization tool for trace_claw output.
Generates reports and visualizations from trace data.
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime


def load_trace_files(directory: str):
    """Load the most recent trace files from directory"""
    trace_dir = Path(directory)
    
    if not trace_dir.exists():
        print(f"Error: Directory {directory} does not exist")
        return None, None
    
    # Find most recent files
    workflow_files = sorted(trace_dir.glob("workflow_*.json"))
    resource_files = sorted(trace_dir.glob("resources_*.json"))
    
    if not workflow_files or not resource_files:
        print("Error: No trace files found in directory")
        return None, None
    
    workflow_file = workflow_files[-1]
    resource_file = resource_files[-1]
    
    print(f"Loading workflow: {workflow_file.name}")
    print(f"Loading resources: {resource_file.name}")
    
    with open(workflow_file) as f:
        workflow_data = json.load(f)
    
    with open(resource_file) as f:
        resource_data = json.load(f)
    
    return workflow_data, resource_data


def print_workflow_report(workflow_data):
    """Print a formatted workflow report"""
    print("\n" + "=" * 80)
    print("WORKFLOW REPORT")
    print("=" * 80)
    
    summary = workflow_data.get('summary', {})
    events = workflow_data.get('events', [])
    
    print(f"Total Events: {summary.get('total_events', 0)}")
    
    if summary.get('start_time') and summary.get('end_time'):
        start = datetime.fromisoformat(summary['start_time'])
        end = datetime.fromisoformat(summary['end_time'])
        duration = (end - start).total_seconds()
        print(f"Duration: {duration:.2f} seconds")
    
    print(f"\nEvent Timeline:")
    print("-" * 80)
    
    for event in events:
        timestamp = event.get('timestamp', '')
        event_type = event.get('event_type', 'UNKNOWN')
        description = event.get('description', '')
        
        # Format timestamp to show only time
        try:
            dt = datetime.fromisoformat(timestamp)
            time_str = dt.strftime('%H:%M:%S.%f')[:-3]
        except:
            time_str = timestamp
        
        print(f"[{time_str}] {event_type:20s} {description}")
        
        if 'details' in event:
            for key, value in event['details'].items():
                print(f"{'':35s} {key}: {value}")
    
    print("=" * 80)


def print_resource_report(resource_data):
    """Print a formatted resource usage report"""
    print("\n" + "=" * 80)
    print("RESOURCE USAGE REPORT")
    print("=" * 80)
    
    stats = resource_data.get('statistics', {})
    
    if 'error' in stats:
        print(f"Error: {stats['error']}")
        return
    
    print(f"Duration: {stats.get('duration_seconds', 0):.2f} seconds")
    print(f"Snapshots: {stats.get('valid_snapshots', 0)}/{stats.get('total_snapshots', 0)}")
    
    # CPU Report
    if 'cpu' in stats:
        print("\n" + "-" * 80)
        print("CPU USAGE")
        print("-" * 80)
        cpu = stats['cpu']
        print(f"Average: {cpu['average']:>8.2f}%")
        print(f"Maximum: {cpu['max']:>8.2f}%")
        print(f"Minimum: {cpu['min']:>8.2f}%")
    
    # Memory Report
    if 'memory_rss_mb' in stats:
        print("\n" + "-" * 80)
        print("MEMORY USAGE")
        print("-" * 80)
        mem_rss = stats['memory_rss_mb']
        mem_pct = stats['memory_percent']
        print(f"Average RSS: {mem_rss['average']:>8.2f} MB ({mem_pct['average']:>6.2f}%)")
        print(f"Maximum RSS: {mem_rss['max']:>8.2f} MB ({mem_pct['max']:>6.2f}%)")
        print(f"Minimum RSS: {mem_rss['min']:>8.2f} MB ({mem_pct['min']:>6.2f}%)")
    
    # I/O Report
    if 'io' in stats:
        print("\n" + "-" * 80)
        print("I/O OPERATIONS")
        print("-" * 80)
        io = stats['io']
        print(f"Total Read:  {io['total_read_mb']:>8.2f} MB ({io['read_operations']:>6d} operations)")
        print(f"Total Write: {io['total_write_mb']:>8.2f} MB ({io['write_operations']:>6d} operations)")
        
        if stats.get('duration_seconds', 0) > 0:
            duration = stats['duration_seconds']
            read_rate = io['total_read_mb'] / duration
            write_rate = io['total_write_mb'] / duration
            print(f"Read Rate:   {read_rate:>8.2f} MB/s")
            print(f"Write Rate:  {write_rate:>8.2f} MB/s")
    
    print("=" * 80)


def generate_ascii_chart(data, width=60, height=10):
    """Generate a simple ASCII chart from data"""
    if not data:
        return "No data available"
    
    min_val = min(data)
    max_val = max(data)
    range_val = max_val - min_val if max_val > min_val else 1
    
    # Normalize data to chart height
    normalized = [(v - min_val) / range_val * (height - 1) for v in data]
    
    # Build chart
    chart = []
    for row in range(height - 1, -1, -1):
        line = ""
        for val in normalized:
            if val >= row:
                line += "█"
            else:
                line += " "
        # Add y-axis label
        y_val = min_val + (row / (height - 1)) * range_val
        chart.append(f"{y_val:>8.1f} │{line}")
    
    # Add x-axis
    chart.append("         └" + "─" * len(normalized))
    
    return "\n".join(chart)


def print_resource_charts(resource_data):
    """Print ASCII charts of resource usage"""
    raw_data = resource_data.get('raw_data', [])
    
    if not raw_data:
        print("No raw data available for charts")
        return
    
    # Extract time series data
    cpu_data = [d.get('cpu_percent', 0) for d in raw_data if 'error' not in d]
    memory_data = [d.get('memory_rss_mb', 0) for d in raw_data if 'error' not in d]
    
    print("\n" + "=" * 80)
    print("CPU USAGE OVER TIME (%)")
    print("=" * 80)
    print(generate_ascii_chart(cpu_data))
    
    print("\n" + "=" * 80)
    print("MEMORY USAGE OVER TIME (MB)")
    print("=" * 80)
    print(generate_ascii_chart(memory_data))
    
    print("=" * 80)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Visualize and report on trace_claw output'
    )
    
    parser.add_argument('directory', nargs='?', default='./trace_output',
                       help='Directory containing trace files (default: ./trace_output)')
    parser.add_argument('--workflow-only', action='store_true',
                       help='Show only workflow report')
    parser.add_argument('--resources-only', action='store_true',
                       help='Show only resource report')
    parser.add_argument('--charts', action='store_true',
                       help='Include ASCII charts of resource usage')
    
    args = parser.parse_args()
    
    # Load trace files
    workflow_data, resource_data = load_trace_files(args.directory)
    
    if not workflow_data and not resource_data:
        sys.exit(1)
    
    # Print reports
    if not args.resources_only and workflow_data:
        print_workflow_report(workflow_data)
    
    if not args.workflow_only and resource_data:
        print_resource_report(resource_data)
        
        if args.charts:
            print_resource_charts(resource_data)
    
    print()


if __name__ == '__main__':
    main()
