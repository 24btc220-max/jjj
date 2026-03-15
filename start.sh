#!/bin/bash
set -e

echo ""
echo " ========================================================="
echo "  EXAMGUARD PRO — Starting Backend"
echo " ========================================================="
echo ""

cd "$(dirname "$0")/backend"

# Create venv if it doesn't exist
if [ ! -f "venv/bin/activate" ]; then
    echo " [1/3] Creating virtual environment..."
    python3 -m venv venv
    echo " [2/3] Installing dependencies (takes a few minutes first time)..."
    source venv/bin/activate
    pip install -r requirements.txt
else
    echo " [1/3] Virtual environment found."
    source venv/bin/activate
fi

echo ""
echo " [3/3] Starting FastAPI server on http://localhost:8000"
echo ""
echo " API docs: http://localhost:8000/docs"
echo " Frontend: open frontend/index.html in Chrome or Edge"
echo ""
echo " Press Ctrl+C to stop."
echo " ========================================================="
echo ""

python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
