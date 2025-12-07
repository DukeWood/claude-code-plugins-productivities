#!/bin/bash
# Quick test runner for encryption module

cd "$(dirname "$0")"

echo "=== Running Encryption Tests (TDD) ==="
echo

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "ERROR: pytest not installed"
    echo "Install with: pip3 install -r requirements-test.txt"
    exit 1
fi

# Run tests with verbose output
python3 -m pytest tests/test_encryption.py -v --tb=short

echo
echo "=== Test run complete ==="
