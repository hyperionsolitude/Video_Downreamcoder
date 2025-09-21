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

from __future__ import annotations

import asyncio
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import streamlit as st
import yt_dlp
import aiohttp
from bs4 import BeautifulSoup, Tag

# Check for required dependencies and provide helpful error messages
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
    import distro  # For Linux distribution detection
except ImportError:
    missing_deps.append("distro")

# If dependencies are missing, show installation instructions
if missing_deps:
    st.error("🚨 **Missing Required Dependencies**")
    st.write(f"The following Python packages are required but not installed: {', '.join(missing_deps)}")
    
    st.write("**To install dependencies, run one of these commands:**")
    
    # Detect platform for appropriate installation command
    system = platform.system().lower()
    if system == "darwin":  # macOS
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

# --- PLATFORM DETECTION ---
def detect_platform() -> Dict[str, Any]:
    """Detect the current platform and return platform-specific configurations.
    
    Returns:
        Dict containing platform information including OS, architecture,
        package manager, and platform-specific configurations.
    """
    system = platform.system().lower()
    machine = platform.machine().lower()
    
    config = {
        'os': system,
        'arch': machine,
        'is_macos': system == 'darwin',
        'is_linux': system == 'linux',
        'is_windows': system == 'windows',
        'is_arm': 'arm' in machine or 'aarch64' in machine,
        'is_apple_silicon': system == 'darwin' and ('arm' in machine or 'aarch64' in machine),
        'package_manager': None,
        'ffmpeg_install_cmd': None,
        'system_packages': [],
        'hardware_acceleration': []
    }
    
    if config['is_macos']:
        config['package_manager'] = 'homebrew'
        config['ffmpeg_install_cmd'] = 'brew install ffmpeg'
        config['system_packages'] = ['ffmpeg', 'wget', 'curl']
        config['hardware_acceleration'] = ['videotoolbox', 'metal']
        
        # Check if Homebrew is installed
        try:
            subprocess.run(['brew', '--version'], capture_output=True, check=True)
            config['homebrew_installed'] = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            config['homebrew_installed'] = False
            
    elif config['is_linux']:
        # Detect Linux distribution
        try:
            distro_info = distro.linux_distribution(full_distribution_name=False)
            distro_name = distro_info[0].lower()
            
            if 'ubuntu' in distro_name or 'debian' in distro_name:
                config['package_manager'] = 'apt'
                config['ffmpeg_install_cmd'] = 'sudo apt install ffmpeg'
                config['system_packages'] = ['ffmpeg', 'wget', 'curl', 'python3-pip', 'python3-venv', 'python3-dev', 'libffi-dev', 'libssl-dev']
            elif 'fedora' in distro_name or 'rhel' in distro_name or 'centos' in distro_name:
                config['package_manager'] = 'dnf'
                config['ffmpeg_install_cmd'] = 'sudo dnf install ffmpeg'
                config['system_packages'] = ['ffmpeg', 'wget', 'curl', 'python3-pip', 'python3-venv', 'python3-devel', 'libffi-devel', 'openssl-devel']
            elif 'arch' in distro_name:
                config['package_manager'] = 'pacman'
                config['ffmpeg_install_cmd'] = 'sudo pacman -S ffmpeg'
                config['system_packages'] = ['ffmpeg', 'wget', 'curl', 'python-pip', 'python-virtualenv']
            else:
                # Generic fallback
                config['package_manager'] = 'unknown'
                config['ffmpeg_install_cmd'] = 'Please install ffmpeg manually'
                config['system_packages'] = ['ffmpeg', 'wget', 'curl']
                
        except Exception:
            # Fallback if distro detection fails
            config['package_manager'] = 'unknown'
            config['ffmpeg_install_cmd'] = 'Please install ffmpeg manually'
            config['system_packages'] = ['ffmpeg', 'wget', 'curl']
            
        config['hardware_acceleration'] = ['nvenc', 'qsv', 'vaapi']
        
    elif config['is_windows']:
        config['package_manager'] = 'chocolatey'
        config['ffmpeg_install_cmd'] = 'choco install ffmpeg'
        config['system_packages'] = ['ffmpeg', 'wget', 'curl']
        config['hardware_acceleration'] = ['nvenc', 'qsv']
    
    return config

# Initialize platform configuration
PLATFORM_CONFIG = detect_platform()

# --- CONFIG ---
BASE_DOWNLOAD_DIR = os.path.expanduser("~/Downloads/StreamlitDownloads")
VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm')
AUDIO_EXTENSIONS = ('.mp3', '.m4a', '.aac', '.ogg', '.wav', '.flac')
YOUTUBE_DOMAINS = ("youtube.com", "youtu.be")
MAX_CONCURRENT_DOWNLOADS = 4

# --- UTILS ---
def get_base_download_dir():
    base = st.session_state.get('base_download_dir', BASE_DOWNLOAD_DIR)
    return os.path.expanduser(base)

def ensure_download_dir(folder_name):
    full_path = os.path.join(get_base_download_dir(), folder_name)
    if not os.path.exists(full_path):
        os.makedirs(full_path)
    return full_path

def remove_download_dir(folder_name):
    full_path = os.path.join(get_base_download_dir(), folder_name)
    if os.path.exists(full_path):
        shutil.rmtree(full_path)

def is_youtube_url(url):
    parsed = urllib.parse.urlparse(url)
    return any(domain in parsed.netloc for domain in YOUTUBE_DOMAINS)

def normalize_filename(filename):
    """Normalize filename for safe filesystem usage"""
    filename = filename.replace('\n', '_').replace('\r', '_')
    filename = re.sub(r'[\\/:*?"<>|]', '_', filename)
    filename = re.sub(r'_+', '_', filename)
    filename = filename.strip(' _')
    return filename[:200]

def get_folder_name_from_url(url, playlist_title=None):
    """Get folder name from URL, using playlist title for YouTube playlists"""
    if is_youtube_url(url) and playlist_title:
        return normalize_filename(playlist_title)
    
    parsed = urllib.parse.urlparse(url)
    path_parts = parsed.path.strip('/').split('/')
    last_part = path_parts[-1] if path_parts else None
    
    if not last_part or '.' in last_part:
        last_part = path_parts[-2] if len(path_parts) > 1 else None
    
    return last_part or "downloads"

