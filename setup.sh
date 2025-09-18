#!/bin/bash
# Setup script for Streamlit Download Manager

set -e

echo "Setting up Streamlit Download Manager..."

# Update package list
echo "Updating package list..."
sudo apt update

# Install system packages
echo "Installing system packages..."
sudo apt install -y \
    ffmpeg \
    wget \
    curl \
    python3-pip \
    python3-venv \
    python3-dev \
    libffi-dev \
    libssl-dev

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install Python packages
echo "Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

# Install yt-dlp globally (for shell commands)
echo "Installing yt-dlp globally..."
pipx install yt-dlp

echo "Setup completed!"
echo ""
echo "To run the application:"
echo "1. Activate the virtual environment: source venv/bin/activate"
echo "2. Run the app: streamlit run streamlit_download_manager_merged.py"
echo ""
echo "Or run directly: ./venv/bin/streamlit run streamlit_download_manager_merged.py"
