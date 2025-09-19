# Changelog

All notable changes to this project will be documented in this file.

## [2.1.0] - 2025-09-19

### ✨ New Features
- **Anime OP/ED Auto-Trim**: Detects intro/outro via audio similarity (MFCC) across episodes
- **Per-Episode Alignment**: Finds the best OP/ED offsets per file when timing shifts
- **Deleted Parts Review**: Exports removed segments and builds a `deleted.mp4` concat for verification
- **Preview Detected Ranges**: UI shows per-file OP/ED ranges with confidence before encoding

### 🔧 Improvements
- **Copy Preset**: Truly copies when possible (single-file copy and concat with `-c copy`), fallback to minimal re-encode only if needed
- **One-Click Cleanup**: Option to keep only the final merged output and `deleted.mp4`, removing all residuals
- **Auto-Detect Fallback**: If AI trim is enabled without manual/detected ranges, detection runs automatically at encode time

### 🐛 Fixes
- Ensured trimming applies even with "copy" preset by handling concat compatibility
- Stabilized temp directory cleanup and file list handling

## [2.0.0] - 2025-09-18

### 🎉 Major Release - Merged Application

**Breaking Changes:**
- Combined separate Python and shell scripts into single application
- New unified interface with built-in terminal output
- Changed default parallel downloads to -1 (unlimited)

### ✨ New Features
- **Integrated Terminal**: Real-time command output in web interface
- **Interactive Password Input**: Secure sudo password handling in UI
- **Self-contained Video Encoding**: No external shell script dependency
- **Smart Concurrency Control**: -1 for unlimited, 0 to disable, 1-50 for limits
- **Hardware Acceleration Detection**: Auto-detection of NVENC, QSV, VA-API
- **Progress Tracking**: Real-time download and encoding progress
- **Resume Downloads**: Automatic resume for interrupted transfers

### 🔧 Improvements
- Better error handling and user feedback
- Cleaner UI with organized sections
- Improved file management and organization
- Enhanced system requirements checking
- Streamlined installation process

### 🐛 Bug Fixes
- Fixed video encoder script not found errors
- Resolved sudo password prompt issues
- Improved file path handling across platforms
- Fixed concurrent download thread management

## [1.0.0] - Original Version

### Features
- Separate Python download manager (`streamlit_download_manager.py`)
- Separate shell video encoder (`video_encoder.sh`)
- Basic YouTube and direct download support
- Command-line video encoding with hardware acceleration
- Manual integration between download and encoding workflows
