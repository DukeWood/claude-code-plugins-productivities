#!/bin/bash
# Run handler tests
cd "$(dirname "$0")"
python3 -m pytest tests/test_handlers.py -v --tb=short
