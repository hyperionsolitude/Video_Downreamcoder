# 🎬 Video Downstreamcoder

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-red.svg)](https://streamlit.io)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)](https://github.com/hyperionsolitude/Video_Downreamcoder)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A powerful cross-platform web-based video download and processing application that combines YouTube downloading, direct file downloads, and hardware-accelerated video encoding in a single, intuitive interface. **Fully optimized for macOS (including Apple Silicon M1/M2/M3/M4), Ubuntu, and other Linux distributions.**

## ✨ Key Features

### 🚀 **Hardware-Accelerated Processing**
- **Apple Silicon**: VideoToolbox (uses Metal GPU) for M1/M2/M3/M4
- **NVIDIA**: NVENC encoding for RTX/GTX series
- **Intel**: Quick Sync Video (QSV) support
- **AMD**: VA-API acceleration on Linux
- **Cross-platform**: Automatic fallback to CPU encoding

### 🎯 **AI-Powered Video Processing**
- **Smart OP/ED Detection**: Audio similarity analysis using MFCC
- **Per-Episode Alignment**: Handles shifting intro/outro positions
- **Automatic Trimming**: Remove repetitive content intelligently
- **Quality Preservation**: Maintains video quality during processing

### 📥 **Advanced Download Management**
- **YouTube Integration**: Playlists, channels, and individual videos
- **Direct Downloads**: Support for any video URL
- **Parallel Processing**: Configurable concurrent downloads
- **Resume Support**: Automatic retry for interrupted downloads
- **Progress Tracking**: Real-time speed and ETA monitoring

## Features

### Download Management
- YouTube video and playlist downloading via `yt-dlp`
- Direct file downloads from URLs using `wget`/`curl`
- Audio extraction from YouTube videos to MP3 with metadata
- Configurable parallel downloads (unlimited, disabled, or specific count)
- Real-time progress tracking with speed and ETA display
- Automatic download resumption for interrupted transfers

### Video Processing
- **Cross-platform hardware-accelerated encoding:**
  - **macOS**: VideoToolbox (H.264/HEVC), Metal support
  - **Linux**: NVIDIA NVENC, Intel QSV, VA-API
  - **Windows**: NVIDIA NVENC, Intel QSV
- CPU fallback encoding (libx264, libx265)
- Multiple codec support (H.264, H.265)
- Quality control with CRF settings (18-32)
- Video file merging and concatenation
- Real-time encoding progress monitoring
- Anime OP/ED auto-trim with audio-similarity analysis (MFCC-based)
- Per-episode alignment for shifting OP/ED positions
- Optional deleted.mp4 created from removed OP/ED segments for review
- "Copy" preset now truly copies when possible (single file copy or concat with -c copy)

### Interface
- Streamlit-based web interface
- Integrated terminal output display
- File selection and management
- **Automatic hardware acceleration detection and configuration**
- **Cross-platform package manager integration**

## Installation

### Quick Setup (Recommended)

**Option 1: One-command launch (fastest)**
```bash
# Clone repository
git clone https://github.com/hyperionsolitude/Video_Downreamcoder.git
cd Video_Downreamcoder

# Run the app (auto-installs dependencies)
./run.sh
```

**Option 2: Python-only setup**
```bash
# Clone repository
git clone https://github.com/hyperionsolitude/Video_Downreamcoder.git
cd Video_Downreamcoder

# Run quick setup script
python3 quick_setup.py

# Start the app
streamlit run streamlit_download_manager_merged.py
```

**Option 3: Full system setup (includes system packages)**

**Option 4: Built-in setup (automatic)**
The app automatically detects missing dependencies and provides installation instructions when you first run it.

**Option 5: Original separate scripts**
If you prefer the original separate scripts, they are available in the `original/` directory:
- `original/streamlit_download_manager.py` - Original Streamlit app
- `original/video_encoder.sh` - Original video encoder script

**Note**: The main application (`streamlit_download_manager_merged.py`) contains all functionality and is recommended for most users.
```bash
# Clone repository
git clone https://github.com/hyperionsolitude/Video_Downreamcoder.git
cd Video_Downreamcoder

# For all platforms
chmod +x setup_cross_platform.sh
./setup_cross_platform.sh

# For macOS specifically
chmod +x setup_macos.sh
./setup_macos.sh
```

**Option 3: Manual setup**
```bash
# Clone repository
git clone https://github.com/hyperionsolitude/Video_Downreamcoder.git
cd Video_Downreamcoder

# Install Python dependencies
pip3 install -r requirements.txt

# Install system dependencies (macOS)
brew install ffmpeg wget curl

# Start the app
streamlit run streamlit_download_manager_merged.py
```

### Manual Installation

#### macOS (Intel & Apple Silicon)
```bash
# Install Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install system dependencies
brew install ffmpeg wget curl python3

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
pip install yt-dlp

# Run application
streamlit run streamlit_download_manager_merged.py
```

#### Ubuntu/Debian
```bash
# Install system dependencies
sudo apt update
sudo apt install -y ffmpeg wget curl python3-pip python3-venv python3-dev libffi-dev libssl-dev

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
pip install yt-dlp

# Run application
streamlit run streamlit_download_manager_merged.py
```

#### Fedora/RHEL/CentOS
```bash
# Install system dependencies
sudo dnf install -y ffmpeg wget curl python3-pip python3-venv python3-devel libffi-devel openssl-devel

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
pip install yt-dlp

# Run application
streamlit run streamlit_download_manager_merged.py
```

#### Arch Linux
```bash
# Install system dependencies
sudo pacman -S --noconfirm ffmpeg wget curl python-pip python-virtualenv

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
pip install yt-dlp

# Run application
streamlit run streamlit_download_manager_merged.py
```

## Usage

### Basic Workflow

1. Access the application at `http://localhost:8501`
2. Enter YouTube playlist URL or direct file URLs
3. Configure download settings (parallel downloads, audio-only mode)
4. Select files to download from the generated list
5. Monitor real-time download progress
6. Use video encoding section for post-processing

### Download Sources

- YouTube videos and playlists
- Direct file URLs
- Web directory listings

### Video Encoding

- Automatic encoder selection with hardware acceleration detection
- Fallback to CPU encoding when hardware acceleration unavailable
- Support for H.264 and H.265 codecs
- Quality control via CRF settings

#### Anime OP/ED Trimming

1) Expand "Anime OP/ED Trimming (optional)" in the Encoding section.
2) Choose Detection Method:
   - Manual Input: enter intro/outro seconds
   - Auto-Detect (AI Analysis): detect repeated OP/ED across episodes
   - Both: auto-detect with manual override
