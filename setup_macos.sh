#!/bin/bash
# macOS-specific setup script for Video Downstreamcoder

set -e

echo "🍎 Setting up Video Downstreamcoder on macOS..."

# Check if we're on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "❌ This script is for macOS only. Use setup_cross_platform.sh for other platforms."
    exit 1
fi

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to install Homebrew
install_homebrew() {
    if ! command_exists brew; then
        echo "📦 Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        
        # Add Homebrew to PATH for Apple Silicon Macs
        if [[ $(uname -m) == "arm64" ]]; then
            echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
            eval "$(/opt/homebrew/bin/brew shellenv)"
            echo "✅ Homebrew added to PATH for Apple Silicon"
        fi
    else
        echo "✅ Homebrew already installed"
    fi
}

# Function to install system packages
install_system_packages() {
    echo "📦 Installing system packages via Homebrew..."
    
    # Install essential packages
    brew install ffmpeg wget curl python3
    
    # Install additional packages for better FFmpeg support
    brew install --cask temurin  # OpenJDK for better Java support
    brew install pkg-config
    
    echo "✅ System packages installed"
}

# Function to create virtual environment
create_venv() {
    echo "🐍 Creating Python virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "✅ Virtual environment created and activated"
}

# Function to install Python packages
install_python_packages() {
    echo "📦 Installing Python packages..."
    
    # Upgrade pip first
    pip install --upgrade pip
    
    # Install requirements
    pip install -r requirements.txt
    
    # Install yt-dlp
    echo "🎥 Installing yt-dlp..."
    pip install yt-dlp
    
    echo "✅ Python packages installed"
}

# Function to check hardware acceleration
check_hardware_acceleration() {
    echo "🔍 Checking hardware acceleration support..."
    
    if command_exists ffmpeg; then
        echo "FFmpeg encoders available:"
        ffmpeg -hide_banner -encoders 2>/dev/null | grep -E "(h264_videotoolbox|hevc_videotoolbox|h264_nvenc|hevc_nvenc)" || echo "ℹ️ No hardware encoders found"
        
        # Test VideoToolbox specifically
        echo "Testing VideoToolbox encoder..."
        if ffmpeg -f lavfi -i testsrc=duration=1:size=320x240:rate=1 -c:v h264_videotoolbox -f null - 2>&1 | grep -q "VideoToolbox"; then
            echo "✅ VideoToolbox H.264 encoder working"
        else
            echo "⚠️ VideoToolbox H.264 encoder not available"
        fi
        
        if ffmpeg -f lavfi -i testsrc=duration=1:size=320x240:rate=1 -c:v hevc_videotoolbox -f null - 2>&1 | grep -q "VideoToolbox"; then
            echo "✅ VideoToolbox HEVC encoder working"
        else
            echo "⚠️ VideoToolbox HEVC encoder not available"
        fi
    fi
}

# Function to verify installation
verify_installation() {
    echo "🔍 Verifying installation..."
    
    # Check Python packages
    python3 -c "import streamlit, yt_dlp, numpy, librosa, scipy, distro; print('✅ All Python packages imported successfully')"
    
    # Check system commands
    for cmd in ffmpeg wget curl; do
        if command_exists "$cmd"; then
            echo "✅ $cmd is available"
        else
            echo "❌ $cmd is not available"
        fi
    done
    
    # Check hardware acceleration
    check_hardware_acceleration
}

# Function to create launch script
create_launch_script() {
    echo "📝 Creating launch script..."
    
    cat > run_app.sh << 'EOF'
#!/bin/bash
# Launch script for Video Downstreamcoder

# Activate virtual environment
source venv/bin/activate

# Run the application
streamlit run streamlit_download_manager_merged.py
EOF
    
    chmod +x run_app.sh
    echo "✅ Launch script created: run_app.sh"
}

# Main installation process
main() {
    echo "Starting macOS setup for Video Downstreamcoder..."
    echo "Architecture: $(uname -m)"
    echo ""
    
    # Install Homebrew
    install_homebrew
    
    # Install system packages
    install_system_packages
    
    # Create virtual environment
    create_venv
    
    # Install Python packages
    install_python_packages
    
    # Verify installation
    verify_installation
    
    # Create launch script
    create_launch_script
    
    echo ""
    echo "🎉 macOS setup completed successfully!"
    echo ""
    echo "To run the application:"
    echo "1. Activate the virtual environment: source venv/bin/activate"
    echo "2. Run the app: streamlit run streamlit_download_manager_merged.py"
    echo ""
    echo "Or use the launch script:"
    echo "./run_app.sh"
    echo ""
    echo "Hardware acceleration:"
    echo "- VideoToolbox: Available on all modern Macs"
    echo "- Metal: Available on Apple Silicon Macs"
    echo "- Intel Quick Sync: Available on Intel Macs with supported graphics"
}

# Run main function
main "$@"
