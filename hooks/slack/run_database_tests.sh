#!/bin/bash
# Test runner for database layer
# Run with: ./run_database_tests.sh

cd "$(dirname "$0")"

echo "Running database tests..."
python3 -m pytest tests/test_database.py -v --tb=short

echo ""
echo "Running with coverage..."
python3 -m pytest tests/test_database.py --cov=lib/database --cov-report=term-missing
