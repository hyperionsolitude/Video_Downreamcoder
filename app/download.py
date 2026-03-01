"""Fetch, download, and stream video/audio files."""

import asyncio
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import aiohttp
import streamlit as st
import yt_dlp
from bs4 import BeautifulSoup, Tag

from .config import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS
from .path_utils import is_youtube_url, normalize_filename
from .shell_utils import (
    TerminalOutput,
    check_command_exists,
    run_shell_command,
    run_shell_command_with_output,
)
from .torrent import is_torrent_link


async def fetch_youtube_video_links(url, audio_only=False, playlist_limit=None):
    """Fetch YouTube video links using yt-dlp."""
    cache_key = f"{url}_{audio_only}_{playlist_limit}"
    if hasattr(st.session_state, "youtube_cache") and cache_key in st.session_state.youtube_cache:
        return st.session_state.youtube_cache[cache_key]

    cmd_parts = ["yt-dlp", "--flat-playlist", "--dump-json"]
    if audio_only:
        cmd_parts.extend(["--extract-audio", "--audio-format", "mp3"])
    if playlist_limit:
        cmd_parts.extend(["--playlist-end", str(playlist_limit)])
    cmd_parts.append(url)
    result = run_shell_command(" ".join(cmd_parts), timeout=60)

    if not result["success"]:
        st.error(f"Failed to fetch YouTube links: {result['stderr']}")
        return [], None

    try:
        lines = result["stdout"].strip().split("\n")
        files = []
        playlist_title = "YouTube_Playlist"
        for line in lines:
            if line.strip():
                try:
                    data = json.loads(line)
                    title = data.get("title", "Unknown")
                    webpage_url = data.get("webpage_url", data.get("url", ""))
                    artist = data.get("uploader", "")
                    base_name = f"{artist} - {title}" if artist else title
                    safe_name = normalize_filename(base_name)
                    files.append({
                        "name": safe_name + (".mp3" if audio_only else ".mp4"),
                        "url": webpage_url,
                        "yt_webpage_url": webpage_url,
                        "is_youtube": True,
                        "is_audio": audio_only,
                        "needs_url_extraction": True,
                        "thumbnail_url": data.get("thumbnail"),
                        "video_id": data.get("id"),
                        "artist": artist,
                        "title": title,
                    })
                    if not playlist_title or playlist_title == "YouTube_Playlist":
                        playlist_title = data.get("playlist_title", data.get("title", "YouTube_Playlist"))
                except json.JSONDecodeError:
                    continue
        if not hasattr(st.session_state, "youtube_cache"):
            st.session_state.youtube_cache = {}
        st.session_state.youtube_cache[cache_key] = (files, playlist_title)
        return files, playlist_title
    except Exception as e:
        st.error(f"Error parsing YouTube data: {e}")
        return [], None


async def fetch_video_links(url, audio_only=False, playlist_limit=None):
    """Fetch video links from URL."""
    if is_youtube_url(url):
        return await fetch_youtube_video_links(url, audio_only, playlist_limit)
    if url.lower().endswith(VIDEO_EXTENSIONS + AUDIO_EXTENSIONS):
        filename = os.path.basename(url)
        return [{
            "name": filename,
            "url": url,
            "is_audio": audio_only and url.lower().endswith(AUDIO_EXTENSIONS),
        }], None
    timeout = aiohttp.ClientTimeout(total=30)
    if not url.endswith("/"):
        url = url + "/"
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")
            links = soup.find_all("a")
            files = []
            for link in links:
                if isinstance(link, Tag):
                    href = link.get("href")
                    if href and isinstance(href, str):
                        if audio_only:
                            if href.lower().endswith(AUDIO_EXTENSIONS):
                                name = os.path.basename(href)
                                files.append({"name": name, "url": urllib.parse.urljoin(url, href), "is_audio": True})
                        else:
                            if href.lower().endswith(VIDEO_EXTENSIONS):
                                name = os.path.basename(href)
                                files.append({"name": name, "url": urllib.parse.urljoin(url, href), "is_audio": False})
            return files, None


