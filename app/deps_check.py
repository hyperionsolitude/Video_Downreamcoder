"""Run dependency check at import time; show installation instructions and stop if deps missing."""

import platform

import streamlit as st

missing_deps = []
try:
    import librosa
except ImportError:
    missing_deps.append("librosa")
try:
    from scipy.spatial.distance import cosine
except ImportError:
    missing_deps.append("scipy")
try:
    import distro
except ImportError:
    missing_deps.append("distro")

if missing_deps:
    st.error("🚨 **Missing Required Dependencies**")
    st.write(f"The following Python packages are required but not installed: {', '.join(missing_deps)}")
    st.write("**To install dependencies, run one of these commands:**")
    system = platform.system().lower()
    if system == "darwin":
        st.code("pip3 install -r requirements.txt", language="bash")
        st.write("**Or use Homebrew (recommended for macOS):**")
        st.code("brew install python3 && pip3 install -r requirements.txt", language="bash")
    elif system == "linux":
        st.code("pip3 install -r requirements.txt", language="bash")
        st.write("**Or install system packages first:**")
        st.code("sudo apt install python3-pip && pip3 install -r requirements.txt", language="bash")
    else:
        st.code("pip install -r requirements.txt", language="bash")
    st.write("**After installing dependencies, refresh this page.**")
    st.stop()
