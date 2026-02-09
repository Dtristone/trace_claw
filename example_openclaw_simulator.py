#!/usr/bin/env python3
"""
Example usage of trace_claw for testing purposes.
This creates a simple test program that simulates openclaw-like behavior.
"""

import time
import sys
import random


def simulate_openclaw():
    """Simulate openclaw execution with various operations"""
    
    print("OpenClaw Simulator Starting...")
    print("=" * 60)
    
    # Simulate initialization
    print("[Phase 1] Initialization")
    time.sleep(0.5)
    print("  - Loading configuration")
    time.sleep(0.3)
    print("  - Initializing data structures")
    time.sleep(0.2)
    
    # Simulate computation phases
    print("\n[Phase 2] Computation")
    for i in range(5):
        print(f"  - Processing iteration {i+1}/5")
        # Allocate some memory
        data = [random.random() for _ in range(100000)]
        # Do some computation
        result = sum(data) / len(data)
        time.sleep(0.5)
        print(f"    Result: {result:.6f}")
    
    # Simulate I/O operations
    print("\n[Phase 3] I/O Operations")
    print("  - Writing results to disk")
    with open('/tmp/openclaw_output.txt', 'w') as f:
        for i in range(1000):
            f.write(f"Line {i}: Some output data\n")
    time.sleep(0.3)
    
    print("  - Reading configuration")
    time.sleep(0.2)
    
    # Simulate cleanup
    print("\n[Phase 4] Cleanup")
    time.sleep(0.3)
    print("  - Releasing resources")
    time.sleep(0.2)
    
    print("\n" + "=" * 60)
    print("OpenClaw Simulator Complete!")
    
    return 0


if __name__ == '__main__':
    try:
        exit_code = simulate_openclaw()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
