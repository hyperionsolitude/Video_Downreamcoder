#!/usr/bin/env python3
"""
Streamlit Download Manager with Shell Command Integration
Combines download management with video encoding using shell commands
"""

import streamlit as st
import subprocess
import os
import sys
import time
import re
import shutil
import tempfile
import json
import threading
import urllib.parse
from pathlib import Path
import asyncio
import aiohttp
from bs4 import BeautifulSoup, Tag
import yt_dlp
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
from mutagen.id3._frames import APIC, TIT2, TPE1, TALB
from PIL import Image
import io
import queue
from datetime import datetime

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
    """Install required packages using shell commands"""
    # Ensure terminal_output exists in session state
    if 'terminal_output' not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()
    
    terminal = st.session_state.terminal_output
    terminal.add_line("Starting prerequisites installation...", "info")
    
    st.info("Installing prerequisites...")
    
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
    
    # Update package list
    st.info("📦 Updating package list...")
    if needs_password:
        result = run_sudo_command_with_password("apt update", password, timeout=60)
    else:
        result = run_shell_command_with_output("sudo apt update", timeout=60)
    
    if not result['success']:
        st.error(f"❌ Failed to update package list.")
        terminal.add_line("Failed to update package list", "error")
        return False
    
    st.success("✅ Package list updated!")
    
    # Install system packages
    packages = [
        "ffmpeg",
        "wget", 
        "curl",
        "python3-pip"
    ]
    
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
    
    # Install yt-dlp via pipx (doesn't need sudo)
    st.info("🎥 Installing yt-dlp...")
    result = run_shell_command_with_output("pipx install yt-dlp", timeout=120)
    if not result['success']:
        st.warning(f"Failed to install yt-dlp via pipx, trying pip3...")
        terminal.add_line("Trying pip3 for yt-dlp installation...", "info")
        # Try with pip3 as fallback
        result = run_shell_command_with_output("pip3 install --user yt-dlp", timeout=120)
        if not result['success']:
            st.warning(f"Failed to install yt-dlp via pip3")
            terminal.add_line("Failed to install yt-dlp", "error")
        else:
            st.success("✅ yt-dlp installed via pip3!")
    else:
        st.success("✅ yt-dlp installed via pipx!")
    
    terminal.add_line("Prerequisites installation completed!", "info")
    st.success("🎉 Prerequisites installation completed!")
    st.info("🔄 **Tip**: Click 'Check System' to verify what was installed successfully.")
    
    return True

def detect_hardware_acceleration():
    """Detect available hardware acceleration using shell commands"""
    acceleration = {
        'nvenc': False,
        'qsv': False,
        'vaapi': False,
        'cpu': True
    }
    
    # Check FFmpeg encoders
    result = run_shell_command("ffmpeg -hide_banner -encoders 2>/dev/null")
    if result['success']:
        encoders = result['stdout']
        acceleration['nvenc'] = 'h264_nvenc' in encoders or 'hevc_nvenc' in encoders
        acceleration['qsv'] = 'h264_qsv' in encoders or 'hevc_qsv' in encoders
        acceleration['vaapi'] = 'h264_vaapi' in encoders or 'hevc_vaapi' in encoders
    
    # Test NVIDIA GPU availability (not just nvidia-smi)
    if acceleration['nvenc']:
        # Test if NVENC actually works
        test_result = run_shell_command("ffmpeg -f lavfi -i testsrc=duration=1:size=320x240:rate=1 -c:v h264_nvenc -f null - 2>&1")
        if not test_result['success'] or 'No capable devices found' in test_result['stderr']:
            acceleration['nvenc'] = False
    
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

def encode_videos_direct(download_dir, output_file, preset="auto", quality="25"):
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
    
    # Create file list for FFmpeg concat
    list_file = os.path.join(download_dir, "filelist.txt")
    try:
        with open(list_file, 'w') as f:
            for video_file in video_files:
                # Escape single quotes for FFmpeg
                escaped_file = video_file.replace("'", "'\"'\"'")
                f.write(f"file '{escaped_file}'\n")
    except Exception as e:
        return False, f"Failed to create file list: {e}"
    
    # Determine encoder based on preset and hardware
    acceleration = detect_hardware_acceleration()
    
    if preset == "auto":
        if acceleration['nvenc']:
            encoder = "hevc_nvenc"
            encoder_opts = f"-c:v {encoder} -preset fast -cq {quality}"
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
        encoder_opts = "-c copy"
    elif "nvenc" in preset:
        encoder_opts = f"-c:v {preset.replace('h264_', 'h264_').replace('h265_', 'hevc_')} -preset fast -cq {quality}"
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
    cmd = f"ffmpeg -y -f concat -safe 0 -i '{list_file}' {encoder_opts} -c:a copy '{output_path}'"
    
    terminal.add_line(f"Using encoder: {encoder_opts}", "info")
    terminal.add_line(f"Output file: {output_path}", "info")
    
    # Run FFmpeg
    result = run_shell_command_with_output(cmd, cwd=download_dir, timeout=3600)
    
    # If hardware acceleration failed, try CPU fallback
    if not result['success'] and ('No capable devices found' in result['stderr'] or 'OpenEncodeSessionEx failed' in result['stderr']):
        terminal.add_line("Hardware acceleration failed, trying CPU fallback...", "warning")
        
        # Fallback to CPU encoding
        if preset == "auto" or "nvenc" in preset or "qsv" in preset or "vaapi" in preset:
            if "h264" in preset or preset == "auto":
                fallback_cmd = f"ffmpeg -y -f concat -safe 0 -i '{list_file}' -c:v libx264 -preset fast -crf {quality} -c:a copy '{output_path}'"
            else:
                fallback_cmd = f"ffmpeg -y -f concat -safe 0 -i '{list_file}' -c:v libx265 -preset fast -crf {quality} -c:a copy '{output_path}'"
            
            terminal.add_line(f"Fallback command: {fallback_cmd}", "info")
            result = run_shell_command_with_output(fallback_cmd, cwd=download_dir, timeout=3600)
    
    # Clean up
    try:
        os.remove(list_file)
    except:
        pass
    
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
            
            if st.button("Start Encoding"):
                output_path = os.path.join(download_dir, output_name)
                terminal = st.session_state.terminal_output
                terminal.add_line(f"Starting video encoding: {preset} quality={quality}", "info")
                
                with st.spinner("Encoding videos..."):
                    success, error = encode_videos_direct(download_dir, output_name, preset, str(quality))
                
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
