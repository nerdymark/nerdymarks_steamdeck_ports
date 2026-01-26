#!/bin/bash
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
cd "$SCRIPT_DIR/gamecom-downloader"
if [ ! -f "venv/bin/python3" ]; then
    echo "First run - setting up Python environment..."
    python3 -m venv venv
    ./venv/bin/pip install pygame
fi
./venv/bin/python3 gamecom_downloader.py