def download_file_with_shell(file_url, file_path, file_info=None, progress_callback=None):
    """Download file using shell commands (wget, curl, or yt-dlp) with progress tracking."""
    file_dir = os.path.dirname(file_path)
    os.makedirs(file_dir, exist_ok=True)
    if file_info and file_info.get("is_youtube"):
        if file_info.get("is_audio"):
            cmd = f"yt-dlp --progress -x --audio-format mp3 -o '{file_path}' '{file_info['yt_webpage_url']}'"
        else:
            cmd = f"yt-dlp --progress -f 'best[ext=mp4]/best' -o '{file_path}' '{file_info['yt_webpage_url']}'"
    else:
        if check_command_exists("wget"):
            cmd = f"wget --progress=bar:force -O '{file_path}' '{file_url}'"
        elif check_command_exists("curl"):
            cmd = f"curl -L --progress-bar -o '{file_path}' '{file_url}'"
        else:
            return False, "Neither wget nor curl available"
    result = run_shell_command_with_output(cmd, timeout=600, show_in_terminal=True)
    return result["success"], result["stderr"]


def start_torrent_download_with_aria2(torrent_url: str, download_dir: str) -> bool:
    """Start a torrent download using aria2c in a background thread."""
    os.makedirs(download_dir, exist_ok=True)
    if "terminal_output" not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()
    terminal = st.session_state.terminal_output
    if not check_command_exists("aria2c"):
        terminal.add_line("aria2c is not installed; cannot start torrent download.", "error")
        return False
    url = torrent_url.strip()
    if not is_torrent_link(url):
        terminal.add_line("The provided link does not look like a torrent or magnet link.", "error")
        return False
    parent_pid = os.getpid()
    cmd = f"aria2c --seed-time=0 --stop-with-process={parent_pid} --dir='{download_dir}' '{url}'"

    def _run():
        terminal.add_line(f"Starting aria2c torrent download into {download_dir}", "info")
        result = run_shell_command_with_output(cmd, timeout=86400, show_in_terminal=True)
        if result["success"]:
            terminal.add_line("✅ Torrent download completed.", "success")
        else:
            terminal.add_line(f"❌ Torrent download exited with code {result['returncode']}", "error")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return True


def stream_torrent_via_webtorrent(torrent_ref: str) -> bool:
    """Stream a torrent directly to VLC using webtorrent-cli."""
    if "terminal_output" not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()
    terminal = st.session_state.terminal_output
    if not check_command_exists("webtorrent"):
        terminal.add_line("webtorrent-cli is not installed; cannot stream torrent directly.", "error")
        st.error("The `webtorrent` CLI is required to stream torrents without downloading.")
        if st.button("Install torrent options (Node.js + webtorrent-cli)", key="install_webtorrent_btn"):
            st.session_state["install_torrent_options_started"] = True
            st.rerun()
        return False
    ref = torrent_ref.strip()
    if not ref:
        terminal.add_line("No torrent reference provided for streaming.", "error")
        return False
    cmd = f'webtorrent "{ref}" --vlc'

    def _run():
        terminal.add_line("Starting webtorrent streaming to VLC...", "info")
        result = run_shell_command_with_output(cmd, timeout=86400, show_in_terminal=True)
        if result.get("returncode") not in (0, None):
            terminal.add_line(f"webtorrent exited with code {result.get('returncode')}", "warning")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return True


def _get_remote_file_size(url):
    """Try HEAD first; if missing, try Range GET to read Content-Range total."""
    try:
        class HeadRequest(urllib.request.Request):
            def get_method(self):
                return "HEAD"
        req = HeadRequest(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                length = resp.headers.get("Content-Length") or resp.headers.get("content-length")
                if length and str(length).isdigit():
                    return int(length)
        except Exception:
            pass
        get_req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-0"},
        )
        with urllib.request.urlopen(get_req, timeout=15) as resp2:
            cr = resp2.headers.get("Content-Range") or resp2.headers.get("content-range")
            if cr:
                m = re.search(r"/\s*(\d+)\s*$", cr)
                if m:
                    return int(m.group(1))
        return 0
    except Exception:
        return 0