# --- TERMINAL OUTPUT SYSTEM ---
class TerminalOutput:
    def __init__(self):
        self.output_queue = queue.Queue()
        self.max_lines = 100
        self.command_count = 0
    
    def add_line(self, text, cmd_type="info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Color coding based on type
        if cmd_type == "command":
            self.command_count += 1
            formatted_text = f"<span style='color: #00ff00; font-weight: bold;'>[{timestamp}] $ {text}</span>"
        elif cmd_type == "error":
            formatted_text = f"<span style='color: #ff4444; font-weight: bold;'>[{timestamp}] ❌ {text}</span>"
        elif cmd_type == "warning":
            formatted_text = f"<span style='color: #ffaa00; font-weight: bold;'>[{timestamp}] ⚠️ {text}</span>"
        elif cmd_type == "success":
            formatted_text = f"<span style='color: #00ff88; font-weight: bold;'>[{timestamp}] ✅ {text}</span>"
        elif cmd_type == "info":
            formatted_text = f"<span style='color: #00aaff;'>[{timestamp}] ℹ️ {text}</span>"
        else:
            formatted_text = f"<span style='color: #ffffff;'>[{timestamp}] {text}</span>"
        
        self.output_queue.put(formatted_text)
    
    def get_output(self):
        lines = []
        while not self.output_queue.empty() and len(lines) < self.max_lines:
            try:
                lines.append(self.output_queue.get_nowait())
            except queue.Empty:
                break
        return lines[-self.max_lines:]  # Keep only recent lines
    
    def clear(self):
        """Clear the terminal output"""
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                break

# Global terminal output instance
if 'terminal_output' not in st.session_state:
    st.session_state.terminal_output = TerminalOutput()

# --- SHELL COMMAND FUNCTIONS ---
def run_shell_command_with_output(cmd, cwd=None, timeout=300, show_in_terminal=True):
    """Run shell command with real-time output capture"""
    # Ensure terminal_output exists in session state
    if 'terminal_output' not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()
    
    terminal = st.session_state.terminal_output
    
    if show_in_terminal:
        terminal.add_line(f"$ {cmd}", "command")
    
    try:
        process = subprocess.Popen(
            cmd,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        stdout_lines = []
        
        # Read output line by line
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                line = output.strip()
                stdout_lines.append(line)
                if show_in_terminal:
                    terminal.add_line(line, "output")
        
        process.wait(timeout=timeout)
        
        return {
            'success': process.returncode == 0,
            'stdout': '\n'.join(stdout_lines),
            'stderr': '',
            'returncode': process.returncode
        }
        
    except subprocess.TimeoutExpired:
        if show_in_terminal:
            terminal.add_line("Command timed out", "error")
        return {
            'success': False,
            'stdout': '',
            'stderr': 'Command timed out',
            'returncode': -1
        }
    except Exception as e:
        if show_in_terminal:
            terminal.add_line(f"Error: {str(e)}", "error")
        return {
            'success': False,
            'stdout': '',
            'stderr': str(e),
            'returncode': -1
        }

def run_shell_command(cmd, cwd=None, timeout=300, interactive=False):
    """Run shell command and return result"""
    if interactive:
        # For interactive commands, use the output version
        return run_shell_command_with_output(cmd, cwd, timeout, show_in_terminal=True)
    else:
        try:
            result = subprocess.run(
                cmd, 
                shell=True, 
                cwd=cwd, 
                capture_output=True, 
                text=True, 
                timeout=timeout
            )
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'stdout': '',
                'stderr': 'Command timed out',
                'returncode': -1
            }
        except Exception as e:
            return {
                'success': False,
                'stdout': '',
                'stderr': str(e),
                'returncode': -1
            }

def check_command_exists(command):
    """Check if a command exists in the system"""
    result = run_shell_command(f"which {command}")
    return result['success']

def run_sudo_command_with_password(cmd, password, timeout=300):
    """Run sudo command with password provided via stdin"""
    # Ensure terminal_output exists in session state
    if 'terminal_output' not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()
    
    terminal = st.session_state.terminal_output
    terminal.add_line(f"$ echo '[password]' | sudo -S {cmd}", "command")
    
    try:
        # Use sudo -S to read password from stdin
        full_cmd = f"echo '{password}' | sudo -S {cmd}"
        process = subprocess.Popen(
            full_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        stdout_lines = []
        
        # Read output line by line
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                line = output.strip()
                # Don't show password-related lines in terminal
                if not any(word in line.lower() for word in ['password', 'sorry', 'authentication']):
                    stdout_lines.append(line)
                    terminal.add_line(line, "output")
        
        process.wait(timeout=timeout)
        
        return {
            'success': process.returncode == 0,
            'stdout': '\n'.join(stdout_lines),
            'stderr': '',
            'returncode': process.returncode
        }
        
    except subprocess.TimeoutExpired:
        terminal.add_line("Command timed out", "error")
        return {
            'success': False,
            'stdout': '',
            'stderr': 'Command timed out',
            'returncode': -1
        }
    except Exception as e:
        terminal.add_line(f"Error: {str(e)}", "error")
        return {
            'success': False,
            'stdout': '',
            'stderr': str(e),
            'returncode': -1
        }

def install_prerequisites():
    """Install required packages using cross-platform package managers"""
    # Ensure terminal_output exists in session state
    if 'terminal_output' not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()
    
    terminal = st.session_state.terminal_output
    terminal.add_line(f"Starting prerequisites installation on {PLATFORM_CONFIG['os']}...", "info")
    
    st.info(f"Installing prerequisites for {PLATFORM_CONFIG['os']}...")
    
    # macOS installation
    if PLATFORM_CONFIG['is_macos']:
        return install_prerequisites_macos(terminal)
    
    # Linux installation
    elif PLATFORM_CONFIG['is_linux']:
        return install_prerequisites_linux(terminal)
    
    # Windows installation
    elif PLATFORM_CONFIG['is_windows']:
        return install_prerequisites_windows(terminal)
    
    else:
        st.error(f"❌ Unsupported operating system: {PLATFORM_CONFIG['os']}")
        terminal.add_line(f"Unsupported OS: {PLATFORM_CONFIG['os']}", "error")
        return False

def install_prerequisites_macos(terminal):
    """Install prerequisites on macOS using Homebrew"""
    st.info("🍎 Installing prerequisites on macOS...")
    
    # Check if Homebrew is installed
    if not PLATFORM_CONFIG.get('homebrew_installed', False):
        st.warning("⚠️ Homebrew not found. Installing Homebrew first...")
        terminal.add_line("Installing Homebrew...", "info")
        
        # Install Homebrew
        install_cmd = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        result = run_shell_command_with_output(install_cmd, timeout=300)
        
        if not result['success']:
            st.error("❌ Failed to install Homebrew. Please install it manually from https://brew.sh")
            terminal.add_line("Failed to install Homebrew", "error")
            return False
        
        st.success("✅ Homebrew installed!")
        terminal.add_line("Homebrew installed successfully", "info")
    
    # Install packages via Homebrew
    packages = ['ffmpeg', 'wget', 'curl']
    st.info("🔧 Installing system packages via Homebrew...")
    
    for package in packages:
        st.info(f"Installing {package}...")
        result = run_shell_command_with_output(f"brew install {package}", timeout=120)
        
        if not result['success']:
            st.warning(f"Failed to install {package}")
            terminal.add_line(f"Failed to install {package}", "error")
        else:
            st.success(f"✅ {package} installed!")
            terminal.add_line(f"Successfully installed {package}", "info")
    
    # Install yt-dlp
    st.info("🎥 Installing yt-dlp...")
    result = run_shell_command_with_output("pip3 install --user yt-dlp", timeout=120)
    if not result['success']:
        st.warning("Failed to install yt-dlp via pip3")
        terminal.add_line("Failed to install yt-dlp", "error")
    else:
        st.success("✅ yt-dlp installed!")
        terminal.add_line("yt-dlp installed successfully", "info")
    
    terminal.add_line("macOS prerequisites installation completed!", "info")
    st.success("🎉 Prerequisites installation completed!")
    return True

def install_prerequisites_linux(terminal):
    """Install prerequisites on Linux using appropriate package manager"""
    st.info("🐧 Installing prerequisites on Linux...")
    
    # Check if we can run sudo commands without password first
    sudo_check = run_shell_command("sudo -n true", timeout=5)
    needs_password = not sudo_check['success']
    
    password = st.session_state.get('sudo_password', None)
    
    if needs_password and not password:
        st.error("❌ No password provided for sudo commands.")
        return False
    
    if needs_password and password:
        # Test the password first
        st.info("🔍 Verifying password...")
        test_result = run_sudo_command_with_password("true", password, timeout=10)
        if not test_result['success']:
            st.error("❌ Invalid password. Please try again.")
            terminal.add_line("Invalid sudo password provided", "error")
            return False
        
        st.success("✅ Password verified!")
        terminal.add_line("Sudo password verified successfully", "info")
    
    # Install packages based on package manager
    if PLATFORM_CONFIG['package_manager'] == 'apt':
        return install_prerequisites_apt(terminal, needs_password, password)
    elif PLATFORM_CONFIG['package_manager'] == 'dnf':
        return install_prerequisites_dnf(terminal, needs_password, password)
    elif PLATFORM_CONFIG['package_manager'] == 'pacman':
        return install_prerequisites_pacman(terminal, needs_password, password)
    else:
        st.error(f"❌ Unsupported package manager: {PLATFORM_CONFIG['package_manager']}")
        terminal.add_line(f"Unsupported package manager: {PLATFORM_CONFIG['package_manager']}", "error")
        return False

def install_prerequisites_apt(terminal, needs_password, password):
    """Install prerequisites using apt (Ubuntu/Debian)"""
    # Update package list
    st.info("📦 Updating package list...")
    if needs_password:
        result = run_sudo_command_with_password("apt update", password, timeout=60)
    else:
        result = run_shell_command_with_output("sudo apt update", timeout=60)
    
    if not result['success']:
        st.error("❌ Failed to update package list.")
        terminal.add_line("Failed to update package list", "error")
        return False
    
    st.success("✅ Package list updated!")
    
    # Install system packages
    packages = PLATFORM_CONFIG['system_packages']
    st.info("🔧 Installing system packages...")
    all_packages = " ".join(packages)
    
    if needs_password:
        result = run_sudo_command_with_password(f"apt install -y {all_packages}", password, timeout=300)
    else:
        result = run_shell_command_with_output(f"sudo apt install -y {all_packages}", timeout=300)
    
    if not result['success']:
        st.warning("⚠️ Some system packages may have failed to install. Trying individual packages...")
        terminal.add_line("Trying individual package installation...", "info")
        for package in packages:
            st.info(f"Installing {package}...")
            if needs_password:
                result = run_sudo_command_with_password(f"apt install -y {package}", password, timeout=60)
            else:
                result = run_shell_command_with_output(f"sudo apt install -y {package}", timeout=60)
            if not result['success']:
                st.warning(f"Failed to install {package}")
                terminal.add_line(f"Failed to install {package}", "error")
            else:
                st.success(f"✅ {package} installed!")
    else:
        st.success("✅ All system packages installed!")
    
    # Install yt-dlp
    st.info("🎥 Installing yt-dlp...")
    result = run_shell_command_with_output("pip3 install --user yt-dlp", timeout=120)
    if not result['success']:
        st.warning("Failed to install yt-dlp via pip3")
        terminal.add_line("Failed to install yt-dlp", "error")
    else:
        st.success("✅ yt-dlp installed!")
        terminal.add_line("yt-dlp installed successfully", "info")
    
    terminal.add_line("Linux prerequisites installation completed!", "info")
    st.success("🎉 Prerequisites installation completed!")
    return True

def install_prerequisites_dnf(terminal, needs_password, password):
    """Install prerequisites using dnf (Fedora/RHEL/CentOS)"""
    # Update package list
    st.info("📦 Updating package list...")
    if needs_password:
        result = run_sudo_command_with_password("dnf update -y", password, timeout=60)
    else:
        result = run_shell_command_with_output("sudo dnf update -y", timeout=60)
    
    if not result['success']:
        st.warning("⚠️ Package list update failed, continuing...")
    
    # Install system packages
    packages = PLATFORM_CONFIG['system_packages']
    st.info("🔧 Installing system packages...")
    all_packages = " ".join(packages)
    
    if needs_password:
        result = run_sudo_command_with_password(f"dnf install -y {all_packages}", password, timeout=300)
    else:
        result = run_shell_command_with_output(f"sudo dnf install -y {all_packages}", timeout=300)
    
    if not result['success']:
        st.warning("⚠️ Some system packages may have failed to install. Trying individual packages...")
        for package in packages:
            st.info(f"Installing {package}...")
            if needs_password:
                result = run_sudo_command_with_password(f"dnf install -y {package}", password, timeout=60)
            else:
                result = run_shell_command_with_output(f"sudo dnf install -y {package}", timeout=60)
            if not result['success']:
                st.warning(f"Failed to install {package}")
            else:
                st.success(f"✅ {package} installed!")
    else:
        st.success("✅ All system packages installed!")
    
    # Install yt-dlp
    st.info("🎥 Installing yt-dlp...")
    result = run_shell_command_with_output("pip3 install --user yt-dlp", timeout=120)
    if not result['success']:
        st.warning("Failed to install yt-dlp via pip3")
    else:
        st.success("✅ yt-dlp installed!")
    
    terminal.add_line("Linux prerequisites installation completed!", "info")
    st.success("🎉 Prerequisites installation completed!")
    return True

def install_prerequisites_pacman(terminal, needs_password, password):
    """Install prerequisites using pacman (Arch Linux)"""
    # Update package list
    st.info("📦 Updating package list...")
    if needs_password:
        result = run_sudo_command_with_password("pacman -Sy", password, timeout=60)
    else:
        result = run_shell_command_with_output("sudo pacman -Sy", timeout=60)
    
    if not result['success']:
        st.warning("⚠️ Package list update failed, continuing...")
    
    # Install system packages
    packages = PLATFORM_CONFIG['system_packages']
    st.info("🔧 Installing system packages...")
    all_packages = " ".join(packages)
    
    if needs_password:
        result = run_sudo_command_with_password(f"pacman -S --noconfirm {all_packages}", password, timeout=300)
    else:
        result = run_shell_command_with_output(f"sudo pacman -S --noconfirm {all_packages}", timeout=300)
    
    if not result['success']:
        st.warning("⚠️ Some system packages may have failed to install. Trying individual packages...")
        for package in packages:
            st.info(f"Installing {package}...")
            if needs_password:
                result = run_sudo_command_with_password(f"pacman -S --noconfirm {package}", password, timeout=60)
            else:
                result = run_shell_command_with_output(f"sudo pacman -S --noconfirm {package}", timeout=60)
            if not result['success']:
                st.warning(f"Failed to install {package}")
            else:
                st.success(f"✅ {package} installed!")
    else:
        st.success("✅ All system packages installed!")
    
    # Install yt-dlp
    st.info("🎥 Installing yt-dlp...")
    result = run_shell_command_with_output("pip install --user yt-dlp", timeout=120)
    if not result['success']:
        st.warning("Failed to install yt-dlp via pip")
    else:
        st.success("✅ yt-dlp installed!")
    
    terminal.add_line("Linux prerequisites installation completed!", "info")
    st.success("🎉 Prerequisites installation completed!")
    return True

def install_prerequisites_windows(terminal):
    """Install prerequisites on Windows using Chocolatey"""
    st.info("🪟 Installing prerequisites on Windows...")
    
    # Check if Chocolatey is installed
    choco_check = run_shell_command("choco --version", timeout=5)
    if not choco_check['success']:
        st.warning("⚠️ Chocolatey not found. Please install it from https://chocolatey.org/install")
        terminal.add_line("Chocolatey not found", "error")
        return False
    
    # Install packages via Chocolatey
    packages = PLATFORM_CONFIG['system_packages']
    st.info("🔧 Installing system packages via Chocolatey...")
    
    for package in packages:
        st.info(f"Installing {package}...")
        result = run_shell_command_with_output(f"choco install -y {package}", timeout=120)
        
        if not result['success']:
            st.warning(f"Failed to install {package}")
            terminal.add_line(f"Failed to install {package}", "error")
        else:
            st.success(f"✅ {package} installed!")
            terminal.add_line(f"Successfully installed {package}", "info")
    
    # Install yt-dlp
    st.info("🎥 Installing yt-dlp...")
    result = run_shell_command_with_output("pip install --user yt-dlp", timeout=120)
    if not result['success']:
        st.warning("Failed to install yt-dlp via pip")
        terminal.add_line("Failed to install yt-dlp", "error")
    else:
        st.success("✅ yt-dlp installed!")
        terminal.add_line("yt-dlp installed successfully", "info")
    
    terminal.add_line("Windows prerequisites installation completed!", "info")
    st.success("🎉 Prerequisites installation completed!")
    return True

def detect_hardware_acceleration() -> Dict[str, bool]:
    """Detect available hardware acceleration using shell commands.
    
    Returns:
        Dict mapping acceleration types to their availability status.
    """
    acceleration = {
        'nvenc': False,
        'qsv': False,
        'vaapi': False,
        'videotoolbox': False,  # VideoToolbox uses Metal GPU on macOS
        'cpu': True
    }
    
    # Check FFmpeg hardware acceleration methods
    hwaccel_result = run_shell_command("ffmpeg -hide_banner -hwaccels 2>/dev/null")
    if hwaccel_result['success']:
        hwaccels = hwaccel_result['stdout']
        
        # Check for VideoToolbox (macOS) - uses Metal GPU
        if 'videotoolbox' in hwaccels and PLATFORM_CONFIG['is_macos']:
            acceleration['videotoolbox'] = True
    
    # Check FFmpeg encoders
    result = run_shell_command("ffmpeg -hide_banner -encoders 2>/dev/null")
    if result['success']:
        encoders = result['stdout']
        
        # NVIDIA NVENC (Linux/Windows)
        acceleration['nvenc'] = 'h264_nvenc' in encoders or 'hevc_nvenc' in encoders
        
        # Intel QSV (Linux/Windows)
        acceleration['qsv'] = 'h264_qsv' in encoders or 'hevc_qsv' in encoders
        
        # VA-API (Linux)
        acceleration['vaapi'] = 'h264_vaapi' in encoders or 'hevc_vaapi' in encoders
        
        # VideoToolbox (macOS) - verify encoders are available
        if PLATFORM_CONFIG['is_macos']:
            acceleration['videotoolbox'] = acceleration['videotoolbox'] and ('h264_videotoolbox' in encoders or 'hevc_videotoolbox' in encoders)
    
    # Check for Metal filters (macOS)
    if PLATFORM_CONFIG['is_macos']:
        filters_result = run_shell_command("ffmpeg -hide_banner -filters 2>/dev/null")
        if filters_result['success']:
            filters = filters_result['stdout']
            # Metal is automatically available through VideoToolbox on macOS
    
    # Test NVIDIA GPU availability (not just nvidia-smi)
    if acceleration['nvenc']:
        # Test if NVENC actually works
        test_result = run_shell_command("ffmpeg -f lavfi -i testsrc=duration=1:size=320x240:rate=1 -c:v h264_nvenc -f null - 2>&1")
        if not test_result['success'] or 'No capable devices found' in test_result['stderr']:
            acceleration['nvenc'] = False
    
    # Test VideoToolbox on macOS
    if acceleration['videotoolbox'] and PLATFORM_CONFIG['is_macos']:
        test_result = run_shell_command("ffmpeg -f lavfi -i testsrc=duration=1:size=320x240:rate=1 -c:v h264_videotoolbox -q:v 20 -f null - 2>&1")
        if not test_result['success'] or 'No capable devices found' in test_result['stderr']:
            acceleration['videotoolbox'] = False
    
    return acceleration

# --- DOWNLOAD FUNCTIONS ---
async def fetch_youtube_video_links(url, audio_only=False, playlist_limit=None):
    """Fetch YouTube video links using yt-dlp"""
    cache_key = f"{url}_{audio_only}_{playlist_limit}"
    if hasattr(st.session_state, 'youtube_cache') and cache_key in st.session_state.youtube_cache:
        return st.session_state.youtube_cache[cache_key]
    
    # Use yt-dlp command line
    cmd_parts = ["yt-dlp", "--flat-playlist", "--dump-json"]
    
    if audio_only:
        cmd_parts.extend(["--extract-audio", "--audio-format", "mp3"])
    
    if playlist_limit:
        cmd_parts.extend(["--playlist-end", str(playlist_limit)])
    
    cmd_parts.append(url)
    
    result = run_shell_command(" ".join(cmd_parts), timeout=60)
    
    if not result['success']:
        st.error(f"Failed to fetch YouTube links: {result['stderr']}")
        return [], None
    
    try:
        # Parse yt-dlp output
        lines = result['stdout'].strip().split('\n')
        files = []
        playlist_title = "YouTube_Playlist"
        
        for line in lines:
            if line.strip():
                try:
                    data = json.loads(line)
                    title = data.get('title', 'Unknown')
                    webpage_url = data.get('webpage_url', data.get('url', ''))
                    artist = data.get('uploader', '')
                    
                    if artist:
                        base_name = f"{artist} - {title}"
                    else:
                        base_name = title
                    
                    safe_name = normalize_filename(base_name)
                    files.append({
                        'name': safe_name + ('.mp3' if audio_only else '.mp4'),
                        'url': webpage_url,
                        'yt_webpage_url': webpage_url,
                        'is_youtube': True,
                        'is_audio': audio_only,
                        'needs_url_extraction': True,
                        'thumbnail_url': data.get('thumbnail'),
                        'video_id': data.get('id'),
                        'artist': artist,
                        'title': title
                    })
                    
                    # Get playlist title from first entry
                    if not playlist_title or playlist_title == "YouTube_Playlist":
                        playlist_title = data.get('playlist_title', data.get('title', 'YouTube_Playlist'))
                        
                except json.JSONDecodeError:
                    continue
        
        # Cache the result
        if not hasattr(st.session_state, 'youtube_cache'):
            st.session_state.youtube_cache = {}
        st.session_state.youtube_cache[cache_key] = (files, playlist_title)
        
        return files, playlist_title
        
    except Exception as e:
        st.error(f"Error parsing YouTube data: {e}")
        return [], None

async def fetch_video_links(url, audio_only=False, playlist_limit=None):
    """Fetch video links from URL"""
    if is_youtube_url(url):
        return await fetch_youtube_video_links(url, audio_only, playlist_limit)
    
    # For direct file links
    if url.lower().endswith(VIDEO_EXTENSIONS + AUDIO_EXTENSIONS):
        filename = urllib.parse.unquote(os.path.basename(url))
        return [{
            'name': filename,
            'url': url,
            'is_audio': audio_only and url.lower().endswith(AUDIO_EXTENSIONS)
        }], None
    
    # For directory listings
    timeout = aiohttp.ClientTimeout(total=30)
    if not url.endswith('/'):
        url = url + '/'
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            links = soup.find_all('a')
            files = []
            
            for link in links:
                if isinstance(link, Tag):
                    href = link.get('href')
                    if href and isinstance(href, str):
                        if audio_only:
                            if href.lower().endswith(AUDIO_EXTENSIONS):
                                name = urllib.parse.unquote(os.path.basename(href))
                                files.append({'name': name, 'url': urllib.parse.urljoin(url, href), 'is_audio': True})
                        else:
                            if href.lower().endswith(VIDEO_EXTENSIONS):
                                name = urllib.parse.unquote(os.path.basename(href))
                                files.append({'name': name, 'url': urllib.parse.urljoin(url, href), 'is_audio': False})
            
            return files, None

def download_file_with_shell(file_url, file_path, file_info=None, progress_callback=None):
    """Download file using shell commands (wget, curl, or yt-dlp) with progress tracking"""
    file_dir = os.path.dirname(file_path)
    os.makedirs(file_dir, exist_ok=True)
    
    # For YouTube videos, use yt-dlp with progress
    if file_info and file_info.get('is_youtube'):
        if file_info.get('is_audio'):
            cmd = f"yt-dlp --progress -x --audio-format mp3 -o '{file_path}' '{file_info['yt_webpage_url']}'"
        else:
            cmd = f"yt-dlp --progress -f 'best[ext=mp4]/best' -o '{file_path}' '{file_info['yt_webpage_url']}'"
    else:
        # For direct downloads, try wget first, then curl
        if check_command_exists('wget'):
            cmd = f"wget --progress=bar:force -O '{file_path}' '{file_url}'"
        elif check_command_exists('curl'):
            cmd = f"curl -L --progress-bar -o '{file_path}' '{file_url}'"
        else:
            return False, "Neither wget nor curl available"
    
    # Use the output version to capture progress
    result = run_shell_command_with_output(cmd, timeout=600, show_in_terminal=True)
    return result['success'], result['stderr']

def download_all_files(files, selected, download_dir, status_dict):
    """Download all selected files using shell commands with concurrency control"""
    max_concurrency = st.session_state.get('max_concurrency', -1)
    
    # Handle edge cases
    if max_concurrency == 0:
        # Downloads disabled
        for file in files:
            if file['name'] in selected:
                status_dict[file['name']] = {'status': 'downloads disabled', 'progress': 0}
        return None
    elif max_concurrency == -1:
        # Unlimited - use number of selected files or reasonable default
        max_workers = min(len(selected), 20)  # Cap at 20 for system stability
    else:
        # Use specified limit
        max_workers = max(1, max_concurrency)
    
    def download_single_file(file):
        """Download a single file"""
        if file['name'] not in selected:
            return
            
        file_path = os.path.join(download_dir, file['name'])
        file_key = file['name']
        
        # Check if file already exists
        if os.path.exists(file_path) and os.path.getsize(file_path) > 1024:
            status_dict[file_key] = {'status': 'already downloaded', 'progress': 100}
            return
        
        status_dict[file_key] = {'status': 'downloading', 'progress': 0}
        
        # Ensure terminal_output exists in session state
        if 'terminal_output' not in st.session_state:
            st.session_state.terminal_output = TerminalOutput()
        
        # Start download with progress tracking
        import threading
        import time
        
        def update_progress():
            """Update progress during download with speed and ETA calculation"""
            start_time = time.time()
            last_progress = 0
            last_size = 0
            last_update_time = start_time
            
            while status_dict[file_key]['status'] == 'downloading':
                if os.path.exists(file_path):
                    current_size = os.path.getsize(file_path)
                    current_time = time.time()
                    elapsed = current_time - start_time
                    
                    # Calculate download speed
                    if current_time - last_update_time > 0.5:  # Update every 0.5 seconds
                        size_diff = current_size - last_size
                        time_diff = current_time - last_update_time
                        speed = size_diff / time_diff if time_diff > 0 else 0
                        
                        # Estimate progress based on time elapsed (more realistic)
                        # Assume average download takes 60 seconds for better estimation
                        progress = min(95, int((elapsed / 60) * 100))
                        
                        # Calculate ETA based on current speed
                        if speed > 0:
                            # Estimate total size based on current progress
                            estimated_total = current_size / (progress / 100) if progress > 0 else current_size * 2
                            remaining = max(0, estimated_total - current_size)
                            eta = remaining / speed if speed > 0 else 0
                        else:
                            eta = 0
                        
                        # Only update if progress changed significantly (reduce flashing)
                        if progress - last_progress >= 2 or progress == 95:
                            status_dict[file_key].update({
                                'progress': progress,
                                'downloaded': current_size,
                                'speed': speed,
                                'eta': eta,
                                'elapsed': elapsed
                            })
                            last_progress = progress
                        
                        last_size = current_size
                        last_update_time = current_time
                
                time.sleep(0.5)  # Check more frequently for better updates
        
        # Start progress tracking thread
        progress_thread = threading.Thread(target=update_progress, daemon=True)
        progress_thread.start()
        
        success, error = download_file_with_shell(file['url'], file_path, file, progress_callback=None)
        
        if success:
            status_dict[file_key] = {'status': 'completed', 'progress': 100}
        else:
            status_dict[file_key] = {'status': f'error: {error}', 'progress': 0}
    
    def download_worker():
        """Worker function that manages concurrent downloads"""
        import concurrent.futures
        import threading
        
        # Get files to download
        files_to_download = [f for f in files if f['name'] in selected]
        
        if not files_to_download:
            return
        
        # Use ThreadPoolExecutor for controlled concurrency
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all download tasks
            future_to_file = {executor.submit(download_single_file, file): file for file in files_to_download}
            
            # Wait for completion
            for future in concurrent.futures.as_completed(future_to_file):
                file = future_to_file[future]
                try:
                    future.result()  # Get result to catch any exceptions
                except Exception as e:
                    # Handle any unexpected errors
                    status_dict[file['name']] = {'status': f'error: {str(e)}', 'progress': 0}
    
    # Start the download worker thread
    thread = threading.Thread(target=download_worker, daemon=True)
    thread.start()
    return thread

async def prepare_streaming_urls(files, selected, download_dir):
    """Prepare URLs for streaming, prioritizing local files over network streams"""
    urls = []
    names = []
    
    # Ensure terminal_output exists in session state
    if 'terminal_output' not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()
    
    terminal = st.session_state.terminal_output
    
    for file in files:
        if file['name'] in selected:
            names.append(file['name'])
            
            # First, check if file exists locally (prioritize local files)
            local_file_path = os.path.join(download_dir, normalize_filename(file['name']))
            
            if os.path.exists(local_file_path) and os.path.getsize(local_file_path) > 1024:
                # File exists locally and has reasonable size - stream from local
                urls.append(f"file://{os.path.abspath(local_file_path)}")
                terminal.add_line(f"Using local file: {file['name']}", "info")
            else:
                # File not downloaded or incomplete - stream from network
                terminal.add_line(f"Streaming from network: {file['name']}", "info")
                
                # Get the actual URL for YouTube videos that need extraction
                if file.get('needs_url_extraction') and file.get('is_youtube'):
                    direct_url = await get_youtube_direct_url(file['yt_webpage_url'], file.get('is_audio', False))
                    urls.append(direct_url)
                else:
                    urls.append(file['url'])
    
    return urls, names

async def get_youtube_direct_url(webpage_url, audio_only=False):
    """Extract direct URL for a YouTube video when needed"""
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'format': 'bestaudio[ext=mp3]/bestaudio/best' if audio_only else 'best[ext=mp4]/best',
    }
    
    loop = asyncio.get_event_loop()
    def run_yt():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(webpage_url, download=False)
            if isinstance(info, dict) and 'url' in info:
                return info['url']
            return webpage_url
    return await loop.run_in_executor(None, run_yt)

def stream_all_in_vlc(urls, names):
    """Stream files in VLC media player"""
    # Ensure terminal_output exists in session state
    if 'terminal_output' not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()
    
    terminal = st.session_state.terminal_output
    terminal.add_line(f"Starting VLC streaming for {len(urls)} files", "info")
    
    try:
        if sys.platform == "darwin":  # macOS
            with tempfile.NamedTemporaryFile('w', suffix='.m3u', delete=False) as m3u:
                for name, url in zip(names, urls):
                    m3u.write(f'#EXTINF:-1,{name}\n{url}\n')
                m3u_path = m3u.name
            subprocess.Popen(["open", "-a", "VLC", m3u_path])
            terminal.add_line("Launched VLC on macOS", "info")
            
        elif sys.platform == "win32":  # Windows
            subprocess.Popen(["vlc"] + urls)
            terminal.add_line("Launched VLC on Windows", "info")
            
        else:  # Linux
            vlc_paths = ["vlc", "/snap/bin/vlc", "/usr/bin/vlc", "/usr/local/bin/vlc"]
            vlc_found = False
            
            for vlc_path in vlc_paths:
                try:
                    result = subprocess.run([vlc_path, "--version"], capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        terminal.add_line(f"Found VLC at: {vlc_path}", "info")
                        
                        # Try different interfaces
                        vlc_interfaces = ["qt", "dummy"]
                        for interface in vlc_interfaces:
                            try:
                                vlc_args = [vlc_path, "--intf", interface]
                                if interface == "qt":
                                    vlc_args.extend(["--no-video-title-show"])
                                vlc_args.extend(urls)
                                
                                env = os.environ.copy()
                                env['DISPLAY'] = ':0'
                                
                                process = subprocess.Popen(
                                    vlc_args, 
                                    stdout=subprocess.PIPE, 
                                    stderr=subprocess.PIPE, 
                                    env=env
                                )
                                
                                time.sleep(2)
                                if process.poll() is None:
                                    terminal.add_line(f"VLC launched successfully with {interface} interface", "info")
                                    vlc_found = True
                                    break
                                    
                            except Exception as e:
                                terminal.add_line(f"Failed to launch VLC with {interface}: {e}", "error")
                                continue
                        
                        if vlc_found:
                            break
                            
                except Exception as e:
                    continue
            
            if not vlc_found:
                raise Exception("VLC not found. Please install VLC: sudo apt install vlc")
                
    except Exception as e:
        terminal.add_line(f"VLC streaming error: {e}", "error")
        st.error(f"Failed to open VLC: {e}")
        st.info("Make sure VLC is installed. On Linux: `sudo apt install vlc`")

# --- VIDEO ENCODING FUNCTIONS ---
def create_video_encoder_script(download_dir):
    """Create the video encoder script in the download directory"""
    script_path = os.path.join(download_dir, "video_encoder.sh")
    
    if not os.path.exists(script_path):
        # Copy the original script
        original_script = os.path.join(os.path.dirname(__file__), "original", "video_encoder.sh")
        if os.path.exists(original_script):
            try:
                shutil.copy2(original_script, script_path)
                os.chmod(script_path, 0o755)
                st.info(f"✅ Video encoder script copied to {script_path}")
                return True
            except Exception as e:
                st.error(f"Failed to copy video encoder script: {e}")
                return False
        else:
            st.warning(f"Original video encoder script not found at {original_script}")
            # Try to find it in the current directory
            current_script = os.path.join(os.getcwd(), "video_encoder.sh")
            if os.path.exists(current_script):
                try:
                    shutil.copy2(current_script, script_path)
                    os.chmod(script_path, 0o755)
                    st.info(f"✅ Video encoder script copied from current directory")
                    return True
                except Exception as e:
                    st.error(f"Failed to copy video encoder script: {e}")
                    return False
    return os.path.exists(script_path)

def list_video_files(download_dir):
    """List video files in directory using shell commands"""
    result = run_shell_command(f"find '{download_dir}' -maxdepth 1 -name '*.mp4' -o -name '*.mkv' -o -name '*.avi' -o -name '*.mov' -o -name '*.wmv' -o -name '*.flv' -o -name '*.webm' | sort -V")
    
    if result['success']:
        files = [f.strip() for f in result['stdout'].split('\n') if f.strip()]
        return files
    return []

def get_video_info(file_path):
    """Get video information using ffprobe"""
    cmd = f"ffprobe -v quiet -print_format json -show_format -show_streams '{file_path}'"
    result = run_shell_command(cmd)
    
    if result['success']:
        try:
            data = json.loads(result['stdout'])
            video_stream = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), None)
            if video_stream:
                return f"{video_stream.get('width', '?')}x{video_stream.get('height', '?')} - {video_stream.get('codec_name', '?')}"
        except:
            pass
    return "Unknown"

