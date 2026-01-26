#!/bin/bash
# nerdymark's DOS Setup Tool for ES-DE
# https://nerdymark.com

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
cd "$SCRIPT_DIR/nerdymarks-dos_setup"

# Create venv and install pygame if needed (first run)
if [ ! -f "venv/bin/python3" ]; then
    echo "First run - setting up Python environment..."
    python3 -m venv venv
    ./venv/bin/pip install pygame
fi

# Run the DOS setup tool
./venv/bin/python3 dos_setup.py
