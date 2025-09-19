# Video Downstreamcoder

A web-based video download and processing application that combines YouTube downloading, direct file downloads, and video encoding capabilities in a single interface.

## Features

### Download Management
- YouTube video and playlist downloading via `yt-dlp`
- Direct file downloads from URLs using `wget`/`curl`
- Audio extraction from YouTube videos to MP3 with metadata
- Configurable parallel downloads (unlimited, disabled, or specific count)
- Real-time progress tracking with speed and ETA display
- Automatic download resumption for interrupted transfers

### Video Processing
- Hardware-accelerated encoding (NVIDIA NVENC, Intel QSV, VA-API)
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
- Hardware acceleration detection and configuration

## Installation

```bash
# Clone repository
git clone https://github.com/hyperionsolitude/Video_Downreamcoder.git
cd Video_Downreamcoder

# Install system dependencies
sudo apt update
sudo apt install -y ffmpeg wget curl python3-pip python3-venv

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install yt-dlp
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
- NVIDIA GPU with drivers
- Intel GPU with QSV support
- AMD/Intel GPU with VA-API support

## Troubleshooting

### Common Issues

**Missing Dependencies**
```bash
sudo apt install ffmpeg wget curl
pip install -r requirements.txt
```

**YouTube Downloads Failing**
```bash
pip install --upgrade yt-dlp
```

**Hardware Acceleration Issues**
- Check GPU drivers: `nvidia-smi` (NVIDIA) or `vainfo` (VA-API)
- Verify FFmpeg support: `ffmpeg -encoders | grep nvenc`
- Application automatically falls back to CPU encoding if hardware acceleration fails

## License

This project uses open-source components:
- Streamlit (Apache 2.0)
- yt-dlp (Unlicense)
- FFmpeg (LGPL/GPL)
- Python libraries (various open-source licenses)