def get_video_duration_seconds(file_path):
    """Get total duration in seconds using ffprobe."""
    cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 '{file_path}'"
    result = run_shell_command(cmd)
    if result['success']:
        try:
            return float(result['stdout'].strip())
        except Exception:
            return None
    return None

def trim_video_remove_segments(src_path, intro_range=None, outro_range=None, work_dir=None, return_removed=False):
    """
    Create a trimmed copy of src_path that removes [intro_start,intro_end] and [outro_start,outro_end].
    - intro_range/outro_range: tuples of (start_sec, end_sec) relative to episode. Use None to skip.
    Returns (success, trimmed_path or error_message)
    """
    # Ensure terminal_output exists in session state
    if 'terminal_output' not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()
    terminal = st.session_state.terminal_output

    duration = get_video_duration_seconds(src_path)
    if duration is None or duration <= 0:
        return False, "Could not determine duration"

    # Normalize and clamp ranges
    keep_segments = []
    removed_segments = []
    # Start before intro
    if intro_range and len(intro_range) == 2:
        i_start = max(0.0, float(intro_range[0]))
        i_end = min(duration, float(intro_range[1]))
        if i_start > 0.25:  # keep tiny heads only if meaningful
            keep_segments.append((0.0, max(0.0, i_start)))
        # removed intro chunk
        if i_end > i_start:
            removed_segments.append((i_start, i_end))
    else:
        # No intro removal, keep from 0 until possibly outro
        pass

    # Middle between intro end and outro start
    if intro_range and len(intro_range) == 2:
        i_end = min(duration, float(intro_range[1]))
        mid_start = i_end
    else:
        mid_start = 0.0

    if outro_range and len(outro_range) == 2:
        o_start = max(0.0, float(outro_range[0]))
        if o_start > mid_start + 0.25:
            keep_segments.append((mid_start, min(duration, o_start)))
    else:
        if duration > mid_start + 0.25:
            keep_segments.append((mid_start, duration))

    # Tail after outro
    if outro_range and len(outro_range) == 2:
        o_end = min(duration, float(outro_range[1]))
        if duration > o_end + 0.25:
            keep_segments.append((o_end, duration))
        # removed outro chunk
        o_start = max(0.0, float(outro_range[0]))
        if o_end > o_start:
            removed_segments.append((o_start, o_end))

    # If no actual removal, just return original
    total_kept = sum(max(0.0, b - a) for a, b in keep_segments)
    if total_kept <= 0.5 or (len(keep_segments) == 1 and abs(keep_segments[0][0] - 0.0) < 1e-3 and abs(keep_segments[0][1] - duration) < 1e-3):
        return True, src_path

    # Prepare output paths
    base_dir = work_dir or os.path.dirname(src_path)
    trimmed_dir = os.path.join(base_dir, "trimmed")
    os.makedirs(trimmed_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(src_path))[0]
    part_paths = []
    removed_paths = []

    # Extract parts
    for idx, (start_t, end_t) in enumerate(keep_segments):
        part_out = os.path.join(trimmed_dir, f"{base_name}.part{idx+1}.mp4")
        # Use stream copy where possible; accuracy depends on keyframes
        cmd = (
            f"ffmpeg -y -ss {start_t:.3f} -to {end_t:.3f} -i '{src_path}' -c copy '{part_out}' 2>&1"
        )
        res = run_shell_command_with_output(cmd, timeout=1800)
        if not res['success'] or not os.path.exists(part_out) or os.path.getsize(part_out) == 0:
            # Fallback to fast re-encode for the segment
            cmd2 = (
                f"ffmpeg -y -ss {start_t:.3f} -to {end_t:.3f} -i '{src_path}' -c:v libx264 -preset veryfast -crf 20 -c:a copy '{part_out}' 2>&1"
            )
            res2 = run_shell_command_with_output(cmd2, timeout=1800)
            if not res2['success']:
                return False, f"Failed to create segment {idx+1}"
        part_paths.append(part_out)

    # Concat parts into one trimmed file
    list_file = os.path.join(trimmed_dir, f"{base_name}_parts.txt")
    with open(list_file, 'w') as lf:
        for p in part_paths:
            esc = p.replace("'", "'\"'\"'")
            lf.write(f"file '{esc}'\n")
    trimmed_out = os.path.join(trimmed_dir, f"{base_name}.trimmed.mp4")
    concat_cmd = f"ffmpeg -y -f concat -safe 0 -i '{list_file}' -c copy '{trimmed_out}' 2>&1"
    resc = run_shell_command_with_output(concat_cmd, timeout=1800)
    if not resc['success'] or not os.path.exists(trimmed_out) or os.path.getsize(trimmed_out) == 0:
        # Fallback to re-encode on concat
        concat_cmd2 = f"ffmpeg -y -f concat -safe 0 -i '{list_file}' -c:v libx264 -preset veryfast -crf 20 -c:a copy '{trimmed_out}' 2>&1"
        resc2 = run_shell_command_with_output(concat_cmd2, timeout=1800)
        if not resc2['success']:
            return False, "Failed to concat trimmed parts"

    # Optionally extract removed segments for verification
    if return_removed and removed_segments:
        removed_dir = os.path.join(base_dir, "removed")
        os.makedirs(removed_dir, exist_ok=True)
        for idx, (start_t, end_t) in enumerate(removed_segments):
            r_out = os.path.join(removed_dir, f"{base_name}.removed{idx+1}.mp4")
            cmdr = (
                f"ffmpeg -y -ss {start_t:.3f} -to {end_t:.3f} -i '{src_path}' -c copy '{r_out}' 2>&1"
            )
            resr = run_shell_command_with_output(cmdr, timeout=1800)
            if (not resr['success']) or (not os.path.exists(r_out)) or (os.path.getsize(r_out) == 0):
                cmdr2 = (
                    f"ffmpeg -y -ss {start_t:.3f} -to {end_t:.3f} -i '{src_path}' -c:v libx264 -preset veryfast -crf 20 -c:a copy '{r_out}' 2>&1"
                )
                resr2 = run_shell_command_with_output(cmdr2, timeout=1800)
                if not resr2['success']:
                    # skip this removed part on failure
                    continue
            removed_paths.append(r_out)

    return (True, trimmed_out, removed_paths) if return_removed else (True, trimmed_out)

