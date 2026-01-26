#!/bin/bash
# nerdymark's MAME Romset Repairer for ES-DE
# Browse, launch, and repair MAME ROMs

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
cd "$SCRIPT_DIR/mame-repair"

# Create venv and install pygame if needed (first run)
if [ ! -f "venv/bin/python3" ]; then
    echo "First run - setting up Python environment..."
    python3 -m venv venv
    ./venv/bin/pip install pygame
fi

# Run the repair tool
./venv/bin/python3 mame_repair.py
