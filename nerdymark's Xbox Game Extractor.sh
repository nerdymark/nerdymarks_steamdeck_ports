#!/bin/bash
# nerdymark's Xbox Game Extractor for ES-DE
# Uses pygame for fullscreen controller-friendly UI

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
cd "$SCRIPT_DIR/xbox-downloader"

# Create venv and install pygame if needed (first run)
if [ ! -f "venv/bin/python3" ]; then
    echo "First run - setting up Python environment..."
    python3 -m venv venv
    ./venv/bin/pip install pygame
fi

# Run the extractor
./venv/bin/python3 xbox_extractor.py