def extract_audio_for_analysis(video_path, work_dir=None):
    """Extract low-rate mono audio for similarity analysis"""
    if 'terminal_output' not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()
    terminal = st.session_state.terminal_output
    
    work_dir = work_dir or os.path.dirname(video_path)
    audio_dir = os.path.join(work_dir, "analysis_audio")
    os.makedirs(audio_dir, exist_ok=True)
    
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    audio_path = os.path.join(audio_dir, f"{base_name}.wav")
    
    # Extract 16kHz mono audio for analysis
    cmd = f"ffmpeg -y -i '{video_path}' -ar 16000 -ac 1 -f wav '{audio_path}' 2>&1"
    result = run_shell_command_with_output(cmd, timeout=300)
    
    if result['success'] and os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
        return audio_path
    return None

def analyze_audio_similarity(audio_paths, sample_duration=30):
    """
    Analyze audio similarity to detect intro/outro patterns.
    Returns (intro_range, outro_range, confidence_scores)
    """
    if len(audio_paths) < 2:
        return None, None, (0, 0)
    
    if 'terminal_output' not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()
    terminal = st.session_state.terminal_output
    
    terminal.add_line(f"Analyzing {len(audio_paths)} audio files for patterns...", "info")
    
    try:
        # Load and analyze first few files
        audio_data = []
        durations = []
        
        for i, audio_path in enumerate(audio_paths[:min(5, len(audio_paths))]):  # Analyze up to 5 files
            if not os.path.exists(audio_path):
                continue
                
            y, sr = librosa.load(audio_path, sr=16000)
            audio_data.append(y)
            durations.append(len(y) / sr)
            
            if i == 0:
                terminal.add_line(f"Loaded audio: {len(y)/sr:.1f}s at {sr}Hz", "info")
        
        if len(audio_data) < 2:
            return None, None, (0, 0)
        
        # Find intro pattern (first 30-90 seconds)
        intro_candidates = []
        outro_candidates = []
        
        # Analyze intro (first 30-90 seconds)
        for start_time in range(0, min(90, int(min(durations))), 10):
            end_time = min(start_time + sample_duration, int(min(durations)))
            if end_time - start_time < 20:  # Need at least 20s
                continue
                
            similarities = []
            for i in range(len(audio_data)):
                for j in range(i+1, len(audio_data)):
                    # Extract segments
                    start_sample = int(start_time * 16000)
                    end_sample = int(end_time * 16000)
                    
                    seg1 = audio_data[i][start_sample:end_sample]
                    seg2 = audio_data[j][start_sample:end_sample]
                    
                    if len(seg1) > 0 and len(seg2) > 0:
                        # Use MFCC features for comparison
                        mfcc1 = librosa.feature.mfcc(y=seg1, sr=16000, n_mfcc=13)
                        mfcc2 = librosa.feature.mfcc(y=seg2, sr=16000, n_mfcc=13)
                        
                        # Compare MFCCs
                        if mfcc1.shape[1] > 0 and mfcc2.shape[1] > 0:
                            # Pad to same length
                            max_len = max(mfcc1.shape[1], mfcc2.shape[1])
                            mfcc1_padded = np.pad(mfcc1, ((0,0), (0, max_len - mfcc1.shape[1])), mode='constant')
                            mfcc2_padded = np.pad(mfcc2, ((0,0), (0, max_len - mfcc2.shape[1])), mode='constant')
                            
                            # Calculate cosine similarity
                            sim = 1 - cosine(mfcc1_padded.flatten(), mfcc2_padded.flatten())
                            similarities.append(sim)
            
            if similarities:
                avg_similarity = np.mean(similarities)
                intro_candidates.append((start_time, end_time, avg_similarity))
        
        # Analyze outro (last 30-90 seconds)
        for end_time in range(int(min(durations)), max(0, int(min(durations)) - 90), -10):
            start_time = max(0, end_time - sample_duration)
            if end_time - start_time < 20:  # Need at least 20s
                continue
                
            similarities = []
            for i in range(len(audio_data)):
                for j in range(i+1, len(audio_data)):
                    # Extract segments
                    start_sample = int(start_time * 16000)
                    end_sample = int(end_time * 16000)
                    
                    seg1 = audio_data[i][start_sample:end_sample]
                    seg2 = audio_data[j][start_sample:end_sample]
                    
                    if len(seg1) > 0 and len(seg2) > 0:
                        # Use MFCC features for comparison
                        mfcc1 = librosa.feature.mfcc(y=seg1, sr=16000, n_mfcc=13)
                        mfcc2 = librosa.feature.mfcc(y=seg2, sr=16000, n_mfcc=13)
                        
                        # Compare MFCCs
                        if mfcc1.shape[1] > 0 and mfcc2.shape[1] > 0:
                            # Pad to same length
                            max_len = max(mfcc1.shape[1], mfcc2.shape[1])
                            mfcc1_padded = np.pad(mfcc1, ((0,0), (0, max_len - mfcc1.shape[1])), mode='constant')
                            mfcc2_padded = np.pad(mfcc2, ((0,0), (0, max_len - mfcc2.shape[1])), mode='constant')
                            
                            # Calculate cosine similarity
                            sim = 1 - cosine(mfcc1_padded.flatten(), mfcc2_padded.flatten())
                            similarities.append(sim)
            
            if similarities:
                avg_similarity = np.mean(similarities)
                outro_candidates.append((start_time, end_time, avg_similarity))
        
        # Find best intro candidate (highest similarity)
        best_intro = None
        if intro_candidates:
            best_intro = max(intro_candidates, key=lambda x: x[2])
            if best_intro[2] > 0.7:  # High similarity threshold
                terminal.add_line(f"Detected intro: {best_intro[0]:.1f}s-{best_intro[1]:.1f}s (confidence: {best_intro[2]:.2f})", "success")
            else:
                terminal.add_line(f"Intro detection low confidence: {best_intro[2]:.2f}", "warning")
                best_intro = None
        
        # Find best outro candidate (highest similarity)
        best_outro = None
        if outro_candidates:
            best_outro = max(outro_candidates, key=lambda x: x[2])
            if best_outro[2] > 0.7:  # High similarity threshold
                terminal.add_line(f"Detected outro: {best_outro[0]:.1f}s-{best_outro[1]:.1f}s (confidence: {best_outro[2]:.2f})", "success")
            else:
                terminal.add_line(f"Outro detection low confidence: {best_outro[2]:.2f}", "warning")
                best_outro = None
        
        intro_range = (best_intro[0], best_intro[1]) if best_intro else None
        outro_range = (best_outro[0], best_outro[1]) if best_outro else None
        confidence = (best_intro[2] if best_intro else 0, best_outro[2] if best_outro else 0)
        
        return intro_range, outro_range, confidence
        
    except Exception as e:
        terminal.add_line(f"Audio analysis error: {str(e)}", "error")
        return None, None, (0, 0)

