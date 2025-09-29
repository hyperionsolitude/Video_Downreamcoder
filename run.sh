#!/bin/bash
# Generic launcher for Video Downstreamcoder that prefers a local virtualenv

set -euo pipefail

echo "🎬 Starting Video Downstreamcoder..."

# Check if Python is available
if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

# Determine venv paths (Unix-like default created by setup_cross_platform.sh)
VENV_DIR="venv"
VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# If venv exists, use it. Otherwise, try to create it briefly; if creation fails, guide the user
if [ -x "$VENV_PY" ]; then
    echo "🐍 Using existing virtual environment at $VENV_DIR"
else
    echo "🐍 No virtual environment found. Attempting to create one at $VENV_DIR..."
    if python3 -m venv "$VENV_DIR" 2>/dev/null; then
        echo "✅ Virtual environment created."
    else
        echo "⚠️ Could not create a virtual environment (python3-venv may be missing)."
        echo "👉 Please run ./setup_cross_platform.sh first, then re-run ./run.sh"
        exit 1
    fi
fi

# Ensure pip inside venv is available and install dependencies inside venv to avoid PEP 668 issues
echo "📦 Ensuring dependencies inside virtual environment..."
"$VENV_PY" -m pip install --upgrade pip >/dev/null 2>&1 || true
"$VENV_PIP" install -r requirements.txt || {
  echo "❌ Failed to install Python dependencies inside venv."
  echo "👉 Try running: ./setup_cross_platform.sh"
  exit 1
}

# Start the application using the venv's Python/Streamlit
echo "🚀 Launching application..."
"$VENV_PY" -m streamlit run streamlit_download_manager_merged.py