3) (Optional) Enable "Per-episode auto alignment" so OP/ED are matched per file even if shifted.
4) Click "Auto-Detect OP/ED" to preview detected ranges per file (with confidence).
5) Start Encoding.

Outputs and cleanup:
- Keep only final outputs (trimmed.mp4 and deleted.mp4): when enabled, cleans all residual folders and source videos, leaving only your merged output and a compiled deleted.mp4 of removed parts.
- Also create deleted.mp4: builds a concat of all removed OP/ED segments for quick review.

Notes on "copy" preset:
- If a single input file (original or trimmed) is selected, the output is a direct filesystem copy.
- For multiple files, the app first attempts ffmpeg concat with `-c copy`. If the bitstreams are incompatible, it automatically falls back to a minimal re-encode for compatibility.

## Configuration

### Parallel Downloads
- `-1`: Unlimited downloads (capped at 20)
- `0`: Downloads disabled
- `1-50`: Specific number of parallel downloads

### Quality Settings (CRF)
- `18`: Near-lossless quality
- `22`: Balanced quality/size (recommended)
- `25`: Default setting
- `28`: Smaller file size
- `32`: Maximum compression

### Download Location
- Default: `~/Downloads/StreamlitDownloads`
- Creates organized subdirectories per URL/playlist

## System Requirements

### Required
- Python 3.8+
- FFmpeg
- wget or curl
- Linux/macOS/Windows with WSL
- For AI OP/ED detection: numpy, scipy, librosa (installed via requirements.txt)

### Optional (Hardware Acceleration)

#### macOS
- **VideoToolbox**: Available on all modern Macs (Intel and Apple Silicon)
- **Metal**: Available on Apple Silicon Macs (M1/M2/M3/M4)
- **Intel Quick Sync**: Available on Intel Macs with supported integrated graphics

#### Linux
- NVIDIA GPU with drivers (NVENC)
- Intel GPU with QSV support
- AMD/Intel GPU with VA-API support

#### Windows
- NVIDIA GPU with drivers (NVENC)
- Intel GPU with QSV support

## macOS-Specific Features

### Apple Silicon Optimization
- **Native ARM64 support** for M1/M2/M3/M4 Macs
- **VideoToolbox hardware acceleration** for H.264 and HEVC encoding
- **Metal framework integration** for enhanced graphics performance
- **Optimized FFmpeg builds** via Homebrew

### Hardware Acceleration on macOS
The application automatically detects and uses the best available hardware acceleration:

1. **VideoToolbox** (Primary): Uses Apple's hardware encoders
   - H.264: `h264_videotoolbox`
   - HEVC: `hevc_videotoolbox`
   - Quality control via `-q:v` parameter

2. **Metal** (Secondary): For graphics processing
   - Automatically detected and used when available

3. **CPU Fallback**: Software encoding with libx264/libx265

### Performance on Apple Silicon
- **M4 Macs**: Excellent performance with VideoToolbox acceleration
- **M3 Macs**: Very good performance with full hardware support
- **M2 Macs**: Good performance with most features supported
- **M1 Macs**: Good performance with basic hardware acceleration

## Troubleshooting

### Common Issues

**Missing Dependencies**

*Ubuntu/Debian:*
```bash
sudo apt install ffmpeg wget curl
pip install -r requirements.txt
```

**macOS Security Warnings**

If you get "Apple could not verify" warnings when opening generated video files:
- **Automatic fix**: The app automatically removes quarantine attributes
- **Alternative**: Right-click the file → "Open With" → VLC (or your preferred player)

*macOS:*
```bash
brew install ffmpeg wget curl
pip install -r requirements.txt
```

**YouTube Downloads Failing**
```bash
pip install --upgrade yt-dlp
```

**Hardware Acceleration Issues**

*Linux:*
- Check GPU drivers: `nvidia-smi` (NVIDIA) or `vainfo` (VA-API)
- Verify FFmpeg support: `ffmpeg -encoders | grep nvenc`

*macOS:*
- Check VideoToolbox: `ffmpeg -encoders | grep videotoolbox`
- Verify Metal support: Check System Information > Graphics/Displays
- Test VideoToolbox: `ffmpeg -f lavfi -i testsrc=duration=1:size=320x240:rate=1 -c:v h264_videotoolbox -f null -`

*General:*
- Application automatically falls back to CPU encoding if hardware acceleration fails

## License

This project uses open-source components:
- Streamlit (Apache 2.0)
- yt-dlp (Unlicense)
- FFmpeg (LGPL/GPL)
- Python libraries (various open-source licenses)
