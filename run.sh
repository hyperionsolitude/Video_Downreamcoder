#!/bin/bash
# Simple launch script for Video Downstreamcoder

echo "🎬 Starting Video Downstreamcoder..."

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.9 or higher."
    exit 1
fi

# Check if requirements are installed
if ! python3 -c "import streamlit, yt_dlp" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip3 install -r requirements.txt
fi

# Start the application
echo "🚀 Launching application..."
streamlit run streamlit_download_manager_merged.py
