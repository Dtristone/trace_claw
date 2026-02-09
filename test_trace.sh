#!/bin/bash
# Test script to validate trace_claw functionality

set -e

echo "=================================="
echo "Testing trace_claw Implementation"
echo "=================================="

# Check Python version
echo -e "\n[1] Checking Python version..."
python3 --version

# Install dependencies
echo -e "\n[2] Installing dependencies..."
pip install -q -r requirements.txt

# Test 1: Basic functionality with simulator
echo -e "\n[3] Testing basic tracing with simulator..."
python3 trace_claw.py --output ./test_trace_1 --interval 0.2 python3 example_openclaw_simulator.py

# Verify output files were created
echo -e "\n[4] Verifying output files..."
if [ -d "./test_trace_1" ]; then
    echo "✓ Output directory created"
    ls -lh ./test_trace_1/
    
    workflow_files=$(find ./test_trace_1 -name "workflow_*.json" | wc -l)
    resource_files=$(find ./test_trace_1 -name "resources_*.json" | wc -l)
    
    if [ "$workflow_files" -gt 0 ]; then
        echo "✓ Workflow file created"
    else
        echo "✗ Workflow file NOT created"
        exit 1
    fi
    
    if [ "$resource_files" -gt 0 ]; then
        echo "✓ Resource file created"
    else
        echo "✗ Resource file NOT created"
        exit 1
    fi
else
    echo "✗ Output directory NOT created"
    exit 1
fi

# Test 2: Visualization
echo -e "\n[5] Testing visualization..."
python3 visualize_trace.py ./test_trace_1

# Test 3: Charts
echo -e "\n[6] Testing visualization with charts..."
python3 visualize_trace.py --charts ./test_trace_1

# Test 4: No capture mode
echo -e "\n[7] Testing no-capture mode..."
python3 trace_claw.py --output ./test_trace_2 --no-capture python3 example_openclaw_simulator.py

# Test 5: Validate JSON structure
echo -e "\n[8] Validating JSON structure..."
python3 -c "
import json
import sys
from pathlib import Path

workflow_file = sorted(Path('./test_trace_1').glob('workflow_*.json'))[-1]
resource_file = sorted(Path('./test_trace_1').glob('resources_*.json'))[-1]

with open(workflow_file) as f:
    workflow = json.load(f)
    assert 'events' in workflow, 'Missing events in workflow'
    assert 'summary' in workflow, 'Missing summary in workflow'
    print('✓ Workflow JSON structure valid')

with open(resource_file) as f:
    resources = json.load(f)
    assert 'statistics' in resources, 'Missing statistics in resources'
    assert 'raw_data' in resources, 'Missing raw_data in resources'
    print('✓ Resource JSON structure valid')
"

# Cleanup
echo -e "\n[9] Cleaning up test files..."
rm -rf ./test_trace_1 ./test_trace_2

echo -e "\n=================================="
echo "All tests passed successfully! ✓"
echo "=================================="
