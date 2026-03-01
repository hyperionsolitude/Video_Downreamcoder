#!/usr/bin/env python3
"""
Streamlit Download Manager with Shell Command Integration
Combines download management with video encoding using shell commands

Features:
- Cross-platform video downloading and processing
- Hardware-accelerated encoding (NVIDIA, Intel, AMD, Apple Silicon)
- AI-powered intro/outro detection and trimming
- Real-time progress monitoring
- macOS security integration
"""

# Run dependency check first (shows install instructions and st.stop() if deps missing)
import app.deps_check  # noqa: F401

from app.main_ui import main

main()
