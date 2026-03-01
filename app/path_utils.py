"""Path and URL utilities for download manager."""

import os
import re
import shutil
import urllib.parse

import streamlit as st

from .config import BASE_DOWNLOAD_DIR, YOUTUBE_DOMAINS


def get_base_download_dir():
    base = st.session_state.get("base_download_dir", BASE_DOWNLOAD_DIR)
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
    """Normalize filename for safe filesystem usage."""
    filename = filename.replace("\n", "_").replace("\r", "_")
    filename = re.sub(r'[\\/:*?"<>|]', "_", filename)
    filename = re.sub(r"_+", "_", filename)
    filename = filename.strip(" _")
    return filename[:200]


def get_folder_name_from_url(url, playlist_title=None):
    """Get folder name from URL, using playlist title for YouTube playlists."""
    if is_youtube_url(url) and playlist_title:
        return normalize_filename(playlist_title)

    parsed = urllib.parse.urlparse(url)
    path_parts = parsed.path.strip("/").split("/")
    last_part = path_parts[-1] if path_parts else None

    if not last_part or "." in last_part:
        last_part = path_parts[-2] if len(path_parts) > 1 else None

    return last_part or "downloads"
