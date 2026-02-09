#!/usr/bin/env python3
"""
OpenClaw Tracer - A comprehensive tracing tool for openclaw execution
Monitors detailed workflow and system resource usage during openclaw execution.
"""

import psutil
import time
import json
import sys
import subprocess
import os
import signal
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import threading
import argparse


class SystemResourceMonitor:
    """Monitor system resources used by openclaw process"""
    
    def __init__(self, pid: int, interval: float = 0.5):
        self.pid = pid
        self.interval = interval
        self.monitoring = False
        self.data: List[Dict[str, Any]] = []
        self.process: Optional[psutil.Process] = None
        self.monitor_thread: Optional[threading.Thread] = None
        
    def start(self):
        """Start resource monitoring"""
        try:
            self.process = psutil.Process(self.pid)
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            print(f"[ResourceMonitor] Started monitoring PID {self.pid}")
        except psutil.NoSuchProcess:
            print(f"[ResourceMonitor] Error: Process {self.pid} not found")
            
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                if self.process and self.process.is_running():
                    snapshot = self._capture_snapshot()
                    self.data.append(snapshot)
                else:
                    print("[ResourceMonitor] Process no longer running")
                    self.monitoring = False
                    break
                time.sleep(self.interval)
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                print(f"[ResourceMonitor] Monitoring stopped: {e}")
                self.monitoring = False
                break
                
    def _capture_snapshot(self) -> Dict[str, Any]:
        """Capture a snapshot of resource usage"""
        timestamp = datetime.now().isoformat()
        
        try:
            cpu_percent = self.process.cpu_percent(interval=0.1)
            memory_info = self.process.memory_info()
            memory_percent = self.process.memory_percent()
            
            # Get I/O stats if available
            io_counters = None
            try:
                io_counters = self.process.io_counters()
            except (AttributeError, psutil.AccessDenied):
                pass
                
            # Get thread count
            num_threads = self.process.num_threads()
            
            # Get file descriptors/handles
            try:
                num_fds = self.process.num_fds() if hasattr(self.process, 'num_fds') else None
            except (AttributeError, psutil.AccessDenied):
                num_fds = None
                
            snapshot = {
                'timestamp': timestamp,
                'cpu_percent': cpu_percent,
                'memory_rss_mb': memory_info.rss / (1024 * 1024),
                'memory_vms_mb': memory_info.vms / (1024 * 1024),
                'memory_percent': memory_percent,
                'num_threads': num_threads,
                'num_fds': num_fds,
            }
            
            if io_counters:
                snapshot.update({
                    'io_read_bytes': io_counters.read_bytes,
                    'io_write_bytes': io_counters.write_bytes,
                    'io_read_count': io_counters.read_count,
                    'io_write_count': io_counters.write_count,
                })
                
            return snapshot
            
        except Exception as e:
            return {
                'timestamp': timestamp,
                'error': str(e)
            }
            
    def stop(self):
        """Stop monitoring"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
        print("[ResourceMonitor] Monitoring stopped")
        
    def get_statistics(self) -> Dict[str, Any]:
        """Calculate statistics from collected data"""
        if not self.data:
            return {}
            
        valid_data = [d for d in self.data if 'error' not in d]
        if not valid_data:
            return {'error': 'No valid data collected'}
            
        cpu_values = [d['cpu_percent'] for d in valid_data]
        memory_rss_values = [d['memory_rss_mb'] for d in valid_data]
        memory_percent_values = [d['memory_percent'] for d in valid_data]
        
        stats = {
            'total_snapshots': len(self.data),
            'valid_snapshots': len(valid_data),
            'duration_seconds': len(valid_data) * self.interval,
            'cpu': {
                'average': sum(cpu_values) / len(cpu_values),
                'max': max(cpu_values),
                'min': min(cpu_values),
            },
            'memory_rss_mb': {
                'average': sum(memory_rss_values) / len(memory_rss_values),
                'max': max(memory_rss_values),
                'min': min(memory_rss_values),
            },
            'memory_percent': {
                'average': sum(memory_percent_values) / len(memory_percent_values),
                'max': max(memory_percent_values),
                'min': min(memory_percent_values),
            },
        }
        
        # Add I/O stats if available
        io_data = [d for d in valid_data if 'io_read_bytes' in d]
        if io_data:
            stats['io'] = {
                'total_read_mb': io_data[-1]['io_read_bytes'] / (1024 * 1024),
                'total_write_mb': io_data[-1]['io_write_bytes'] / (1024 * 1024),
                'read_operations': io_data[-1]['io_read_count'],
                'write_operations': io_data[-1]['io_write_count'],
            }
            
        return stats


class WorkflowTracer:
    """Trace the workflow of openclaw execution"""
    
    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        
    def log_event(self, event_type: str, description: str, details: Optional[Dict] = None):
        """Log a workflow event"""
        timestamp = datetime.now().isoformat()
        event = {
            'timestamp': timestamp,
            'event_type': event_type,
            'description': description,
        }
        if details:
            event['details'] = details
        self.events.append(event)
        print(f"[Workflow] {event_type}: {description}")
        
    def start_workflow(self, command: List[str]):
        """Mark the start of workflow"""
        self.start_time = datetime.now()
        self.log_event('START', f'Starting openclaw execution', {'command': command})
        
    def end_workflow(self, exit_code: int):
        """Mark the end of workflow"""
        self.end_time = datetime.now()
        duration = (self.end_time - self.start_time).total_seconds() if self.start_time else 0
        self.log_event('END', f'Openclaw execution finished', {
            'exit_code': exit_code,
            'duration_seconds': duration
        })


class OpenClawTracer:
    """Main tracer for openclaw execution"""
    
    def __init__(self, output_dir: str = './trace_output', monitor_interval: float = 0.5):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.monitor_interval = monitor_interval
        
        self.workflow_tracer = WorkflowTracer()
        self.resource_monitor: Optional[SystemResourceMonitor] = None
        
        self.process: Optional[subprocess.Popen] = None
        self.stdout_data: List[str] = []
        self.stderr_data: List[str] = []
        
    def trace_openclaw(self, openclaw_command: List[str], capture_output: bool = True):
        """Trace openclaw execution with workflow and resource monitoring"""
        print("=" * 80)
        print("OpenClaw Tracer")
        print("=" * 80)
        print(f"Command: {' '.join(openclaw_command)}")
        print(f"Output directory: {self.output_dir}")
        print(f"Monitor interval: {self.monitor_interval}s")
        print("=" * 80)
        
        # Start workflow tracing
        self.workflow_tracer.start_workflow(openclaw_command)
        
        try:
            # Launch openclaw process
            self.workflow_tracer.log_event('LAUNCH', 'Launching openclaw process')
            
            if capture_output:
                self.process = subprocess.Popen(
                    openclaw_command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
            else:
                self.process = subprocess.Popen(openclaw_command)
                
            pid = self.process.pid
            self.workflow_tracer.log_event('PROCESS_CREATED', f'Process created with PID {pid}', {'pid': pid})
            
            # Start resource monitoring
            self.resource_monitor = SystemResourceMonitor(pid, self.monitor_interval)
            self.resource_monitor.start()
            
            # Monitor process execution
            if capture_output and self.process.stdout and self.process.stderr:
                self._monitor_output()
            else:
                # Just wait for completion
                self.process.wait()
                
            exit_code = self.process.returncode
            self.workflow_tracer.log_event('PROCESS_EXITED', f'Process exited with code {exit_code}', {'exit_code': exit_code})
            
            # Stop resource monitoring
            if self.resource_monitor:
                self.resource_monitor.stop()
                
            # Finalize workflow
            self.workflow_tracer.end_workflow(exit_code)
            
            # Save results
            self._save_results()
            
            print("=" * 80)
            print("Tracing complete!")
            print(f"Results saved to: {self.output_dir}")
            print("=" * 80)
            
            return exit_code
            
        except KeyboardInterrupt:
            print("\n[Tracer] Interrupted by user")
            self.workflow_tracer.log_event('INTERRUPTED', 'Execution interrupted by user')
            if self.process:
                self.process.terminate()
                self.process.wait(timeout=5)
            if self.resource_monitor:
                self.resource_monitor.stop()
            self._save_results()
            return -1
            
        except Exception as e:
            print(f"[Tracer] Error: {e}")
            self.workflow_tracer.log_event('ERROR', f'Tracing error: {str(e)}')
            if self.resource_monitor:
                self.resource_monitor.stop()
            self._save_results()
            raise
            
    def _monitor_output(self):
        """Monitor stdout and stderr from the process"""
        def read_stream(stream, data_list, stream_name):
            for line in stream:
                data_list.append(line)
                print(f"[{stream_name}] {line}", end='')
                
        import threading
        stdout_thread = threading.Thread(
            target=read_stream, 
            args=(self.process.stdout, self.stdout_data, 'stdout'),
            daemon=True
        )
        stderr_thread = threading.Thread(
            target=read_stream,
            args=(self.process.stderr, self.stderr_data, 'stderr'),
            daemon=True
        )
        
        stdout_thread.start()
        stderr_thread.start()
        
        self.process.wait()
        
        stdout_thread.join(timeout=2.0)
        stderr_thread.join(timeout=2.0)
        
    def _save_results(self):
        """Save all tracing results to files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save workflow events
        workflow_file = self.output_dir / f"workflow_{timestamp}.json"
        with open(workflow_file, 'w') as f:
            json.dump({
                'events': self.workflow_tracer.events,
                'summary': {
                    'total_events': len(self.workflow_tracer.events),
                    'start_time': self.workflow_tracer.start_time.isoformat() if self.workflow_tracer.start_time else None,
                    'end_time': self.workflow_tracer.end_time.isoformat() if self.workflow_tracer.end_time else None,
                }
            }, f, indent=2)
        print(f"[Tracer] Workflow saved to: {workflow_file}")
        
        # Save resource monitoring data
        if self.resource_monitor:
            resource_file = self.output_dir / f"resources_{timestamp}.json"
            stats = self.resource_monitor.get_statistics()
            with open(resource_file, 'w') as f:
                json.dump({
                    'statistics': stats,
                    'raw_data': self.resource_monitor.data,
                }, f, indent=2)
            print(f"[Tracer] Resource data saved to: {resource_file}")
            
            # Print summary statistics
            self._print_resource_summary(stats)
            
        # Save stdout/stderr if captured
        if self.stdout_data:
            stdout_file = self.output_dir / f"stdout_{timestamp}.log"
            with open(stdout_file, 'w') as f:
                f.writelines(self.stdout_data)
            print(f"[Tracer] Stdout saved to: {stdout_file}")
            
        if self.stderr_data:
            stderr_file = self.output_dir / f"stderr_{timestamp}.log"
            with open(stderr_file, 'w') as f:
                f.writelines(self.stderr_data)
            print(f"[Tracer] Stderr saved to: {stderr_file}")
            
    def _print_resource_summary(self, stats: Dict[str, Any]):
        """Print a summary of resource usage"""
        if 'error' in stats:
            print(f"[Summary] Error: {stats['error']}")
            return
            
        print("\n" + "=" * 80)
        print("RESOURCE USAGE SUMMARY")
        print("=" * 80)
        print(f"Duration: {stats.get('duration_seconds', 0):.2f} seconds")
        print(f"Snapshots: {stats.get('valid_snapshots', 0)}/{stats.get('total_snapshots', 0)}")
        
        if 'cpu' in stats:
            cpu = stats['cpu']
            print(f"\nCPU Usage:")
            print(f"  Average: {cpu['average']:.2f}%")
            print(f"  Max: {cpu['max']:.2f}%")
            print(f"  Min: {cpu['min']:.2f}%")
            
        if 'memory_rss_mb' in stats:
            mem = stats['memory_rss_mb']
            mem_pct = stats['memory_percent']
            print(f"\nMemory Usage (RSS):")
            print(f"  Average: {mem['average']:.2f} MB ({mem_pct['average']:.2f}%)")
            print(f"  Max: {mem['max']:.2f} MB ({mem_pct['max']:.2f}%)")
            print(f"  Min: {mem['min']:.2f} MB ({mem_pct['min']:.2f}%)")
            
        if 'io' in stats:
            io = stats['io']
            print(f"\nI/O Operations:")
            print(f"  Total Read: {io['total_read_mb']:.2f} MB ({io['read_operations']} operations)")
            print(f"  Total Write: {io['total_write_mb']:.2f} MB ({io['write_operations']} operations)")
            
        print("=" * 80)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Trace openclaw execution with detailed workflow and resource monitoring',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Trace openclaw with default settings
  python trace_claw.py openclaw input.claw
  
  # Trace with custom output directory and monitor interval
  python trace_claw.py --output ./my_traces --interval 1.0 openclaw input.claw
  
  # Trace without capturing stdout/stderr
  python trace_claw.py --no-capture openclaw input.claw
        """
    )
    
    parser.add_argument('command', nargs='+', help='The openclaw command to execute')
    parser.add_argument('-o', '--output', default='./trace_output',
                       help='Output directory for trace files (default: ./trace_output)')
    parser.add_argument('-i', '--interval', type=float, default=0.5,
                       help='Resource monitoring interval in seconds (default: 0.5)')
    parser.add_argument('--no-capture', action='store_true',
                       help='Do not capture stdout/stderr')
    
    args = parser.parse_args()
    
    tracer = OpenClawTracer(output_dir=args.output, monitor_interval=args.interval)
    exit_code = tracer.trace_openclaw(args.command, capture_output=not args.no_capture)
    
    sys.exit(exit_code if exit_code is not None else 0)


if __name__ == '__main__':
    main()
