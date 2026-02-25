import os
import threading
from pathlib import Path
from typing import List, Tuple

import streamlit as st

from .shell_utils import TerminalOutput, check_command_exists, ensure_terminal, run_shell_command_with_output

TORRENT_EXTENSIONS = (".torrent",)
MAGNET_PREFIX = "magnet:?"


def is_torrent_link(url: str) -> bool:
    if not url:
        return False
    u = url.strip()
    if u.lower().startswith(MAGNET_PREFIX):
        return True
    parsed = __import__("urllib.parse").urlparse(u)
    return parsed.path.lower().endswith(TORRENT_EXTENSIONS)


def start_torrent_download_with_aria2(torrent_url: str, download_dir: str) -> bool:
    os.makedirs(download_dir, exist_ok=True)

    terminal = ensure_terminal()

    if not check_command_exists("aria2c"):
        terminal.add_line("aria2c is not installed; cannot start torrent download.", "error")
        return False

    url = torrent_url.strip()
    if not is_torrent_link(url):
        terminal.add_line("The provided link does not look like a torrent or magnet link.", "error")
        return False

    parent_pid = os.getpid()
    cmd = f"aria2c --seed-time=0 --stop-with-process={parent_pid} --dir='{download_dir}' '{url}'"

    def _run() -> None:
        terminal.add_line(f"Starting aria2c torrent download into {download_dir}", "info")
        result = run_shell_command_with_output(cmd, timeout=86400, show_in_terminal=True)
        if result["success"]:
            terminal.add_line("✅ Torrent download completed.", "success")
        else:
            terminal.add_line(
                f"❌ Torrent download exited with code {result.get('returncode')}", "error"
            )

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return True


def stream_torrent_via_webtorrent(torrent_ref: str) -> bool:
    terminal = ensure_terminal()

    if not check_command_exists("webtorrent"):
        terminal.add_line(
            "webtorrent-cli is not installed; cannot stream torrent directly.", "error"
        )
        st.error(
            "The `webtorrent` CLI is required to stream torrents without downloading. "
            "Install with: npm install -g webtorrent-cli"
        )
        return False

    ref = torrent_ref.strip()
    if not ref:
        terminal.add_line("No torrent reference provided for streaming.", "error")
        return False

    cmd = f'webtorrent "{ref}" --vlc'

    def _run() -> None:
        terminal.add_line("Starting webtorrent streaming to VLC...", "info")
        result = run_shell_command_with_output(cmd, timeout=86400, show_in_terminal=True)
        if result.get("returncode") not in (0, None):
            terminal.add_line(f"webtorrent exited with code {result.get('returncode')}", "warning")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return True


def collect_torrent_video_files(root_dir: str, video_extensions: Tuple[str, ...]) -> List[str]:
    video_paths: List[str] = []
    if not os.path.isdir(root_dir):
        return video_paths
    try:
        for root, _dirs, files_in_dir in os.walk(root_dir):
            for entry in files_in_dir:
                if entry.lower().endswith(video_extensions):
                    full = os.path.join(root, entry)
                    if os.path.isfile(full):
                        video_paths.append(full)
    except Exception:
        return []
    return video_paths


