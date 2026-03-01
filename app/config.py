"""Application constants and configuration."""

import os

BASE_DOWNLOAD_DIR = os.path.expanduser("~/Downloads/StreamlitDownloads")
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm")
AUDIO_EXTENSIONS = (".mp3", ".m4a", ".aac", ".ogg", ".wav", ".flac")
YOUTUBE_DOMAINS = ("youtube.com", "youtu.be")
TORRENT_EXTENSIONS = (".torrent",)
MAGNET_PREFIX = "magnet:?"
MAX_CONCURRENT_DOWNLOADS = 4