def auto_detect_intro_outro(video_files, work_dir):
    """Automatically detect intro/outro segments across multiple video files"""
    if 'terminal_output' not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()
    terminal = st.session_state.terminal_output
    
    terminal.add_line("Starting automatic intro/outro detection...", "info")
    
    # Extract audio from videos
    audio_paths = []
    for video_file in video_files:
        audio_path = extract_audio_for_analysis(video_file, work_dir)
        if audio_path:
            audio_paths.append(audio_path)
    
    if len(audio_paths) < 2:
        terminal.add_line("Need at least 2 videos for pattern detection", "warning")
        return None, None, (0, 0)
    
    # Analyze patterns
    intro_range, outro_range, confidence = analyze_audio_similarity(audio_paths)
    
    return intro_range, outro_range, confidence

def _compute_mfcc(y, sr=16000):
    mf = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    return mf

def _avg_template(segments_mfcc):
    # Pad to max time dimension and average
    max_len = max(m.shape[1] for m in segments_mfcc)
    stacked = []
    for m in segments_mfcc:
        if m.shape[1] < max_len:
            m = np.pad(m, ((0,0),(0,max_len-m.shape[1])), mode='constant')
        stacked.append(m)
    return np.mean(np.stack(stacked, axis=0), axis=0)

def build_intro_outro_templates(audio_paths, intro_range, outro_range, sr=16000):
    """Build MFCC templates for intro and outro by averaging across files"""
    intro_template = None
    outro_template = None
    segments_intro = []
    segments_outro = []
    for path in audio_paths:
        if not os.path.exists(path):
            continue
        y, _sr = librosa.load(path, sr=sr)
        if intro_range:
            s = int(intro_range[0]*sr); e = int(intro_range[1]*sr)
            seg = y[s:e]
            if seg.size > sr*5:
                segments_intro.append(_compute_mfcc(seg, sr))
        if outro_range:
            s = int(outro_range[0]*sr); e = int(outro_range[1]*sr)
            seg = y[s:e]
            if seg.size > sr*5:
                segments_outro.append(_compute_mfcc(seg, sr))
    if segments_intro:
        intro_template = _avg_template(segments_intro)
    if segments_outro:
        outro_template = _avg_template(segments_outro)
    return intro_template, outro_template

def detect_segment_offset(audio_path, template_mfcc, search_start, search_end, sr=16000, hop_seconds=1.0):
    """Slide template over search window; return best (start,end,sim) in seconds."""
    if template_mfcc is None:
        return None
    if not os.path.exists(audio_path):
        return None
    y, _sr = librosa.load(audio_path, sr=sr)
    total_dur = len(y)/sr
    search_start = max(0.0, search_start)
    search_end = min(total_dur, search_end)
    tpl_len_frames = template_mfcc.shape[1]
    # Approximate hop length 512 by default in librosa
    tpl_len_sec = tpl_len_frames * (512/float(sr))
    best_sim = -1.0
    best_start = None
    step = max(1, int(hop_seconds*sr))
    start_idx = int(search_start*sr)
    end_idx = max(start_idx+int(tpl_len_sec*sr), int(search_end*sr))
    for s in range(start_idx, end_idx, step):
        e = s + int(tpl_len_sec*sr)
        if e > len(y):
            break
        seg = y[s:e]
        mf = _compute_mfcc(seg, sr)
        # Pad to same width
        max_len = max(mf.shape[1], template_mfcc.shape[1])
        mf_p = np.pad(mf, ((0,0),(0,max_len-mf.shape[1])), mode='constant')
        tpl_p = np.pad(template_mfcc, ((0,0),(0,max_len-template_mfcc.shape[1])), mode='constant')
        sim = 1 - cosine(mf_p.flatten(), tpl_p.flatten())
        if sim > best_sim:
            best_sim = sim
            best_start = s/float(sr)
    if best_start is None:
        return None
    return (best_start, best_start + tpl_len_sec, best_sim)

def detect_alignment_for_files(video_files, work_dir, intro_range, outro_range):
    """Compute per-file aligned intro/outro ranges and confidence for preview."""
    if 'terminal_output' not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()
    terminal = st.session_state.terminal_output

    results = []
    # Build audio once
    audio_paths = []
    for vf in video_files:
        ap = extract_audio_for_analysis(vf, work_dir)
        audio_paths.append(ap)
    intro_tpl, outro_tpl = build_intro_outro_templates([p for p in audio_paths if p], intro_range, outro_range)

    for idx, vf in enumerate(video_files):
        ap = audio_paths[idx]
        vf_intro = None
        vf_outro = None
        conf_i = 0.0
        conf_o = 0.0
        dur = get_video_duration_seconds(vf) or 0.0
        if ap and intro_tpl is not None:
            det = detect_segment_offset(ap, intro_tpl, 0, min(180.0, dur))
            if det:
                vf_intro = (det[0], det[1])
                conf_i = float(det[2])
        if ap and outro_tpl is not None:
            start_win = max(0.0, dur - 240.0)
            det = detect_segment_offset(ap, outro_tpl, start_win, dur)
            if det:
                vf_outro = (det[0], det[1])
                conf_o = float(det[2])
        results.append({
            'file': os.path.basename(vf),
            'intro': vf_intro,
            'intro_conf': conf_i,
            'outro': vf_outro,
            'outro_conf': conf_o,
        })
    return results

