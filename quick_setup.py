#!/usr/bin/env python3
"""
Quick setup script for Video Downstreamcoder
Installs dependencies and checks system requirements
"""

import subprocess
import sys
import platform
import os

def run_command(cmd, description):
    """Run a command and return success status"""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e.stderr}")
        return False

def check_python_version():
    """Check if Python version is compatible"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print(f"❌ Python {version.major}.{version.minor} is not supported. Please use Python 3.8 or higher.")
        return False
    print(f"✅ Python {version.major}.{version.minor}.{version.micro} is compatible")
    return True

def install_dependencies():
    """Install Python dependencies"""
    print("📦 Installing Python dependencies...")
    
    # Check if requirements.txt exists
    if not os.path.exists("requirements.txt"):
        print("❌ requirements.txt not found. Please run this script from the project directory.")
        return False
    
    # Install dependencies
    if run_command("pip3 install -r requirements.txt", "Installing Python packages"):
        return True
    else:
        # Try with pip instead of pip3
        return run_command("pip install -r requirements.txt", "Installing Python packages (fallback)")

def check_system_dependencies():
    """Check for system dependencies"""
    print("🔍 Checking system dependencies...")
    
    system = platform.system().lower()
    missing_deps = []
    
    # Check for FFmpeg
    if not run_command("ffmpeg -version", "Checking FFmpeg"):
        missing_deps.append("ffmpeg")
    
    # Check for wget or curl
    if not run_command("wget --version", "Checking wget") and not run_command("curl --version", "Checking curl"):
        missing_deps.append("wget or curl")
    
    if missing_deps:
        print(f"⚠️ Missing system dependencies: {', '.join(missing_deps)}")
        print("Please install them using your system package manager:")
        
        if system == "darwin":  # macOS
            print("  brew install ffmpeg wget curl")
        elif system == "linux":
            print("  sudo apt install ffmpeg wget curl  # Ubuntu/Debian")
            print("  sudo dnf install ffmpeg wget curl  # Fedora/RHEL")
            print("  sudo pacman -S ffmpeg wget curl    # Arch Linux")
        else:
            print("  Please install ffmpeg, wget, and curl using your package manager")
        
        return False
    
    print("✅ All system dependencies are available")
    return True

def main():
    """Main setup function"""
    print("🚀 Video Downstreamcoder - Quick Setup")
    print("=" * 50)
    
    # Check Python version
    if not check_python_version():
        sys.exit(1)
    
    # Install Python dependencies
    if not install_dependencies():
        print("❌ Failed to install Python dependencies")
        print("Please try running: pip3 install -r requirements.txt")
        sys.exit(1)
    
    # Check system dependencies
    if not check_system_dependencies():
        print("⚠️ Some system dependencies are missing, but you can still run the app")
        print("The app will guide you through installing them.")
    
    print("\n🎉 Setup completed!")
    print("You can now run the app with:")
    print("  streamlit run streamlit_download_manager_merged.py")
    print("\nThe app will be available at: http://localhost:8501")

if __name__ == "__main__":
    main()