def download_all_files(files, selected, download_dir, status_dict):
    """Download all selected files using shell commands with concurrency control."""
    max_concurrency = st.session_state.get("max_concurrency", -1)
    if max_concurrency == 0:
        for file in files:
            if file["name"] in selected:
                status_dict[file["name"]] = {"status": "downloads disabled", "progress": 0}
        return None
    elif max_concurrency == -1:
        max_workers = min(len(selected), 20)
    else:
        max_workers = max(1, max_concurrency)

    def download_single_file(file):
        if file["name"] not in selected:
            return
        safe_name = normalize_filename(file["name"])
        file_path = os.path.join(download_dir, safe_name)
        file_key = file["name"]
        if os.path.exists(file_path) and os.path.getsize(file_path) > 1024:
            status_dict[file_key] = {"status": "already downloaded", "progress": 100}
            return
        status_dict[file_key] = {"status": "downloading", "progress": 0}
        if "terminal_output" not in st.session_state:
            st.session_state.terminal_output = TerminalOutput()
        expected_total_size = 0
        try:
            expected_total_size = _get_remote_file_size(file["url"])
        except Exception:
            pass

        def update_progress():
            start_time = time.time()
            last_progress = 0
            last_size = 0
            last_update_time = start_time
            last_ui_update = start_time
            avg_speed = 0.0
            while status_dict[file_key]["status"] == "downloading" and not st.session_state.get("stop_downloads"):
                if os.path.exists(file_path):
                    current_size = os.path.getsize(file_path)
                    current_time = time.time()
                    elapsed = current_time - start_time
                    if current_time - last_update_time > 0.5:
                        size_diff = current_size - last_size
                        time_diff = current_time - last_update_time
                        instant_speed = size_diff / time_diff if time_diff > 0 else 0
                        avg_speed = instant_speed if avg_speed == 0 else 0.8 * avg_speed + 0.2 * instant_speed
                        if expected_total_size and expected_total_size > 0:
                            progress = int((current_size / expected_total_size) * 100)
                            progress = max(0, min(progress, 99))
                            remaining_bytes = max(0, expected_total_size - current_size)
                            eta = (remaining_bytes / avg_speed) if avg_speed > 0 else 0
                        else:
                            progress = last_progress
                            eta = 0
                        if (progress - last_progress >= 1) or progress in (0, 99) or (current_time - last_ui_update >= 1.0):
                            status_dict[file_key].update({
                                "progress": progress,
                                "downloaded": current_size,
                                "speed": avg_speed,
                                "eta": eta,
                                "elapsed": elapsed,
                            })
                            last_progress = progress
                            last_ui_update = current_time
                        last_size = current_size
                        last_update_time = current_time
                time.sleep(0.5)

        progress_thread = threading.Thread(target=update_progress, daemon=True)
        progress_thread.start()
        success, error = download_file_with_shell(file["url"], file_path, file, progress_callback=None)
        if success:
            status_dict[file_key] = {"status": "completed", "progress": 100}
        else:
            status_dict[file_key] = {"status": f"error: {error}", "progress": 0}

    def download_worker():
        files_to_download = [f for f in files if f["name"] in selected]
        if not files_to_download:
            return
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {executor.submit(download_single_file, file): file for file in files_to_download}
            for future in concurrent.futures.as_completed(future_to_file):
                file = future_to_file[future]
                try:
                    future.result()
                except Exception as e:
                    status_dict[file["name"]] = {"status": f"error: {str(e)}", "progress": 0}

    thread = threading.Thread(target=download_worker, daemon=True)
    thread.start()
    return thread