def encode_videos_direct(download_dir, output_file, preset="auto", quality="25", intro_range=None, outro_range=None, per_file_align=False, cleanup_residuals=True, keep_deleted_compilation=False, only_keep_outputs=False):
    """Encode videos directly using FFmpeg commands"""
    # Ensure terminal_output exists in session state
    if 'terminal_output' not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()
    
    terminal = st.session_state.terminal_output
    
    # Find video files
    video_files = list_video_files(download_dir)
    if not video_files:
        return False, "No video files found"
    
    terminal.add_line(f"Found {len(video_files)} video files to merge", "info")
    
    # Optionally trim intro/outro per file
    processed_files = []
    did_trim = False
    if intro_range or outro_range:
        terminal.add_line("Trimming intro/outro segments before merge...", "info")
        
        # If per-file alignment is enabled, build templates then align per episode
        if per_file_align:
            terminal.add_line("Per-episode alignment enabled: building templates...", "info")
            # Build audio paths and templates
            audio_paths = []
            for vf in video_files:
                ap = extract_audio_for_analysis(vf, download_dir)
                if ap:
                    audio_paths.append(ap)
            intro_tpl = None
            outro_tpl = None
            if len(audio_paths) >= 1:
                intro_tpl, outro_tpl = build_intro_outro_templates(audio_paths, intro_range, outro_range)
            # For each file, detect offset for intro/outro within reasonable windows and trim
            for idx, vf in enumerate(video_files):
                ap = audio_paths[idx] if idx < len(audio_paths) else None
                ep_intro = intro_range
                ep_outro = outro_range
                if ap and intro_tpl is not None:
                    # Search intro in first ~180s
                    det = detect_segment_offset(ap, intro_tpl, 0, 180)
                    if det and det[2] > 0.6:
                        ep_intro = (det[0], det[1])
                        terminal.add_line(f"Aligned intro for {os.path.basename(vf)}: {ep_intro[0]:.1f}-{ep_intro[1]:.1f}", "info")
                if ap and outro_tpl is not None:
                    # Search outro in last ~240s window
                    dur = get_video_duration_seconds(vf) or 0
                    start_win = max(0.0, dur - 240)
                    det = detect_segment_offset(ap, outro_tpl, start_win, dur)
                    if det and det[2] > 0.6:
                        ep_outro = (det[0], det[1])
                        terminal.add_line(f"Aligned outro for {os.path.basename(vf)}: {ep_outro[0]:.1f}-{ep_outro[1]:.1f}", "info")
                ok, outp = trim_video_remove_segments(vf, intro_range=ep_intro, outro_range=ep_outro, work_dir=download_dir, return_removed=False)
                if not ok:
                    return False, f"Trimming failed for {os.path.basename(vf)}: {outp}"
                processed_files.append(outp)
                did_trim = True
        else:
            for vf in video_files:
                ok, outp = trim_video_remove_segments(vf, intro_range=intro_range, outro_range=outro_range, work_dir=download_dir, return_removed=False)
                if not ok:
                    return False, f"Trimming failed for {os.path.basename(vf)}: {outp}"
                processed_files.append(outp)
                did_trim = True
    else:
        processed_files = video_files
    
    # Create file list for FFmpeg concat
    list_file = os.path.join(download_dir, "filelist.txt")
    try:
        with open(list_file, 'w') as f:
            for video_file in processed_files:
                # Escape single quotes for FFmpeg
                escaped_file = video_file.replace("'", "'\"'\"'")
                f.write(f"file '{escaped_file}'\n")
    except Exception as e:
        return False, f"Failed to create file list: {e}"
    
    # If preset is 'copy', try zero-reencode paths first
    if preset == "copy":
        output_path = os.path.join(download_dir, output_file)
        # Single file: just copy the (possibly trimmed) file
        if len(processed_files) == 1:
            try:
                shutil.copy2(processed_files[0], output_path)
                terminal.add_line("Copied single file to output (no re-encode)", "success")
                # Optional cleanup
                if cleanup_residuals:
                    try:
                        for d in [os.path.join(download_dir, "trimmed"), os.path.join(download_dir, "analysis_audio")]:
                            if os.path.isdir(d):
                                shutil.rmtree(d, ignore_errors=True)
                    except Exception as e:
                        terminal.add_line(f"Cleanup warning: {e}", "warning")
                return True, ""
            except Exception as e:
                terminal.add_line(f"Copy failed, will try concat/encode: {e}", "warning")
        
        # Multiple files: try concat with stream copy
        copy_cmd = f"ffmpeg -y -f concat -safe 0 -i '{list_file}' -c copy '{output_path}'"
        terminal.add_line("Attempting concat with stream copy (-c copy)", "info")
        copy_result = run_shell_command_with_output(copy_cmd, cwd=download_dir, timeout=3600)
        if copy_result['success']:
            # Clean up list file
            try:
                os.remove(list_file)
            except:
                pass
            # Optional cleanup
            if cleanup_residuals:
                try:
                    for d in [os.path.join(download_dir, "trimmed"), os.path.join(download_dir, "analysis_audio")]:
                        if os.path.isdir(d):
                            shutil.rmtree(d, ignore_errors=True)
                except Exception as e:
                    terminal.add_line(f"Cleanup warning: {e}", "warning")
            return True, ""
        else:
            terminal.add_line("Concat with copy failed; falling back to re-encode for compatibility", "warning")
    
    # Determine encoder based on preset and hardware
    acceleration = detect_hardware_acceleration()
    
    if preset == "auto":
        if acceleration['nvenc']:
            encoder = "hevc_nvenc"
            encoder_opts = f"-c:v {encoder} -preset fast -cq {quality}"
        elif acceleration['videotoolbox'] and PLATFORM_CONFIG['is_macos']:
            encoder = "hevc_videotoolbox"
            encoder_opts = f"-hwaccel videotoolbox -c:v {encoder} -q:v {quality} -prio_speed 1 -spatial_aq 1 -power_efficient 0"
        elif acceleration['qsv']:
            encoder = "hevc_qsv"
            encoder_opts = f"-c:v {encoder} -preset fast -global_quality {quality}"
        elif acceleration['vaapi']:
            encoder = "hevc_vaapi"
            encoder_opts = f"-hwaccel vaapi -vaapi_device /dev/dri/renderD128 -c:v {encoder} -qp {quality}"
        else:
            encoder = "libx265"
            encoder_opts = f"-c:v {encoder} -preset fast -crf {quality}"
    elif preset == "copy":
        # At this point copy failed or was not possible; pick a safe re-encode
        encoder_opts = f"-c:v libx264 -preset fast -crf {quality}"
    elif "nvenc" in preset:
        encoder_opts = f"-c:v {preset.replace('h264_', 'h264_').replace('h265_', 'hevc_')} -preset fast -cq {quality}"
    elif "videotoolbox" in preset:
        if "h264" in preset:
            encoder_opts = f"-hwaccel videotoolbox -c:v h264_videotoolbox -q:v {quality} -prio_speed 1 -spatial_aq 1 -power_efficient 0"
        elif "h265" in preset or "hevc" in preset:
            encoder_opts = f"-hwaccel videotoolbox -c:v hevc_videotoolbox -q:v {quality} -prio_speed 1 -spatial_aq 1 -power_efficient 0"
        else:
            encoder_opts = f"-hwaccel videotoolbox -c:v hevc_videotoolbox -q:v {quality} -prio_speed 1 -spatial_aq 1 -power_efficient 0"
    elif "qsv" in preset:
        encoder_opts = f"-c:v {preset.replace('h265_', 'hevc_')} -preset fast -global_quality {quality}"
    elif "vaapi" in preset:
        encoder_opts = f"-hwaccel vaapi -vaapi_device /dev/dri/renderD128 -c:v {preset.replace('h265_', 'hevc_')} -qp {quality}"
    elif "cpu" in preset:
        if "h264" in preset:
            encoder_opts = f"-c:v libx264 -preset fast -crf {quality}"
        elif "h265" in preset:
            encoder_opts = f"-c:v libx265 -preset fast -crf {quality}"
        elif "av1" in preset:
            encoder_opts = f"-c:v libaom-av1 -crf {quality}"
    else:
        encoder_opts = f"-c:v libx265 -preset fast -crf {quality}"
    
    # Build FFmpeg command
    output_path = os.path.join(download_dir, output_file)
    
    # For VideoToolbox, hwaccel needs to come before input
    if "videotoolbox" in encoder_opts:
        # Use Metal-optimized VideoToolbox with additional GPU acceleration
        cmd = f"ffmpeg -y -hwaccel videotoolbox -f concat -safe 0 -i '{list_file}' {encoder_opts.replace('-hwaccel videotoolbox ', '')} -c:a copy -threads 0 '{output_path}'"
    else:
        cmd = f"ffmpeg -y -f concat -safe 0 -i '{list_file}' {encoder_opts} -c:a copy '{output_path}'"
    
    terminal.add_line(f"Using encoder: {encoder_opts}", "info")
    terminal.add_line(f"Output file: {output_path}", "info")
    
    # Run FFmpeg
    result = run_shell_command_with_output(cmd, cwd=download_dir, timeout=3600)
    
    # If hardware acceleration failed, try CPU fallback
    if not result['success'] and ('No capable devices found' in result['stderr'] or 'OpenEncodeSessionEx failed' in result['stderr'] or 'videotoolbox' in result['stderr'].lower()):
        terminal.add_line("Hardware acceleration failed, trying CPU fallback...", "warning")
        
        # Fallback to CPU encoding
        if preset == "auto" or "nvenc" in preset or "qsv" in preset or "vaapi" in preset or "videotoolbox" in preset:
            if "h264" in preset or preset == "auto":
                fallback_cmd = f"ffmpeg -y -f concat -safe 0 -i '{list_file}' -c:v libx264 -preset fast -crf {quality} -c:a copy '{output_path}'"
            else:
                fallback_cmd = f"ffmpeg -y -f concat -safe 0 -i '{list_file}' -c:v libx265 -preset fast -crf {quality} -c:a copy '{output_path}'"
            
            terminal.add_line(f"Fallback command: {fallback_cmd}", "info")
            result = run_shell_command_with_output(fallback_cmd, cwd=download_dir, timeout=3600)
    
    # Clean up list file (keep trimmed parts for reuse)
    try:
        os.remove(list_file)
    except:
        pass
    
    # If requested, compile deleted parts into a single deleted.mp4 in the download_dir
    deleted_path = None

    # Remove residual temporary artifacts after successful encode
    if result['success'] and cleanup_residuals:
        try:
            tmp_dirs = [
                os.path.join(download_dir, "trimmed"),
                os.path.join(download_dir, "analysis_audio"),
                os.path.join(download_dir, "removed"),
            ]
            for d in tmp_dirs:
                if os.path.isdir(d):
                    terminal.add_line(f"Removing temporary directory: {d}", "info")
                    shutil.rmtree(d, ignore_errors=True)
        except Exception as e:
            terminal.add_line(f"Cleanup warning: {e}", "warning")
    
    # Optionally delete all other video files except the final outputs
    if result['success'] and only_keep_outputs:
        try:
            keep_set = {os.path.join(download_dir, output_file)}
            if deleted_path:
                keep_set.add(deleted_path)
            for entry in os.listdir(download_dir):
                p = os.path.join(download_dir, entry)
                if os.path.isfile(p) and p not in keep_set and entry.lower().endswith(VIDEO_EXTENSIONS):
                    terminal.add_line(f"Removing source video: {entry}", "info")
                    try:
                        os.remove(p)
                    except Exception:
                        pass
        except Exception as e:
            terminal.add_line(f"Final outputs retention warning: {e}", "warning")
    
    # Remove macOS quarantine attribute to prevent security warnings
    if result['success'] and PLATFORM_CONFIG['is_macos']:
        output_path = os.path.join(download_dir, output_file)
        if os.path.exists(output_path):
            try:
                subprocess.run(f"xattr -d com.apple.quarantine '{output_path}'", shell=True, capture_output=True)
                terminal.add_line("🔓 Removed macOS quarantine attribute", "info")
            except:
                pass  # Ignore if xattr fails
    
    return result['success'], result['stderr']

# Keep the old function for backward compatibility
def encode_videos_shell(download_dir, output_file, preset="auto", quality="25"):
    """Encode videos using direct FFmpeg commands (no shell script needed)"""
    return encode_videos_direct(download_dir, output_file, preset, quality)

