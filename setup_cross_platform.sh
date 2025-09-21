#!/bin/bash
# Cross-platform setup script for Video Downstreamcoder
# Supports macOS, Linux (Ubuntu/Debian, Fedora/RHEL/CentOS, Arch), and Windows

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_info "🚀 Setting up Video Downstreamcoder..."

# Detect platform
if [[ "$OSTYPE" == "darwin"* ]]; then
    PLATFORM="macos"
    echo "🍎 Detected macOS"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    PLATFORM="linux"
    echo "🐧 Detected Linux"
elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
    PLATFORM="windows"
    echo "🪟 Detected Windows"
else
    echo "❌ Unsupported platform: $OSTYPE"
    exit 1
fi

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to install Homebrew on macOS
install_homebrew() {
    if ! command_exists brew; then
        echo "📦 Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        
        # Add Homebrew to PATH for Apple Silicon Macs
        if [[ $(uname -m) == "arm64" ]]; then
            echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi
    else
        echo "✅ Homebrew already installed"
    fi
}

# Function to install system packages
install_system_packages() {
    case $PLATFORM in
        "macos")
            install_homebrew
            echo "📦 Installing system packages via Homebrew..."
            brew install ffmpeg wget curl python3
            ;;
        "linux")
            echo "📦 Installing system packages..."
            if command_exists apt; then
                sudo apt update
                sudo apt install -y ffmpeg wget curl python3-pip python3-venv python3-dev libffi-dev libssl-dev
            elif command_exists dnf; then
                sudo dnf install -y ffmpeg wget curl python3-pip python3-venv python3-devel libffi-devel openssl-devel
            elif command_exists pacman; then
                sudo pacman -S --noconfirm ffmpeg wget curl python-pip python-virtualenv
            else
                echo "❌ Unsupported package manager. Please install ffmpeg, wget, curl, and python3 manually."
                exit 1
            fi
            ;;
        "windows")
            if ! command_exists choco; then
                echo "❌ Chocolatey not found. Please install it from https://chocolatey.org/install"
                exit 1
            fi
            echo "📦 Installing system packages via Chocolatey..."
            choco install -y ffmpeg wget curl python3
            ;;
    esac
}

# Function to create virtual environment
create_venv() {
    echo "🐍 Creating Python virtual environment..."
    python3 -m venv venv
    
    # Activate virtual environment
    if [[ "$PLATFORM" == "windows" ]]; then
        source venv/Scripts/activate
    else
        source venv/bin/activate
    fi
    
    echo "✅ Virtual environment created and activated"
}

# Function to install Python packages
install_python_packages() {
    echo "📦 Installing Python packages..."
    pip install --upgrade pip
    pip install -r requirements.txt
    
    # Install yt-dlp
    echo "🎥 Installing yt-dlp..."
    pip install yt-dlp
    
    echo "✅ Python packages installed"
}

# Function to verify installation
verify_installation() {
    echo "🔍 Verifying installation..."
    
    # Check Python packages
    python3 -c "import streamlit, yt_dlp, numpy, librosa, scipy; print('✅ All Python packages imported successfully')"
    
    # Check system commands
    for cmd in ffmpeg wget curl; do
        if command_exists "$cmd"; then
            echo "✅ $cmd is available"
        else
            echo "❌ $cmd is not available"
        fi
    done
    
    # Check FFmpeg encoders
    echo "🔍 Checking FFmpeg encoders..."
    if command_exists ffmpeg; then
        ffmpeg -hide_banner -encoders 2>/dev/null | grep -E "(h264_nvenc|hevc_nvenc|h264_qsv|hevc_qsv|h264_vaapi|hevc_vaapi|h264_videotoolbox|hevc_videotoolbox)" || echo "ℹ️ No hardware encoders found (this is normal on some systems)"
    fi
}

# Main installation process
main() {
    echo "Starting cross-platform setup for Video Downstreamcoder..."
    echo "Platform: $PLATFORM"
    echo ""
    
    # Install system packages
    install_system_packages
    
    # Create virtual environment
    create_venv
    
    # Install Python packages
    install_python_packages
    
    # Verify installation
    verify_installation
    
    echo ""
    echo "🎉 Setup completed successfully!"
    echo ""
    echo "To run the application:"
    if [[ "$PLATFORM" == "windows" ]]; then
        echo "1. Activate the virtual environment: venv\\Scripts\\activate"
        echo "2. Run the app: streamlit run streamlit_download_manager_merged.py"
    else
        echo "1. Activate the virtual environment: source venv/bin/activate"
        echo "2. Run the app: streamlit run streamlit_download_manager_merged.py"
    fi
    echo ""
    echo "Or run directly:"
    if [[ "$PLATFORM" == "windows" ]]; then
        echo "venv\\Scripts\\streamlit run streamlit_download_manager_merged.py"
    else
        echo "./venv/bin/streamlit run streamlit_download_manager_merged.py"
    fi
}

# Run main function
main "$@"