async def prepare_streaming_urls(files, selected, download_dir):
    """Prepare URLs for streaming, prioritizing local files over network streams."""
    urls = []
    names = []
    if "terminal_output" not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()
    terminal = st.session_state.terminal_output
    for file in files:
        if file["name"] in selected:
            names.append(file["name"])
            local_file_path = os.path.join(download_dir, normalize_filename(file["name"]))
            alt_local_file_path = os.path.join(download_dir, file["name"])
            candidate_path = None
            if os.path.exists(local_file_path) and os.path.getsize(local_file_path) > 1024:
                candidate_path = local_file_path
            elif os.path.exists(alt_local_file_path) and os.path.getsize(alt_local_file_path) > 1024:
                candidate_path = alt_local_file_path
            if candidate_path is not None:
                abs_path = os.path.abspath(candidate_path)
                file_uri = Path(abs_path).as_uri()
                urls.append(file_uri)
                terminal.add_line(f"Using local file: {file['name']}", "info")
            else:
                terminal.add_line(f"Streaming from network: {file['name']}", "info")
                if file.get("needs_url_extraction") and file.get("is_youtube"):
                    # Always request video for VLC streaming so both video and audio play
                    direct_url = await get_youtube_direct_url(file["yt_webpage_url"], audio_only=False)
                    urls.append(direct_url)
                else:
                    urls.append(file["url"])
    return urls, names


async def get_youtube_direct_url(webpage_url, audio_only=False):
    """Extract direct URL for a YouTube video when needed."""
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "format": "bestaudio[ext=mp3]/bestaudio/best" if audio_only else "best[ext=mp4]/best",
    }
    loop = asyncio.get_event_loop()
    def run_yt():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(webpage_url, download=False)
            if isinstance(info, dict) and "url" in info:
                return info["url"]
            return webpage_url
    return await loop.run_in_executor(None, run_yt)


def stream_all_in_vlc(urls, names):
    """Stream files in VLC media player."""
    if "terminal_output" not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()
    terminal = st.session_state.terminal_output
    terminal.add_line(f"Starting VLC streaming for {len(urls)} files", "info")
    try:
        if sys.platform == "darwin":
            with tempfile.NamedTemporaryFile("w", suffix=".m3u", delete=False) as m3u:
                for name, url in zip(names, urls):
                    m3u.write(f"#EXTINF:-1,{name}\n{url}\n")
                m3u_path = m3u.name
            subprocess.Popen(["open", "-a", "VLC", m3u_path])
            terminal.add_line("Launched VLC on macOS", "info")
        elif sys.platform == "win32":
            subprocess.Popen(["vlc"] + urls)
            terminal.add_line("Launched VLC on Windows", "info")
        else:
            # Linux: try default GUI first (no --intf), then qt; avoid dummy (headless, no window)
            vlc_paths = ["vlc", "/snap/bin/vlc", "/usr/bin/vlc", "/usr/local/bin/vlc"]
            vlc_found = False
            for vlc_path in vlc_paths:
                try:
                    result = subprocess.run([vlc_path, "--version"], capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        terminal.add_line(f"Found VLC at: {vlc_path}", "info")
                        # Try default (opens GUI) then qt; do not use dummy (no window)
                        for vlc_args in [
                            [vlc_path] + urls,
                            [vlc_path, "--intf", "qt", "--no-video-title-show"] + urls,
                        ]:
                            try:
                                env = os.environ.copy()
                                env.setdefault("DISPLAY", ":0")
                                process = subprocess.Popen(
                                    vlc_args,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE,
                                    env=env,
                                    start_new_session=True,
                                )
                                time.sleep(1)
                                if process.poll() is None:
                                    terminal.add_line("VLC launched successfully", "info")
                                    vlc_found = True
                                    break
                            except Exception as e:
                                terminal.add_line(f"VLC launch attempt: {e}", "warning")
                                continue
                        if vlc_found:
                            break
                except Exception:
                    continue
            if not vlc_found:
                raise Exception("VLC not found or could not start. Install with: sudo apt install vlc")
    except Exception as e:
        terminal.add_line(f"VLC streaming error: {e}", "error")
        st.error(f"Failed to open VLC: {e}")
        st.info("Make sure VLC is installed. On Linux: `sudo apt install vlc`")