# --- STREAMLIT UI ---
def main():
    st.set_page_config(
        page_title="Streamlit Download Manager", 
        layout="wide",
        initial_sidebar_state="expanded",
        page_icon="📥"
    )
    
    # Custom CSS for better UI/UX
    st.markdown("""
    <style>
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        text-align: center;
        color: white;
    }
    .main-header h1 {
        margin: 0;
        font-size: 2.5rem;
        font-weight: bold;
    }
    .main-header p {
        margin: 0.5rem 0 0 0;
        font-size: 1.2rem;
        opacity: 0.9;
    }
    .status-card {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #007bff;
        margin: 1rem 0;
    }
    .progress-container {
        background: #ffffff;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        margin: 1rem 0;
    }
    .file-item {
        background: #f8f9fa;
        padding: 0.8rem;
        margin: 0.5rem 0;
        border-radius: 6px;
        border-left: 3px solid #28a745;
    }
    .terminal-container {
        background: #1e1e1e;
        color: #ffffff;
        padding: 15px;
        border-radius: 8px;
        font-family: 'Courier New', monospace;
        font-size: 14px;
        line-height: 1.4;
        max-height: 400px;
        overflow-y: auto;
        border: 1px solid #333;
    }
    .stButton > button {
        background: linear-gradient(45deg, #667eea, #764ba2);
        color: white;
        border: none;
        border-radius: 6px;
        padding: 0.5rem 1rem;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Main header
    st.markdown("""
    <div class="main-header">
        <h1>📥 Streamlit Download Manager</h1>
        <p>Advanced video downloading with shell integration and real-time progress tracking</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Initialize session state
    if 'file_status' not in st.session_state:
        st.session_state['file_status'] = {}
    if 'video_files' not in st.session_state:
        st.session_state['video_files'] = []
    if 'selected_files' not in st.session_state:
        st.session_state['selected_files'] = []
    if 'is_downloading' not in st.session_state:
        st.session_state['is_downloading'] = False
    if 'base_download_dir' not in st.session_state:
        st.session_state['base_download_dir'] = BASE_DOWNLOAD_DIR
    
    # Header controls
    col_head_left, col_head_right = st.columns([3, 1])
    with col_head_left:
        audio_only = st.checkbox("Audio Only (YouTube: bestaudio, Direct: audio files)", value=False)
    with col_head_right:
        st.session_state['max_concurrency'] = st.number_input(
            "Max parallel downloads", 
            min_value=-1, 
            max_value=50, 
            value=-1,
            help="Set to -1 for unlimited, 0 to disable downloads, or positive number to limit concurrent downloads"
        )
    
    # Playlist limit
    playlist_limit = st.number_input(
        "Playlist Limit (YouTube only, 0 = no limit):", 
        min_value=0, 
        max_value=1000, 
        value=0,
        help="Limit the number of videos fetched from YouTube playlists."
    )
    
    # System info and prerequisites
    with st.expander("System Information & Prerequisites", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Check System"):
                st.write("**System Commands:**")
                commands = ['ffmpeg', 'wget', 'curl', 'yt-dlp']
                for cmd in commands:
                    available = check_command_exists(cmd)
                    st.write(f"- {cmd}: {'✓' if available else '✗'}")
                
                st.write("**Hardware Acceleration:**")
                acceleration = detect_hardware_acceleration()
                st.write(f"- NVIDIA NVENC: {'✓' if acceleration['nvenc'] else '✗'}")
                st.write(f"- Intel QSV: {'✓' if acceleration['qsv'] else '✗'}")
                st.write(f"- VA-API: {'✓' if acceleration['vaapi'] else '✗'}")
                if PLATFORM_CONFIG['is_macos']:
                    st.write(f"- VideoToolbox + Metal (macOS): {'✓' if acceleration['videotoolbox'] else '✗'}")
                st.write(f"- CPU: ✓")
        
        with col2:
            # Check if we need password first
            sudo_check = run_shell_command("sudo -n true", timeout=5)
            needs_password = not sudo_check['success']
            
            if needs_password and 'installation_started' not in st.session_state:
                # Show password input first
                if st.button("Install Prerequisites"):
                    st.session_state['show_password_input'] = True
                    st.rerun()
                
                # Show password input if requested
                if st.session_state.get('show_password_input', False):
                    st.warning("🔐 **Sudo Password Required**")
                    
                    def on_password_change():
                        # Auto-start installation when Enter is pressed
                        if st.session_state.get('sudo_password_input', ''):
                            st.session_state['sudo_password'] = st.session_state['sudo_password_input']
                            st.session_state['installation_started'] = True
                            st.session_state['show_password_input'] = False
                    
                    password = st.text_input(
                        "Enter your sudo password:", 
                        type="password", 
                        help="Press Enter to start installation automatically",
                        key="sudo_password_input",
                        on_change=on_password_change
                    )
                    
                    col_install, col_cancel = st.columns(2)
                    with col_install:
                        if st.button("Start Installation", type="primary"):
                            if password:
                                st.session_state['sudo_password'] = password
                                st.session_state['installation_started'] = True
                                st.session_state['show_password_input'] = False
                                st.rerun()
                            else:
                                st.error("Please enter your password first!")
                    
                    with col_cancel:
                        if st.button("Cancel"):
                            st.session_state['show_password_input'] = False
                            if 'sudo_password_input' in st.session_state:
                                del st.session_state['sudo_password_input']
                            st.rerun()
            else:
                # Either no password needed or password already provided
                if st.button("Install Prerequisites"):
                    st.session_state['installation_started'] = True
                    st.rerun()
            
            # Run installation if started
            if st.session_state.get('installation_started', False):
                with st.spinner("Installing prerequisites..."):
                    success = install_prerequisites()
                    st.session_state['installation_started'] = False
                    if 'sudo_password' in st.session_state:
                        del st.session_state['sudo_password']
                    if success:
                        st.balloons()  # Celebration on success!
        
        # Terminal Output Display
        st.markdown("### 📺 Terminal Output")
        
        # Terminal controls
        col_refresh, col_clear, col_auto = st.columns([1, 1, 2])
        
        with col_refresh:
            if st.button("🔄 Refresh Terminal", help="Refresh terminal output"):
                st.rerun()
        
        with col_clear:
            if st.button("🗑️ Clear Terminal", help="Clear terminal output"):
                st.session_state.terminal_output.clear()
                st.rerun()
        
        with col_auto:
            auto_refresh = st.checkbox("🔄 Auto-refresh (2s)", value=True, help="Automatically refresh terminal every 2 seconds")
        
        # Get terminal output
        terminal_output = st.session_state.terminal_output.get_output()
        
        if terminal_output:
            # Create a styled terminal display
            terminal_html = f"""
            <div style="
                background-color: #1e1e1e;
                color: #ffffff;
                padding: 15px;
                border-radius: 8px;
                font-family: 'Courier New', monospace;
                font-size: 14px;
                line-height: 1.4;
                max-height: 400px;
                overflow-y: auto;
                border: 1px solid #333;
                white-space: pre-wrap;
            ">
            {''.join(terminal_output)}
            </div>
            """
            st.markdown(terminal_html, unsafe_allow_html=True)
        else:
            st.info("No terminal output yet. Run commands to see output here.")
        
        # Auto-refresh if enabled
        if auto_refresh and terminal_output:
            import time
            if 'last_terminal_refresh' not in st.session_state:
                st.session_state['last_terminal_refresh'] = time.time()
            
            current_time = time.time()
            if current_time - st.session_state['last_terminal_refresh'] > 2:
                st.session_state['last_terminal_refresh'] = current_time
                st.rerun()
    
    # Download location
    with st.expander("Download Location", expanded=False):
        cur_base = st.text_input("Base download directory", value=str(st.session_state.get('base_download_dir', get_base_download_dir())))
        col_bd1, col_bd2 = st.columns([1, 1])
        with col_bd1:
            if st.button("Use Default"):
                st.session_state['base_download_dir'] = BASE_DOWNLOAD_DIR
                st.success(f"Set base directory to {BASE_DOWNLOAD_DIR}")
        with col_bd2:
            if st.button("Save Location"):
                st.session_state['base_download_dir'] = os.path.expanduser(cur_base)
                os.makedirs(st.session_state['base_download_dir'], exist_ok=True)
                st.success(f"Base directory set to {st.session_state['base_download_dir']}")
    
    # URL input
    url = st.text_input("Enter video directory URL:", "")
    
    # Fetch video list
    if st.button("Fetch Video List") or 'video_files' not in st.session_state:
        if url:
            with st.spinner("Fetching video list..."):
                files, playlist_title = asyncio.run(fetch_video_links(url, audio_only, playlist_limit if playlist_limit > 0 else None))
                st.session_state['video_files'] = files
                st.session_state['selected_files'] = []
                st.session_state['current_folder'] = get_folder_name_from_url(url, playlist_title)
                st.session_state['file_status'] = {}
                st.session_state['is_downloading'] = False
                st.session_state['playlist_title'] = playlist_title
                st.session_state['current_url'] = url
        else:
            st.warning("Please enter a URL.")
    
    files = st.session_state.get('video_files', [])
    current_folder = st.session_state.get('current_folder', 'downloads')
    playlist_title = st.session_state.get('playlist_title', None)
    
    # Show playlist info
    if playlist_title and 'current_url' in st.session_state and is_youtube_url(st.session_state['current_url']):
        st.success(f"📁 Playlist: {playlist_title}")
        st.info(f"📂 Downloads will go to: {os.path.join(get_base_download_dir(), current_folder)}")
    
    # File selection
    if files:
        st.success(f"Found {len(files)} video files.")
        st.info(f"Downloads will go to: {os.path.join(get_base_download_dir(), current_folder)}")
        
        # Initialize selected files if not exists
        if 'selected_files' not in st.session_state:
            st.session_state['selected_files'] = []
        
        # Select all/none buttons
        col_select, col_deselect = st.columns([1, 1])
        with col_select:
            if st.button("Select All", key="select_all_files"):
                st.session_state['selected_files'] = [f['name'] for f in files]
                st.rerun()
        with col_deselect:
            if st.button("Deselect All", key="deselect_all_files"):
                st.session_state['selected_files'] = []
                st.rerun()
        
        # File multiselect with better state management
        def on_selection_change():
            # This callback ensures the session state is updated immediately
            st.session_state['selected_files'] = st.session_state['file_selector']
        
        selected = st.multiselect(
            "Select files to download or stream:",
            options=[f['name'] for f in files],
            default=st.session_state.get('selected_files', []),
            key='file_selector',
            on_change=on_selection_change
        )
        
        # Ensure session state is always in sync
        if selected != st.session_state.get('selected_files', []):
            st.session_state['selected_files'] = selected
        
        # Show selection status
        if selected:
            st.info(f"📋 Selected {len(selected)} files: {', '.join(selected[:3])}{'...' if len(selected) > 3 else ''}")
        else:
            st.info("📋 No files selected")
        
        # Download button with concurrency info
        max_concurrency = st.session_state.get('max_concurrency', -1)
        
        # Show concurrency info
        if max_concurrency == -1:
            concurrency_info = "🚀 Unlimited parallel downloads"
        elif max_concurrency == 0:
            concurrency_info = "🚫 Downloads disabled"
        else:
            concurrency_info = f"⚡ Max {max_concurrency} parallel downloads"
        
        st.info(concurrency_info)
        
        # Ensure download directory exists
        download_dir = ensure_download_dir(current_folder)
        
        # Download button
        col_download, col_stream = st.columns([1, 1])
        
        with col_download:
            if st.button("📥 Download Selected", type="primary"):
                if not selected:
                    st.warning("No files selected for download!")
                elif max_concurrency == 0:
                    st.error("Downloads are disabled! Set max parallel downloads to a positive number or -1 for unlimited.")
                else:
                    st.session_state['is_downloading'] = True
                    files_to_download = [f for f in files if f['name'] in selected]
                    
                    # Show actual concurrency being used
                    if max_concurrency == -1:
                        actual_workers = min(len(selected), 20)
                        st.info(f"📊 Using {actual_workers} parallel downloads (capped at 20 for stability)")
                    else:
                        st.info(f"📊 Using {max_concurrency} parallel downloads")
                    
                    # Start download thread
                    download_thread = download_all_files(files_to_download, [f['name'] for f in files_to_download], download_dir, st.session_state['file_status'])
        
        # Show download progress if downloading
        if st.session_state.get('is_downloading', False):
            st.markdown("""
            <div class="progress-container">
                <h3 style="margin-top: 0; color: #333;">📊 Download Progress</h3>
            """, unsafe_allow_html=True)
            
            # Create placeholders for real-time updates
            progress_placeholder = st.empty()
            status_placeholder = st.empty()
            
            # Control buttons
            col_refresh, col_stop, col_pause = st.columns([1, 1, 1])
            
            with col_refresh:
                if st.button("🔄 Refresh Progress", help="Refresh the progress display"):
                    st.rerun()
            
            with col_stop:
                if st.button("⏹️ Stop Downloads", help="Stop all downloads"):
                    st.session_state['is_downloading'] = False
                    st.warning("Downloads stopped by user")
                    st.rerun()
            
            with col_pause:
                if st.button("⏸️ Pause/Resume", help="Pause or resume downloads"):
                    st.session_state['download_paused'] = not st.session_state.get('download_paused', False)
                    status = "paused" if st.session_state['download_paused'] else "resumed"
                    st.info(f"Downloads {status}")
                    st.rerun()
            
            # Real-time progress update loop (like original script)
            import time
            max_wait = 600  # 10 minutes max for polling
            poll_interval = 0.5  # seconds
            start_time = time.time()
            
            while st.session_state.get('is_downloading', False) and (time.time() - start_time < max_wait):
                file_status = st.session_state.get('file_status', {})
                completed_files = sum(1 for name in selected if file_status.get(name, {}).get('status') in ['completed', 'already downloaded'])
                failed_files = sum(1 for name in selected if str(file_status.get(name, {}).get('status', '')).startswith('error'))
                total_selected = len(selected)
                processed_files = completed_files + failed_files
                progress = processed_files / total_selected if total_selected > 0 else 0
                
                # Update progress bar
                progress_text = f"Progress: {processed_files}/{total_selected} processed ({completed_files} successful, {failed_files} failed)"
                progress_placeholder.progress(progress, text=progress_text)
                
                # Update status lines
                status_lines = []
                for name in selected:
                    status_info = file_status.get(name, {})
                    status = status_info.get('status', '-')
                    progress_val = status_info.get('progress', 0)
                    speed = status_info.get('speed', 0)
                    eta = status_info.get('eta', 0)
                    downloaded = status_info.get('downloaded', 0)
                    
                    if status == 'completed':
                        status_lines.append(f"✅ `{name}`: Completed")
                    elif status == 'downloading':
                        # Format speed and ETA
                        speed_str = f"{speed/1024/1024:.1f} MB/s" if speed > 1024*1024 else f"{speed/1024:.1f} KB/s" if speed > 1024 else f"{speed:.1f} B/s"
                        eta_str = f"{int(eta)}s" if eta < 60 else f"{int(eta/60)}m {int(eta%60)}s" if eta < 3600 else f"{int(eta/3600)}h {int((eta%3600)/60)}m"
                        size_str = f"{downloaded/1024/1024:.1f} MB" if downloaded > 1024*1024 else f"{downloaded/1024:.1f} KB" if downloaded > 1024 else f"{downloaded} B"
                        status_lines.append(f"⏳ `{name}`: Downloading ({progress_val:.1f}%) - {speed_str} - ETA: {eta_str} - {size_str}")
                    elif status == 'paused':
                        status_lines.append(f"⏸️ `{name}`: Paused")
                    elif status == 'stopped':
                        status_lines.append(f"⏹️ `{name}`: Stopped")
                    elif str(status).startswith('error'):
                        status_lines.append(f"❌ `{name}`: {status}")
                    elif status == 'already downloaded':
                        status_lines.append(f"✅ `{name}`: Already Downloaded")
                    else:
                        status_lines.append(f"📄 `{name}`: {status}")
                
                # Update status display
                status_placeholder.markdown("\n".join(status_lines))
                
                # Check if all downloads are complete
                if completed_files == total_selected and total_selected > 0:
                    st.session_state['is_downloading'] = False
                    st.success("🎉 All downloads completed!")
                    st.balloons()
                    break
                
                time.sleep(poll_interval)
            
            # Final update after downloads
            file_status = st.session_state.get('file_status', {})
            completed_files = sum(1 for name in selected if file_status.get(name, {}).get('status') in ['completed', 'already downloaded'])
            failed_files = sum(1 for name in selected if str(file_status.get(name, {}).get('status', '')).startswith('error'))
            total_selected = len(selected)
            processed_files = completed_files + failed_files
            progress = processed_files / total_selected if total_selected > 0 else 0
            
            # Final progress update
            progress_text = f"Progress: {processed_files}/{total_selected} processed ({completed_files} successful, {failed_files} failed)"
            progress_placeholder.progress(progress, text=progress_text)
            
            # Final status update
            status_lines = []
            for name in selected:
                status_info = file_status.get(name, {})
                status = status_info.get('status', '-')
                if status == 'completed':
                    status_lines.append(f"✅ `{name}`: Completed")
                elif status == 'downloading':
                    prog = status_info.get('progress', 0)
                    status_lines.append(f"⏳ `{name}`: Downloading ({prog:.1f}%)")
                elif status == 'paused':
                    status_lines.append(f"⏸️ `{name}`: Paused")
                elif status == 'stopped':
                    status_lines.append(f"⏹️ `{name}`: Stopped")
                elif str(status).startswith('error'):
                    status_lines.append(f"❌ `{name}`: {status}")
                elif status == 'already downloaded':
                    status_lines.append(f"✅ `{name}`: Already Downloaded")
                else:
                    status_lines.append(f"📄 `{name}`: {status}")
            
            status_placeholder.markdown("\n".join(status_lines))
            
            # Close progress container
            st.markdown("</div>", unsafe_allow_html=True)
        
        # Stream button
        with col_stream:
            if st.button("🎬 Stream in VLC"):
                if not selected:
                    st.warning("No files selected for streaming!")
                else:
                    with st.spinner("Preparing streaming URLs..."):
                        try:
                            urls, names = asyncio.run(prepare_streaming_urls(files, selected, download_dir))
                            if urls:
                                stream_all_in_vlc(urls, names)
                                
                                # Count local vs network streams
                                local_count = sum(1 for url in urls if url.startswith('file://'))
                                network_count = len(urls) - local_count
                                
                                st.success(f"✅ Launched VLC with {len(urls)} files!")
                                if local_count > 0 and network_count > 0:
                                    st.info(f"📁 {local_count} local files, 🌐 {network_count} network streams")
                                elif local_count > 0:
                                    st.info(f"📁 Streaming {local_count} local files")
                                else:
                                    st.info(f"🌐 Streaming {network_count} files from network")
                                st.info("Check your system for the VLC media player window.")
                            else:
                                st.error("No valid URLs found for streaming!")
                        except Exception as e:
                            st.error(f"Failed to prepare streaming: {e}")
                
        
        # Video encoding section
        st.markdown("---")
        st.markdown("### 🎬 Video Encoding & Merging")
        video_files = list_video_files(download_dir)
        
        if video_files:
            st.info(f"Found {len(video_files)} video files ready for encoding/merging:")
            
            # Show video files
            for i, file_path in enumerate(video_files[:5]):
                file_name = os.path.basename(file_path)
                info = get_video_info(file_path)
                st.write(f"{i+1}. {file_name} - {info}")
            
            if len(video_files) > 5:
                st.write(f"... and {len(video_files) - 5} more")
            
            # Show available hardware acceleration
            acceleration = detect_hardware_acceleration()
            hw_info = []
            if acceleration['nvenc']:
                hw_info.append("🚀 NVIDIA NVENC")
            if acceleration['qsv']:
                hw_info.append("⚡ Intel QSV")
            if acceleration['vaapi']:
                hw_info.append("🔧 VA-API")
            if acceleration['videotoolbox'] and PLATFORM_CONFIG['is_macos']:
                hw_info.append("🍎 VideoToolbox + Metal GPU (macOS)")
            hw_info.append("🖥️ CPU")
            
            st.info(f"Available encoders: {', '.join(hw_info)}")
            
            # Encoding options
            col1, col2, col3 = st.columns(3)
            
            with col1:
                preset_options = ["auto", "copy"]
                if acceleration['nvenc']:
                    preset_options.extend(["h264_nvenc", "h265_nvenc"])
                if acceleration['qsv']:
                    preset_options.extend(["h264_qsv", "h265_qsv"])
                if acceleration['vaapi']:
                    preset_options.extend(["h264_vaapi", "h265_vaapi"])
                if acceleration['videotoolbox'] and PLATFORM_CONFIG['is_macos']:
                    preset_options.extend(["h264_videotoolbox", "h265_videotoolbox"])
                preset_options.extend(["h264_cpu", "h265_cpu"])
                
                preset = st.selectbox(
                    "Encoding Preset",
                    preset_options,
                    help="Choose encoding method. 'auto' selects best available hardware acceleration."
                )
            
            with col2:
                quality = st.slider("Quality", 18, 32, 25, help="Lower = higher quality, larger file")
            
            with col3:
                output_name = st.text_input("Output filename", f"{current_folder}_merged.mp4")
            
            # OP/ED trimming controls
            with st.expander("Anime OP/ED Trimming (optional)", expanded=False):
                st.write("Choose how to detect intro/outro segments to remove from each episode before merging.")
                
                # Detection method
                detection_method = st.radio(
                    "Detection Method:",
                    ["Manual Input", "Auto-Detect (AI Analysis)", "Both (Auto + Manual Override)"],
                    help="Auto-detect analyzes audio patterns across episodes to find repeated intro/outro segments"
                )
                
                # Auto-detection section
                if detection_method in ["Auto-Detect (AI Analysis)", "Both (Auto + Manual Override)"]:
                    st.markdown("### 🤖 Automatic Detection")
                    col_auto1, col_auto2 = st.columns(2)
                    
                    with col_auto1:
                        if st.button("🔍 Auto-Detect OP/ED", help="Analyze video files to automatically find intro/outro patterns"):
                            with st.spinner("Analyzing audio patterns across episodes..."):
                                intro_range, outro_range, confidence = auto_detect_intro_outro(video_files, download_dir)
                                
                                if intro_range or outro_range:
                                    st.success("🎯 Detection completed!")
                                    if intro_range:
                                        st.info(f"**Detected Intro:** {intro_range[0]:.1f}s - {intro_range[1]:.1f}s (confidence: {confidence[0]:.2f})")
                                    if outro_range:
                                        st.info(f"**Detected Outro:** {outro_range[0]:.1f}s - {outro_range[1]:.1f}s (confidence: {confidence[1]:.2f})")
                                    
                                    # Store detected values for use
                                    st.session_state['detected_intro'] = intro_range
                                    st.session_state['detected_outro'] = outro_range
                                    st.session_state['detection_confidence'] = confidence

                                    # Preview per-episode alignment results
                                    try:
                                        align_preview = detect_alignment_for_files(video_files, download_dir, intro_range, outro_range)
                                        st.markdown("#### Preview per-episode OP/ED matches")
                                        for r in align_preview:
                                            intro_txt = f"{r['intro'][0]:.1f}-{r['intro'][1]:.1f}s (conf {r['intro_conf']:.2f})" if r['intro'] else "-"
                                            outro_txt = f"{r['outro'][0]:.1f}-{r['outro'][1]:.1f}s (conf {r['outro_conf']:.2f})" if r['outro'] else "-"
                                            st.write(f"• `{r['file']}` → OP: {intro_txt} | ED: {outro_txt}")
                                        st.caption("These are the ranges that will be applied if per-episode alignment is enabled.")
                                        st.session_state['align_preview'] = align_preview
                                    except Exception as e:
                                        st.warning(f"Preview unavailable: {e}")
                                else:
                                    st.warning("⚠️ No clear patterns detected. Try manual input or check if videos have consistent intro/outro.")
                    
                    with col_auto2:
                        if 'detected_intro' in st.session_state and st.session_state['detected_intro']:
                            st.success("✅ Intro detected")
                            st.caption(f"Range: {st.session_state['detected_intro'][0]:.1f}s - {st.session_state['detected_intro'][1]:.1f}s")
                        if 'detected_outro' in st.session_state and st.session_state['detected_outro']:
                            st.success("✅ Outro detected")
                            st.caption(f"Range: {st.session_state['detected_outro'][0]:.1f}s - {st.session_state['detected_outro'][1]:.1f}s")
                
                # Manual input section
                if detection_method in ["Manual Input", "Both (Auto + Manual Override)"]:
                    st.markdown("### ✏️ Manual Input")
                    st.caption("Tip: Use seconds. Example OP 0-90, ED last 90 seconds (e.g., start = duration-90).")
                    col_to, col_te = st.columns(2)
                    
                    with col_to:
                        remove_intro = st.checkbox("Remove Intro (OP)", value=False)
                        # Use detected values as defaults if available
                        default_intro_start = st.session_state.get('detected_intro', (0.0, 90.0))[0] if 'detected_intro' in st.session_state else 0.0
                        default_intro_end = st.session_state.get('detected_intro', (0.0, 90.0))[1] if 'detected_intro' in st.session_state else 90.0
                        intro_start = st.number_input("Intro start (s)", min_value=0.0, value=default_intro_start, step=0.5, disabled=not remove_intro)
                        intro_end = st.number_input("Intro end (s)", min_value=0.0, value=default_intro_end, step=0.5, disabled=not remove_intro)
                    
                    with col_te:
                        remove_outro = st.checkbox("Remove Outro (ED)", value=False)
                        # Use detected values as defaults if available
                        default_outro_start = st.session_state.get('detected_outro', (0.0, 0.0))[0] if 'detected_outro' in st.session_state else 0.0
                        default_outro_end = st.session_state.get('detected_outro', (0.0, 0.0))[1] if 'detected_outro' in st.session_state else 0.0
                        outro_start = st.number_input("Outro start (s)", min_value=0.0, value=default_outro_start, step=0.5, disabled=not remove_outro)
                        outro_end = st.number_input("Outro end (s)", min_value=0.0, value=default_outro_end, step=0.5, disabled=not remove_outro)
            
            align_per_file = False
            if 'detection_method' in locals() and detection_method in ["Auto-Detect (AI Analysis)", "Both (Auto + Manual Override)"]:
                align_per_file = st.checkbox("Per-episode auto alignment (intro/outro may shift per file)", value=True)

            # Cleanup option
            cleanup_residuals = st.checkbox("Keep only final trimmed output (delete residuals)", value=True, help="Deletes temporary folders and removed parts")

            if st.button("Start Encoding"):
                output_path = os.path.join(download_dir, output_name)
                terminal = st.session_state.terminal_output
                terminal.add_line(f"Starting video encoding: {preset} quality={quality}", "info")
                
                with st.spinner("Encoding videos..."):
                    # If using auto detection but no ranges are available, run detection now
                    if detection_method in ["Auto-Detect (AI Analysis)", "Both (Auto + Manual Override)"]:
                        no_manual = not (('remove_intro' in locals() and remove_intro) or ('remove_outro' in locals() and remove_outro))
                        no_detected = (not st.session_state.get('detected_intro')) and (not st.session_state.get('detected_outro'))
                        if no_manual and no_detected:
                            try:
                                auto_i, auto_o, conf = auto_detect_intro_outro(video_files, download_dir)
                                if auto_i or auto_o:
                                    st.session_state['detected_intro'] = auto_i
                                    st.session_state['detected_outro'] = auto_o
                                    st.session_state['detection_confidence'] = conf
                            except Exception as e:
                                pass
                    # Determine intro/outro ranges based on detection method
                    intro_rng = None
                    outro_rng = None
                    
                    if detection_method == "Auto-Detect (AI Analysis)":
                        # Use only auto-detected values
                        if 'detected_intro' in st.session_state and st.session_state['detected_intro']:
                            intro_rng = st.session_state['detected_intro']
                        if 'detected_outro' in st.session_state and st.session_state['detected_outro']:
                            outro_rng = st.session_state['detected_outro']
                    elif detection_method == "Manual Input":
                        # Use only manual input values
                        if 'remove_intro' in locals() and remove_intro:
                            intro_rng = (intro_start, intro_end)
                        if 'remove_outro' in locals() and remove_outro:
                            outro_rng = (outro_start, outro_end)
                    else:  # Both (Auto + Manual Override)
                        # Use manual values if provided, otherwise fall back to detected
                        if 'remove_intro' in locals() and remove_intro:
                            intro_rng = (intro_start, intro_end)
                        elif 'detected_intro' in st.session_state and st.session_state['detected_intro']:
                            intro_rng = st.session_state['detected_intro']
                            
                        if 'remove_outro' in locals() and remove_outro:
                            outro_rng = (outro_start, outro_end)
                        elif 'detected_outro' in st.session_state and st.session_state['detected_outro']:
                            outro_rng = st.session_state['detected_outro']
                    
                    # Log what will be trimmed
                    if intro_rng:
                        terminal.add_line(f"Trimming intro: {intro_rng[0]:.1f}s - {intro_rng[1]:.1f}s", "info")
                    if outro_rng:
                        terminal.add_line(f"Trimming outro: {outro_rng[0]:.1f}s - {outro_rng[1]:.1f}s", "info")
                    
                    success, error = encode_videos_direct(
                        download_dir,
                        output_name,
                        preset,
                        str(quality),
                        intro_rng,
                        outro_rng,
                        per_file_align=align_per_file,
                        cleanup_residuals=cleanup_residuals,
                        keep_deleted_compilation=False,
                        only_keep_outputs=cleanup_residuals
                    )
                
                if success:
                    st.success(f"✅ Successfully created: {output_path}")
                    if os.path.exists(output_path):
                        file_size = os.path.getsize(output_path) / (1024*1024)  # MB
                        st.info(f"File size: {file_size:.1f} MB")
                        terminal.add_line(f"Encoding completed successfully: {file_size:.1f} MB", "info")
                    else:
                        st.warning("Output file created but not found at expected location")
                else:
                    st.error(f"❌ Encoding failed: {error}")
                    terminal.add_line(f"Encoding failed: {error}", "error")
        
        else:
            st.info("No video files found for encoding. Download some videos first!")
            st.info("💡 Try downloading some videos from YouTube or other sources first.")

if __name__ == "__main__":
    main()
