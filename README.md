# Streamlit Download Manager

A powerful, web-based download manager with integrated video encoding capabilities. Built with Streamlit and shell commands for robust file downloading and video processing.

## ✨ Features

### 📥 Download Management
- **YouTube Support**: Download videos and playlists using `yt-dlp`
- **Direct Downloads**: Download files from URLs using `wget`/`curl`
- **Audio Extraction**: Convert YouTube videos to MP3 with metadata
- **Parallel Downloads**: Configurable concurrency (-1 for unlimited, 0 to disable)
- **Progress Tracking**: Real-time download progress and status
- **Resume Downloads**: Automatic resume for interrupted downloads

### 🎬 Video Encoding & Merging
- **Hardware Acceleration**: Auto-detection of NVIDIA NVENC, Intel QSV, VA-API
- **Multiple Codecs**: H.264, H.265, AV1 support
- **Smart Presets**: Auto-select best available encoder
- **Quality Control**: Adjustable quality settings (18-32 range)
- **File Merging**: Combine multiple video files into one
- **Real-time Progress**: Live encoding progress in terminal output

### 🌐 User Interface
- **Web-based**: Clean, responsive Streamlit interface
- **Built-in Terminal**: Real-time command output display
- **Secure Password Input**: Safe sudo password handling
- **File Management**: Easy file selection and organization
- **System Information**: Hardware acceleration detection

## 🚀 Quick Start

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd streamlit-download-manager
```

2. **Run the setup script**
```bash
chmod +x setup.sh
./setup.sh
```

3. **Start the application**
```bash
source venv/bin/activate
streamlit run streamlit_download_manager_merged.py
```

### Manual Installation

```bash
# Install system dependencies
sudo apt update
sudo apt install -y ffmpeg wget curl python3-pip python3-venv

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python packages
pip install -r requirements.txt

# Install yt-dlp globally
pipx install yt-dlp
```

## 📖 Usage

### Basic Workflow

1. **Open the app**: Navigate to `http://localhost:8501`
2. **Enter URL**: Paste a YouTube playlist or directory URL
3. **Configure Settings**:
   - Set max parallel downloads (-1 for unlimited)
   - Choose audio-only mode if needed
   - Set playlist limits for large playlists
4. **Select Files**: Choose which files to download
5. **Download**: Click "Download Selected"
6. **Encode/Merge**: Use the video encoding section for post-processing

### Download Sources

- **YouTube**: Individual videos and playlists
- **Direct URLs**: Any direct file links
- **Directory Listings**: Web directories with video files

### Video Encoding Options

- **auto**: Automatically selects best available encoder
- **Hardware Acceleration**: NVENC, QSV, VA-API when available
- **CPU Encoding**: Fallback for all systems
- **Copy Mode**: Merge without re-encoding (fastest)

## ⚙️ Configuration

### Parallel Downloads
- **-1**: Unlimited (capped at 20 for stability)
- **0**: Downloads disabled
- **1-50**: Specific number of parallel downloads

### Quality Settings
- **18**: Near-lossless quality
- **22**: Balanced quality/size (recommended)
- **25**: Default setting
- **28**: Smaller file size
- **32**: Maximum compression

### Download Location
- **Default**: `~/Downloads/StreamlitDownloads`
- **Configurable**: Set custom base directory
- **Organized**: Creates subdirectories per URL/playlist

## 🛠️ Architecture

### Hybrid Approach
- **Streamlit**: Web UI and user interaction
- **Shell Commands**: Core operations (downloading, encoding)
- **Python**: State management and command orchestration

### Shell Commands Used
- `yt-dlp`: YouTube video/audio downloading
- `wget`/`curl`: Direct file downloads
- `ffmpeg`: Video encoding and merging
- `ffprobe`: Video information extraction

## 📁 File Structure

```
streamlit-download-manager/
├── streamlit_download_manager_merged.py  # Main application
├── requirements.txt                      # Python dependencies
├── setup.sh                             # Installation script
├── README.md                            # This file
├── .gitignore                           # Git ignore rules
└── original/                            # Original scripts backup
    ├── streamlit_download_manager.py    # Original Python script
    └── video_encoder.sh                 # Original shell script
```

## 🔧 System Requirements

### Required
- Python 3.8+
- FFmpeg
- wget or curl
- Linux/macOS/Windows with WSL

### Optional (for hardware acceleration)
- NVIDIA GPU with drivers
- Intel GPU with QSV support
- AMD/Intel GPU with VA-API support

## 🐛 Troubleshooting

### Common Issues

**Missing Dependencies**
```bash
# Run system check
python streamlit_download_manager_merged.py --check-system

# Install missing packages
sudo apt install ffmpeg wget curl
pip install -r requirements.txt
```

**Permission Issues**
```bash
# Make scripts executable
chmod +x setup.sh

# Fix sudo issues
sudo -v  # Verify sudo access
```

**YouTube Downloads Failing**
```bash
# Update yt-dlp
pipx upgrade yt-dlp

# Check connectivity
wget -q --spider http://youtube.com
```

### Hardware Acceleration Issues
- Check GPU drivers: `nvidia-smi` (NVIDIA) or `vainfo` (VA-API)
- Verify FFmpeg support: `ffmpeg -encoders | grep nvenc`
- Try CPU fallback if hardware encoding fails

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project combines multiple open-source tools. Please respect individual component licenses:
- **Streamlit**: Apache 2.0
- **yt-dlp**: Unlicense
- **FFmpeg**: LGPL/GPL
- **Python libraries**: Various open-source licenses

## 🙏 Acknowledgments

- [Streamlit](https://streamlit.io/) for the excellent web framework
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) for YouTube downloading
- [FFmpeg](https://ffmpeg.org/) for video processing
- All the open-source contributors who made this possible

## 📞 Support

If you encounter issues:
1. Check the troubleshooting section
2. Review system requirements
3. Test with the original scripts in `original/`
4. Open an issue with detailed information

---

**Made with ❤️ using Streamlit and shell commands**
