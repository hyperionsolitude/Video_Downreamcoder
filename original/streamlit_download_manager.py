import streamlit as st
import aiohttp
import asyncio
import os
import urllib.parse
from bs4 import BeautifulSoup, Tag
import subprocess
import sys
import time
import re
import shutil
import threading
import tempfile
import yt_dlp
import functools
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
from mutagen.id3._frames import APIC, TIT2, TPE1, TALB
from PIL import Image
import io
import json
# Limit how many files download at once
MAX_CONCURRENT_DOWNLOADS = 4


# --- CONFIG ---
BASE_DOWNLOAD_DIR = os.path.expanduser("~/Downloads/StreamlitDownloads")
VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm')
AUDIO_EXTENSIONS = ('.mp3', '.m4a', '.aac', '.ogg', '.wav', '.flac')
YOUTUBE_DOMAINS = ("youtube.com", "youtu.be")

# --- UTILS ---
def get_base_download_dir():
    # Use user-selected base dir if set, else default
    base = st.session_state.get('base_download_dir', BASE_DOWNLOAD_DIR)
    return os.path.expanduser(base)
def get_folder_name_from_url(url, playlist_title=None):
    """Get folder name from URL, using playlist title for YouTube playlists"""
    if is_youtube_url(url) and playlist_title:
        # Use playlist title for YouTube playlists
        safe_title = normalize_filename(playlist_title)
        return safe_title
    
    # Original logic for non-YouTube URLs
    parsed = urllib.parse.urlparse(url)
    path_parts = parsed.path.strip('/').split('/')
    last_part = path_parts[-1] if path_parts else None
    
    # If last part is empty or just a file extension, try the previous part
    if not last_part or '.' in last_part:
        last_part = path_parts[-2] if len(path_parts) > 1 else None
    
    return last_part or "downloads"

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

async def fetch_youtube_video_links(url, audio_only=False, playlist_limit=None):
    # Check if we have cached results for this URL
    cache_key = f"{url}_{audio_only}_{playlist_limit}"
    if hasattr(st.session_state, 'youtube_cache') and cache_key in st.session_state.youtube_cache:
        return st.session_state.youtube_cache[cache_key]
    
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': True,  # Use flat extraction for speed
        'format': 'bestaudio[ext=mp3]/bestaudio/best' if audio_only else 'best[ext=mp4]/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }] if audio_only else [],
    }
    
    # Add playlist limit if specified
    if playlist_limit:
        ydl_opts['playlist_items'] = f'1-{playlist_limit}'
    
    loop = asyncio.get_event_loop()
    def run_yt():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not isinstance(info, dict):
                return [], None
            entries = info.get('entries', None)
            # Extract playlist title
            playlist_title = info.get('title', 'YouTube_Playlist')
            if entries and isinstance(entries, list):
                # Playlist - use flat extraction for speed
                result = []
                for i, entry in enumerate(entries):
                    if not isinstance(entry, dict):
                        continue
                    webpage_url = entry.get('webpage_url') or entry.get('url')
                    title = entry.get('title', f"video_{i+1}")
                    artist = entry.get('artist') or entry.get('uploader') or ''
                    # Build unique file name
                    if artist:
                        base_name = f"{artist} - {title}"
                    else:
                        base_name = title
                    safe_name = normalize_filename(base_name)
                    result.append({
                        'name': safe_name + ('.mp3' if audio_only else '.mp4'),
                        'url': webpage_url,  # Use webpage_url for flat extraction
                        'yt_webpage_url': webpage_url,
                        'is_youtube': True,
                        'is_audio': audio_only,
                        'needs_url_extraction': True,  # Flag to extract actual URL later
                        'thumbnail_url': entry.get('thumbnail'),  # Store thumbnail URL
                        'video_id': entry.get('id'),  # Store video ID for metadata
                        'artist': artist,
                        'title': title
                    })
                return result, playlist_title
            else:
                title = info.get('title', 'youtube_audio' if audio_only else 'youtube_video')
                artist = info.get('artist') or info.get('uploader') or ''
                if artist:
                    base_name = f"{artist} - {title}"
                else:
                    base_name = title
                safe_name = normalize_filename(base_name)
                return [{
                    'name': safe_name + ('.mp3' if audio_only else '.mp4'),
                    'url': info.get('url') if info.get('url', '').startswith('http') else url,
                    'yt_webpage_url': url,
                    'is_youtube': True,
                    'is_audio': audio_only,
                    'needs_url_extraction': False,
                    'thumbnail_url': info.get('thumbnail'),
                    'video_id': info.get('id'),
                    'artist': artist,
                    'title': title
                }], title
    
    result, playlist_title = await loop.run_in_executor(None, run_yt)
    
    # Cache the result
    if not hasattr(st.session_state, 'youtube_cache'):
        st.session_state.youtube_cache = {}
    st.session_state.youtube_cache[cache_key] = (result, playlist_title)
    
    return result, playlist_title

async def get_youtube_direct_url(webpage_url, audio_only=False):
    """Extract direct URL for a YouTube video when needed"""
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'format': 'bestaudio[ext=mp3]/bestaudio/best' if audio_only else 'best[ext=mp4]/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }] if audio_only else [],
    }
    loop = asyncio.get_event_loop()
    def run_yt():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(webpage_url, download=False)
            if isinstance(info, dict) and 'url' in info:
                return info['url']
            return webpage_url
    return await loop.run_in_executor(None, run_yt)

async def fetch_video_links(url, playlist_limit=None):
    if is_youtube_url(url):
        files, playlist_title = await fetch_youtube_video_links(url, audio_only=audio_only, playlist_limit=playlist_limit)
        return files, playlist_title
    timeout = aiohttp.ClientTimeout(total=30)
    # Check if the URL is a direct file link
    if url.lower().endswith(VIDEO_EXTENSIONS + AUDIO_EXTENSIONS) or (audio_only and url.lower().endswith(AUDIO_EXTENSIONS)):
        filename = urllib.parse.unquote(os.path.basename(url))
        return [{
            'name': filename,
            'url': url,
            'is_audio': audio_only and url.lower().endswith(AUDIO_EXTENSIONS)
        }], None
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
                else:
                    href = None
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

async def download_and_embed_thumbnail(mp3_file_path, thumbnail_url, title, artist=None, album=None):
    """Download thumbnail and embed it into MP3 file along with metadata"""
    try:
        if st.session_state.get('stop_flag', {}).get('value'):
            return False
        print(f"🖼️ Downloading thumbnail from: {thumbnail_url}")
        # Download thumbnail
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(thumbnail_url) as response:
                if response.status == 200:
                    thumbnail_data = await response.read()
                    print(f"✅ Downloaded {len(thumbnail_data)} bytes of thumbnail data")
                    
                    # Process thumbnail with PIL
                    image = Image.open(io.BytesIO(thumbnail_data))
                    print(f"🖼️ Image format: {image.format}, Size: {image.size}, Mode: {image.mode}")
                    
                    # Convert to RGB if necessary and resize if too large
                    if image.mode != 'RGB':
                        image = image.convert('RGB')
                    
                    # Resize if too large (max 500x500 for MP3)
                    max_size = (500, 500)
                    if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                        image.thumbnail(max_size, Image.Resampling.LANCZOS)
                        print(f"🖼️ Resized image to: {image.size}")
                    
                    # Convert back to bytes
                    img_buffer = io.BytesIO()
                    image.save(img_buffer, format='JPEG', quality=85)
                    img_data = img_buffer.getvalue()
                    print(f"✅ Processed image: {len(img_data)} bytes")
                    
                    # Try to embed into audio file
                    try:
                        print(f"🎵 Attempting to embed metadata into: {mp3_file_path}")
                        
                        # Check if file is actually an MP3
                        try:
                            audio = MP3(mp3_file_path)
                            if audio.tags is None:
                                audio.tags = ID3()
                            
                            # Add thumbnail
                            audio.tags.add(APIC(
                                encoding=3,  # UTF-8
                                mime='image/jpeg',
                                type=3,  # Cover (front)
                                desc='Cover',
                                data=img_data
                            ))
                            
                            # Add title
                            if title:
                                audio.tags.add(TIT2(encoding=3, text=title))
                            
                            # Add artist if provided
                            if artist:
                                audio.tags.add(TPE1(encoding=3, text=artist))
                            
                            # Add album if provided
                            if album:
                                audio.tags.add(TALB(encoding=3, text=album))
                            
                            audio.save()
                            print(f"✅ Successfully embedded thumbnail and metadata into {mp3_file_path}")
                            return True
                            
                        except Exception as mp3_error:
                            print(f"⚠️ MP3 embedding failed: {mp3_error}")
                            
                            # Check if file is actually an MP3 by checking file header
                            with open(mp3_file_path, 'rb') as f:
                                header = f.read(3)
                                if header != b'ID3' and not header.startswith(b'\xff\xfb') and not header.startswith(b'\xff\xf3'):
                                    print(f"⚠️ File {mp3_file_path} is not a valid MP3 file. It might be M4A/AAC with wrong extension.")
                                    print(f"💡 Try installing FFmpeg for proper MP3 conversion: sudo apt install ffmpeg")
                                    return False
                            
                            # If it's a valid MP3 but embedding failed, try alternative approach
                            print(f"🔄 Trying alternative metadata embedding method...")
                            try:
                                # Try using mutagen's easy module
                                from mutagen.easyid3 import EasyID3
                                audio = EasyID3(mp3_file_path)
                                audio['title'] = [title] if title else []
                                audio['artist'] = [artist] if artist else []
                                audio['album'] = [album] if album else []
                                audio.save()
                                print(f"✅ Successfully embedded basic metadata into {mp3_file_path}")
                                return True
                            except Exception as easy_error:
                                print(f"⚠️ Alternative embedding also failed: {easy_error}")
                                return False
                                
                    except Exception as e:
                        print(f"⚠️ Could not embed metadata into {mp3_file_path}: {e}")
                        return False
                else:
                    print(f"⚠️ Could not download thumbnail from {thumbnail_url}. Status: {response.status}")
                    return False
    except Exception as e:
        print(f"⚠️ Error processing thumbnail for {mp3_file_path}: {e}")
        return False

async def get_youtube_thumbnail_url(webpage_url):
    """Extract thumbnail URL for a YouTube video"""
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': False,  # Need full extraction for thumbnails
    }
    loop = asyncio.get_event_loop()
    def run_yt():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(webpage_url, download=False)
            if isinstance(info, dict):
                # Try different thumbnail fields
                thumbnail = info.get('thumbnail') or info.get('thumbnails', [{}])[0].get('url') if info.get('thumbnails') else None
                return thumbnail
            return None
    return await loop.run_in_executor(None, run_yt)

def has_embedded_thumbnail(mp3_path):
    try:
        audio = MP3(mp3_path)
        if audio.tags is None:
            return False
        return any(isinstance(tag, APIC) for tag in audio.tags.values())
    except Exception:
        return False

async def download_file(file_url, file_name, pause_flag, stop_flag, status_dict, file_key, file_info=None):
    # --- Check if file already exists and is complete ---
    if os.path.exists(file_name):
        # For YouTube audio, check if MP3 is valid and has some size
        if file_info and file_info.get('is_youtube') and file_info.get('is_audio') and file_name.lower().endswith('.mp3'):
            try:
                audio = MP3(file_name)
                if audio.info.length > 1 and os.path.getsize(file_name) > 1024 * 100:  # >100KB and >1s
                    status_dict[file_key] = {'status': 'already downloaded', 'progress': 100}
                    return
            except Exception:
                pass  # If error, treat as incomplete and re-download
        else:
            # For direct downloads, check remote file size
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.head(file_url) as resp:
                        remote_size = int(resp.headers.get('content-length', 0))
                        local_size = os.path.getsize(file_name)
                        if remote_size > 0 and local_size == remote_size:
                            status_dict[file_key] = {'status': 'already downloaded', 'progress': 100}
                            return
            except Exception:
                pass  # If error, treat as incomplete and re-download
    # --- End existence check ---

    # If this is a YouTube audio file, use yt-dlp to download and convert to MP3
    if file_info and file_info.get('is_youtube') and file_info.get('is_audio') and file_name.lower().endswith('.mp3'):
        try:
            if st.session_state.get('stop_flag', {}).get('value'):
                return
            status_dict[file_key] = {'status': 'downloading', 'progress': 0}
            # Use yt-dlp to download and convert to MP3
            base_path = os.path.splitext(file_name)[0]  # Remove .mp3 extension
            output_dir = os.path.dirname(base_path)
            os.makedirs(output_dir, exist_ok=True)
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': base_path,  # No extension!
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
                'progress_hooks': [
                    lambda d: status_dict[file_key].update({
                        'status': d['status'],
                        'progress': d.get('downloaded_bytes', 0) / d.get('total_bytes', 1) * 100 if d.get('total_bytes') else 0
                    }) if d['status'] in ['downloading', 'finished'] else None
                ],
                'continuedl': True,  # Resume partially downloaded files
                'noprogress': False,
                'overwrites': False,  # Do not overwrite existing files
            }
            loop = asyncio.get_event_loop()
            def run_yt():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    try:
                        ydl.download([file_info['yt_webpage_url']])
                    except Exception as e:
                        # Handle 'Requested format is not available' error
                        err_str = str(e)
                        if 'Requested format is not available' in err_str:
                            # List available formats
                            info = ydl.extract_info(file_info['yt_webpage_url'], download=False)
                            # Find best available audio format
                            formats = info.get('formats', [])
                            audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('url')]
                            if not audio_formats:
                                status_dict[file_key] = {'status': 'error: No audio format available'}
                                return
                            # Pick the best audio format (highest abr)
                            best_audio = max(audio_formats, key=lambda f: f.get('abr', 0) or 0)
                            # Download with this format
                            alt_opts = ydl_opts.copy()
                            alt_opts['format'] = best_audio['format_id']
                            with yt_dlp.YoutubeDL(alt_opts) as alt_ydl:
                                alt_ydl.download([file_info['yt_webpage_url']])
                        else:
                            raise
            await loop.run_in_executor(None, run_yt)
            status_dict[file_key] = {'status': 'completed', 'progress': 100}
            # Embed thumbnail after download
            mp3_path = base_path + '.mp3'
            if not has_embedded_thumbnail(mp3_path):
                title = os.path.splitext(os.path.basename(mp3_path))[0]
                album = st.session_state.get('playlist_title', 'YouTube Audio')
                thumbnail_url = file_info.get('thumbnail_url')
                if not thumbnail_url and file_info.get('yt_webpage_url'):
                    print(f"🔍 Fetching thumbnail for {title}")
                    thumbnail_url = await get_youtube_thumbnail_url(file_info['yt_webpage_url'])
                if thumbnail_url:
                    print(f"🎵 Embedding thumbnail for {mp3_path}")
                    await download_and_embed_thumbnail(
                        mp3_path,
                        thumbnail_url,
                        title,
                        album=album
                    )
                else:
                    print(f"⚠️ No thumbnail available for {mp3_path}")
            else:
                print(f"🖼️ Thumbnail already embedded in {mp3_path}, skipping.")
            return
        except Exception as e:
            status_dict[file_key] = {'status': f'error: {e}'}
            return
    # Otherwise, use aiohttp for direct downloads
    timeout = aiohttp.ClientTimeout(total=99999)
    try:
        # --- Resume logic for direct downloads ---
        resume = False
        local_size = 0
        if os.path.exists(file_name):
            local_size = os.path.getsize(file_name)
            # Check remote size
            async with aiohttp.ClientSession() as session:
                async with session.head(file_url) as resp:
                    remote_size = int(resp.headers.get('content-length', 0))
                    if remote_size > 0 and local_size < remote_size:
                        resume = True
        headers = {}
        if resume and local_size > 0:
            headers['Range'] = f'bytes={local_size}-'
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(file_url, headers=headers) as response:
                # If resuming, append to file; else, write new
                mode = 'ab' if resume else 'wb'
                total_size = int(response.headers.get('content-length', 0))
                if resume and total_size > 0:
                    total_size += local_size
                downloaded = local_size
                start_time = time.time()
                last_update_time = start_time
                # Initialize status dict for this file
                status_dict[file_key] = {
                    'status': 'downloading',
                    'downloaded': downloaded,
                    'total_size': total_size,
                    'speed': 0,
                    'eta': 0,
                    'progress': (downloaded / total_size) * 100 if total_size > 0 else 0
                }
                with open(file_name, mode) as f:
                    async for chunk in response.content.iter_chunked(8192):
                        if stop_flag['value']:
                            status_dict[file_key] = {'status': 'stopped'}
                            return
                        while pause_flag['value']:
                            status_dict[file_key]['status'] = 'paused'
                            await asyncio.sleep(0.2)
                        f.write(chunk)
                        downloaded += len(chunk)
                        current_time = time.time()
                        # Update progress every 0.5 seconds
                        if current_time - last_update_time > 0.5:
                            elapsed = current_time - start_time
                            if elapsed > 0:
                                speed = (downloaded - local_size) / elapsed  # bytes per second
                                if total_size > 0:
                                    progress = (downloaded / total_size) * 100
                                    remaining = total_size - downloaded
                                    eta = remaining / speed if speed > 0 else 0
                                else:
                                    progress = 0
                                    eta = 0
                                status_dict[file_key].update({
                                    'status': 'downloading',
                                    'downloaded': downloaded,
                                    'total_size': total_size,
                                    'speed': speed,
                                    'eta': eta,
                                    'progress': progress
                                })
                            last_update_time = current_time
                # Final update
                status_dict[file_key] = {'status': 'completed'}
    except Exception as e:
        status_dict[file_key] = {'status': f'error: {e}'}

def normalize_filename(filename):
    # Replace forbidden/special characters with underscores
    # Remove newlines and replace forbidden characters
    filename = filename.replace('\n', '_').replace('\r', '_')
    filename = re.sub(r'[\\/:*?"<>|]', '_', filename)
    # Collapse multiple underscores
    filename = re.sub(r'_+', '_', filename)
    # Remove leading/trailing whitespace and underscores
    filename = filename.strip(' _')
    # Optionally, limit length
    return filename[:200]

# --- Episode/merge helpers ---
EPISODE_REGEXES = [
    re.compile(r'(?:^|[^\d])(\d{1,3})(?:[^\d]|$)'),
    re.compile(r'[\-_\s]e(?:p|pisode)?[\-_\s]*(\d{1,3})', re.IGNORECASE),
    re.compile(r'[\-_\s](\d{1,3})(?=[\._\s])')
]

def extract_episode_number_from_filename(name):
    base = os.path.basename(name)
    # Prefer patterns with explicit separators
    for rx in [
        re.compile(r'[\s_\-]+(\d{1,3})(?=\D|$)'),
        re.compile(r'climax[\s_\-]*-[\s_]*(\d{1,3})', re.IGNORECASE),
        re.compile(r'e(?:p|pisode)?[\s_\-]*(\d{1,3})', re.IGNORECASE),
    ]:
        m = rx.search(base)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
    # Fallback generic search
    for rx in EPISODE_REGEXES:
        m = rx.search(base)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
    return None

def list_episode_video_files_sorted(folder_path):
    """List video files sorted by episode number for merging"""
    all_entries = []
    if not os.path.isdir(folder_path):
        return []
    for entry in os.listdir(folder_path):
        name_lc = entry.lower()
        # Exclude already merged outputs and temp/partial files
        if name_lc.endswith(VIDEO_EXTENSIONS) and '_merged' not in name_lc and '(merged' not in name_lc:
            ep = extract_episode_number_from_filename(entry)
            all_entries.append((ep if ep is not None else 10**9, entry))
    all_entries.sort(key=lambda t: (t[0], t[1].lower()))
    return [os.path.join(folder_path, name) for _, name in all_entries]

# Video encoding and merging functionality moved to video_encoder.sh
# This keeps the Streamlit app focused on downloading only

def copy_video_encoder_script(download_dir):
    """Copy the video_encoder.sh script to the download directory"""
    script_source = "/media/ubuntu/ST1000LM010/Downloads/video_encoder.sh"
    script_dest = os.path.join(download_dir, "video_encoder.sh")
    
    if os.path.exists(script_source) and not os.path.exists(script_dest):
        try:
            shutil.copy2(script_source, script_dest)
            # Make it executable
            os.chmod(script_dest, 0o755)
            return True
        except Exception as e:
            print(f"Failed to copy video_encoder.sh: {e}")
            return False
    return os.path.exists(script_dest)

# --- Persistence helpers ---
STATUS_FILE = 'download_status.json'
def save_status_to_disk():
    try:
        data = {
            'file_status': st.session_state.get('file_status', {}),
            'video_files': st.session_state.get('video_files', []),
            'selected_files': st.session_state.get('selected_files', []),
            'current_folder': st.session_state.get('current_folder', ''),
            'playlist_title': st.session_state.get('playlist_title', ''),
            'current_url': st.session_state.get('current_url', ''),
            'base_download_dir': st.session_state.get('base_download_dir', BASE_DOWNLOAD_DIR),
        }
        with open(STATUS_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Error saving status: {e}")

def load_status_from_disk():
    try:
        with open(STATUS_FILE, 'r') as f:
            data = json.load(f)
        st.session_state['file_status'] = data.get('file_status', {})
        st.session_state['video_files'] = data.get('video_files', [])
        st.session_state['selected_files'] = data.get('selected_files', [])
        st.session_state['current_folder'] = data.get('current_folder', '')
        st.session_state['playlist_title'] = data.get('playlist_title', '')
        st.session_state['current_url'] = data.get('current_url', '')
        st.session_state['base_download_dir'] = data.get('base_download_dir', BASE_DOWNLOAD_DIR)
    except Exception as e:
        print(f"Error loading status: {e}")

# --- Download Thread Function ---
def download_all_parallel(files, selected, download_dir, pause_flag, stop_flag, status_dict, set_downloading_false, current_folder):
    async def _download():
        thumbnail_cache = {}
        thumbnail_results = {}
        # Download ALL selected files in parallel (no artificial cap)
        total_selected = sum(1 for f in files if f['name'] in selected)
        sem = asyncio.Semaphore(max(1, total_selected))
        async def get_or_download_thumbnail(url):
            if not url:
                return None
            if url in thumbnail_cache:
                return thumbnail_cache[url]
            try:
                timeout = aiohttp.ClientTimeout(total=30)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.read()
                            thumbnail_cache[url] = data
                            return data
            except Exception:
                pass
            return None
        async def process_and_download(file):
            if file['name'] not in selected:
                return None
            async with sem:
                safe_name = normalize_filename(file['name'])
                file_path = os.path.join(download_dir, safe_name)
                file_url = file['url']
                if file.get('needs_url_extraction') and file.get('is_youtube'):
                    file_url = await get_youtube_direct_url(file['yt_webpage_url'], file.get('is_audio', False))
                # Patch download_file to use cached thumbnail logic
                async def patched_download_file(*args, **kwargs):
                    orig_download_and_embed_thumbnail = globals()['download_and_embed_thumbnail']
                    async def patched_embed(mp3_file_path, thumbnail_url, title, artist=None, album=None):
                        cache_key = (mp3_file_path, thumbnail_url)
                        if cache_key in thumbnail_results and not thumbnail_results[cache_key]:
                            data = await get_or_download_thumbnail(thumbnail_url)
                        else:
                            data = await get_or_download_thumbnail(thumbnail_url)
                        if data is None:
                            thumbnail_results[cache_key] = False
                            return False
                        try:
                            audio = MP3(mp3_file_path)
                            if audio.tags is None:
                                audio.tags = ID3()
                            audio.tags.add(APIC(
                                encoding=3,
                                mime='image/jpeg',
                                type=3,
                                desc='Cover',
                                data=data
                            ))
                            if title:
                                audio.tags.add(TIT2(encoding=3, text=title))
                            if artist:
                                audio.tags.add(TPE1(encoding=3, text=artist))
                            if album:
                                audio.tags.add(TALB(encoding=3, text=album))
                            audio.save()
                            thumbnail_results[cache_key] = True
                            return True
                        except Exception:
                            thumbnail_results[cache_key] = False
                            return False
                    globals()['download_and_embed_thumbnail'] = patched_embed
                    try:
                        result = await orig_download_file(*args, **kwargs)
                        save_status_to_disk()
                        return result
                    finally:
                        globals()['download_and_embed_thumbnail'] = orig_download_and_embed_thumbnail
                orig_download_file = globals()['download_file']
                globals()['download_file'] = patched_download_file
                try:
                    result = await orig_download_file(
                        file_url,
                        file_path,
                        pause_flag,
                        stop_flag,
                        status_dict,
                        file['name'],
                        file
                    )
                    save_status_to_disk()
                    return result
                except Exception as e:
                    # Mark this file as error and continue
                    status_dict[file['name']] = {'status': f'error: {e}'}
                    save_status_to_disk()
                    return None
                finally:
                    globals()['download_file'] = orig_download_file

        # Run all selected downloads concurrently up to MAX_CONCURRENT_DOWNLOADS
        tasks = [asyncio.create_task(process_and_download(f)) for f in files if f['name'] in selected]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        set_downloading_false()
        save_status_to_disk()
    try:
        asyncio.run(_download())
    except Exception as e:
        print(f"Download error: {e}")
        set_downloading_false()

async def prepare_streaming_urls(files, selected):
    """Prepare direct URLs for streaming, handling YouTube URL extraction"""
    urls = []
    names = []
    
    for file in files:
        if file['name'] in selected:
            names.append(file['name'])
            
            # Get the actual URL for YouTube videos that need extraction
            if file.get('needs_url_extraction') and file.get('is_youtube'):
                direct_url = await get_youtube_direct_url(file['yt_webpage_url'], file.get('is_audio', False))
                urls.append(direct_url)
            else:
                urls.append(file['url'])
    
    return urls, names

# --- Streaming Function ---
def stream_all_in_vlc(urls, names):
    print("=" * 60)
    print("🎬 VLC STREAMING STARTED")
    print("=" * 60)
    print(f"Attempting to stream {len(urls)} files in VLC:")
    for i, (name, url) in enumerate(zip(names, urls)):
        print(f"  {i+1}. {name}")
        print(f"     URL: {url}")
        print(f"     Extension: {os.path.splitext(name)[1] if '.' in name else 'No extension'}")
        print()
    print("=" * 60)
    print("🔧 VLC LAUNCH ATTEMPT")
    print("=" * 60)
    try:
        if sys.platform == "darwin":
            with tempfile.NamedTemporaryFile('w', suffix='.m3u', delete=False) as m3u:
                for name, url in zip(names, urls):
                    m3u.write(f'#EXTINF:-1,{name}\n{url}\n')
                m3u_path = m3u.name
            subprocess.Popen(["open", "-a", "VLC", m3u_path])
        elif sys.platform == "win32":
            subprocess.Popen(["vlc"] + urls)
        else:
            vlc_paths = ["vlc", "/snap/bin/vlc", "/usr/bin/vlc", "/usr/local/bin/vlc"]
            vlc_found = False
            for vlc_path in vlc_paths:
                try:
                    result = subprocess.run([vlc_path, "--version"], capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        print(f"Found VLC at: {vlc_path}")
                        print(f"Launching VLC with URLs: {urls}")
                        try:
                            vlc_interfaces = ["qt", "dummy", "ncurses"]
                            vlc_launched = False
                            for interface in vlc_interfaces:
                                try:
                                    print(f"🔧 Trying VLC with interface: {interface}")
                                    print(f"   URLs to stream: {urls}")
                                    print(f"   Number of URLs: {len(urls)}")
                                    vlc_args = [vlc_path, "--intf", interface]
                                    if interface == "qt":
                                        vlc_args.extend(["--no-video-title-show"])
                                    elif interface == "dummy":
                                        vlc_args.extend(["--play-and-exit"])
                                    vlc_args.extend(urls)
                                    print(f"🔧 VLC command: {' '.join(vlc_args)}")
                                    print(f"🔧 Full command length: {len(' '.join(vlc_args))} characters")
                                    env = os.environ.copy()
                                    env['DISPLAY'] = ':0'
                                    env['QT_QPA_PLATFORM'] = 'xcb'
                                    process = subprocess.Popen(vlc_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
                                    print(f"VLC process started with PID: {process.pid}")
                                    import time
                                    time.sleep(2)
                                    if process.poll() is None:
                                        print(f"VLC is running successfully with {interface} interface")
                                        vlc_launched = True
                                        break
                                    else:
                                        stdout, stderr = process.communicate()
                                        print(f"VLC failed with {interface} interface. stdout: {stdout}, stderr: {stderr}")
                                        continue
                                except Exception as interface_error:
                                    print(f"Failed to launch VLC with {interface} interface: {interface_error}")
                                    continue
                            if vlc_launched:
                                vlc_found = True
                                break
                        except Exception as launch_error:
                            print(f"Failed to launch VLC: {launch_error}")
                            continue
                except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
                    print(f"VLC path {vlc_path} failed: {e}")
                    continue
            if not vlc_found:
                raise Exception("VLC not found. Please install VLC or ensure it's in your PATH.")
            print("VLC found and will attempt to launch...")
    except Exception as e:
        print(f"VLC streaming error: {e}")
        st.error(f"Failed to open VLC: {e}")
        st.info("Make sure VLC is installed and accessible. On Linux, try: sudo apt install vlc")

# --- STREAMLIT APP ---
if 'file_status' not in st.session_state or not st.session_state.get('file_status'):
    load_status_from_disk()

st.set_page_config(page_title="Streamlit Download Manager", layout="wide")
st.title("📥 Streamlit Download Manager")

col_head_left, col_head_right = st.columns([3,1])
with col_head_left:
    audio_only = st.checkbox("Audio Only (YouTube: bestaudio, Direct: audio files)", value=False)
with col_head_right:
    st.session_state['max_concurrency'] = st.number_input("Max parallel downloads", min_value=1, max_value=16, value=int(st.session_state.get('max_concurrency', MAX_CONCURRENT_DOWNLOADS)))

# Add playlist limit option for YouTube
playlist_limit = st.number_input(
    "Playlist Limit (YouTube only, 0 = no limit):", 
    min_value=0, 
    max_value=1000, 
    value=0,
    help="Limit the number of videos fetched from YouTube playlists. Set to 0 for no limit."
)

st.markdown(f"""
- Enter a URL to a directory of video files (e.g. an open directory listing)
- Select files to download or stream
- Downloads are saved to: `{get_base_download_dir()}/<folder_from_url>`
- **For video merging/encoding:** Use the `video_encoder.sh` script (automatically copied to download folders)
""")

# Base download directory chooser
with st.expander("Download Location", expanded=False):
    cur_base = st.text_input("Base download directory", value=str(st.session_state.get('base_download_dir', get_base_download_dir())), help="Parent folder under which a subfolder per URL/playlist is created.")
    col_bd1, col_bd2 = st.columns([1,1])
    with col_bd1:
        if st.button("Use Default (~/Downloads/StreamlitDownloads)"):
            st.session_state['base_download_dir'] = BASE_DOWNLOAD_DIR
            save_status_to_disk()
            st.success(f"Set base directory to {BASE_DOWNLOAD_DIR}")
    with col_bd2:
        if st.button("Save Location"):
            st.session_state['base_download_dir'] = os.path.expanduser(cur_base)
            os.makedirs(st.session_state['base_download_dir'], exist_ok=True)
            save_status_to_disk()
            st.success(f"Base directory set to {st.session_state['base_download_dir']}")

url = st.text_input("Enter video directory URL:", "")

if st.button("Fetch Video List") or 'video_files' not in st.session_state:
    if url:
        if is_youtube_url(url) and playlist_limit and playlist_limit > 50:
            st.info(f"⏳ Fetching up to {playlist_limit} videos from YouTube playlist. This may take a while for large playlists...")
        
        with st.spinner("Fetching video list..."):
            files, playlist_title = asyncio.run(fetch_video_links(url, playlist_limit=playlist_limit if playlist_limit > 0 else None))
            st.session_state['video_files'] = files
            st.session_state['selected_files'] = []
            st.session_state['current_folder'] = get_folder_name_from_url(url, playlist_title)
            st.session_state['file_status'] = {}
            st.session_state['is_downloading'] = False
            st.session_state['pause_flag'] = {'value': False}
            st.session_state['stop_flag'] = {'value': False}
            st.session_state['playlist_title'] = playlist_title
            st.session_state['current_url'] = url
            save_status_to_disk()
    else:
        st.warning("Please enter a URL.")

files = st.session_state.get('video_files', [])
current_folder = st.session_state.get('current_folder', 'downloads')
playlist_title = st.session_state.get('playlist_title', None)

# Show playlist title for YouTube playlists
if playlist_title and 'current_url' in st.session_state and is_youtube_url(st.session_state['current_url']):
    st.success(f"📁 Playlist: {playlist_title}")
    st.info(f"📂 Downloads will go to: {os.path.join(BASE_DOWNLOAD_DIR, current_folder)}")

# --- Multiselect with full session state sync ---
def on_multiselect_change():
    st.session_state['selected_files'] = st.session_state['file_multiselect']

if 'selected_files' not in st.session_state:
    st.session_state['selected_files'] = []
if 'file_status' not in st.session_state:
    st.session_state['file_status'] = {}
if 'is_downloading' not in st.session_state:
    st.session_state['is_downloading'] = False
if 'pause_flag' not in st.session_state:
    st.session_state['pause_flag'] = {'value': False}
if 'stop_flag' not in st.session_state:
    st.session_state['stop_flag'] = {'value': False}

if files:
    st.success(f"Found {len(files)} video files.")
    st.info(f"Downloads will go to: {os.path.join(get_base_download_dir(), current_folder)}")

    col_select, col_deselect = st.columns([1,1])
    with col_select:
        if st.button("Select All", key="select_all_btn"):
            st.session_state['selected_files'] = [f['name'] for f in files]
            st.session_state['file_multiselect'] = st.session_state['selected_files']
            try:
                st.rerun()
            except AttributeError:
                pass
    with col_deselect:
        if st.button("Deselect All", key="deselect_all_btn"):
            st.session_state['selected_files'] = []
            st.session_state['file_multiselect'] = []
            try:
                st.rerun()
            except AttributeError:
                pass

    # Filter controls
    col_filter, col_clear_filter = st.columns([3, 1])
    with col_filter:
        filter_input = st.text_input(
            "🔍 Filter files (indexes: 1,3,4 or ranges: 1-6 or extensions: mp4,mkv or text: episode):",
            placeholder="e.g., 1-6 or 1,3,4 or mp4,mkv or episode",
            help="Filter by: indexes (1,3,4), ranges (1-6), extensions (mp4,mkv), or text in filename"
        )
    with col_clear_filter:
        if st.button("Clear Filter", key="clear_filter_btn"):
            filter_input = ""
            try:
                st.rerun()
            except AttributeError:
                pass

    # Apply filters
    filtered_files = files.copy()
    if filter_input:
        filter_terms = [term.strip().lower() for term in filter_input.split(',')]
        def is_numeric_or_range(term):
            if term.isdigit():
                return True
            if '-' in term:
                parts = term.split('-')
                return all(p.isdigit() for p in parts)
            return False
        filtered = []
        for i, f in enumerate(files):
            name = f['name'].lower()
            match = False
            for term in filter_terms:
                if is_numeric_or_range(term):
                    if '-' in term:
                        start, end = map(int, term.split('-'))
                        if start <= i+1 <= end:
                            match = True
                    elif term.isdigit() and int(term) == i+1:
                        match = True
                elif term in name:
                    match = True
                elif any(name.endswith('.'+ext) for ext in term.split('.')):
                    match = True
            if match:
                filtered.append(f)
        filtered_files = filtered

    selected = st.multiselect(
        "Select files to download or stream:",
        [f['name'] for f in filtered_files],
        default=st.session_state.get('selected_files', []),
        key='file_multiselect',
        on_change=on_multiselect_change
    )

    # --- Download/Stream Buttons ---
    col1, col2 = st.columns([2, 2])
    with col1:
        if st.button("Download Selected", key="download_btn"):
            if not selected:
                st.warning("No files selected for download!")
            else:
                st.session_state['is_downloading'] = True
                download_dir = ensure_download_dir(current_folder)
                files_to_download = [f for f in files if f['name'] in selected]
                def set_downloading_false():
                    st.session_state['is_downloading'] = False
                    # Copy video encoder script to download folder
                    copy_video_encoder_script(download_dir)
                import threading
                threading.Thread(
                    target=download_all_parallel,
                    args=(files_to_download, [f['name'] for f in files_to_download], download_dir, st.session_state['pause_flag'], st.session_state['stop_flag'], st.session_state['file_status'], set_downloading_false, current_folder),
                    daemon=True
                ).start()
    # --- Manual Cleanup Buttons ---
    with col2:
        if st.button("Delete Incomplete/Failed Files", key="cleanup_incomplete_btn"):
            file_status = st.session_state.get('file_status', {})
            for f in files:
                name = f['name']
                status = file_status.get(name, {}).get('status')
                if status not in ['completed', 'already downloaded']:
                    file_path = os.path.join(ensure_download_dir(current_folder), name)
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except Exception as e:
                            st.warning(f"Could not delete {name}: {e}")
            st.success("Incomplete/failed files deleted.")
        if st.button("Delete Entire Download Folder", key="cleanup_folder_btn"):
            folder_path = ensure_download_dir(current_folder)
            try:
                shutil.rmtree(folder_path)
                st.success("Download folder deleted.")
            except Exception as e:
                st.warning(f"Could not delete folder: {e}")
        
        st.markdown("---")
        
        # Check if video encoder script is available
        download_dir = ensure_download_dir(current_folder)
        script_available = copy_video_encoder_script(download_dir)
        
        if script_available:
            st.success("✅ Video encoder script is ready!")
            st.info("💡 **For video merging/encoding:** Use the `video_encoder.sh` script in the download folder after downloads complete.")
            st.code(f"cd {download_dir}\n./video_encoder.sh . --menu", language="bash")
            
            # Show available video files for merging
            video_files = list_episode_video_files_sorted(download_dir)
            if len(video_files) >= 2:
                st.info(f"📁 Found {len(video_files)} video files ready for merging:")
                for i, file_path in enumerate(video_files[:5]):  # Show first 5
                    st.text(f"  {i+1}. {os.path.basename(file_path)}")
                if len(video_files) > 5:
                    st.text(f"  ... and {len(video_files) - 5} more")
        else:
            st.warning("⚠️ Video encoder script not available. Please ensure video_encoder.sh is in the Downloads folder.")

    # --- Real-time Download Status ---
    st.markdown("### Download Status")
    status_placeholder = st.empty()
    progress_placeholder = st.empty()
    # Show Pause/Stop only when downloading
    if st.session_state.get('is_downloading', False):
        file_status = st.session_state.get('file_status', {})
        completed_files = sum(1 for name in selected if file_status.get(name, {}).get('status') in ['completed', 'already downloaded'])
        failed_files = sum(1 for name in selected if str(file_status.get(name, {}).get('status', '')).startswith('error'))
        total_selected = len(selected)
        processed_files = completed_files + failed_files
        
        if completed_files == total_selected and total_selected > 0:
            st.success("🎉 All files have been downloaded and completed!")
        elif processed_files == total_selected and total_selected > 0:
            st.warning(f"📊 Download session completed: {completed_files} successful, {failed_files} failed out of {total_selected} total files.")
        else:
            col_pause, col_stop = st.columns([1, 1])
            with col_pause:
                if st.session_state['pause_flag']['value']:
                    if st.button("Resume", key="resume_btn"):
                        st.session_state['pause_flag']['value'] = False
                        # Prioritize retrying error files first
                        file_status = st.session_state.get('file_status', {})
                        # DO NOT reset selected_files or file_status here!
                        error_files = [f for f in files if f['name'] in st.session_state['selected_files'] and str(file_status.get(f['name'], {}).get('status', '')).startswith('error')]
                        not_downloaded_files = [f for f in files if f['name'] in st.session_state['selected_files'] and file_status.get(f['name'], {}).get('status') not in ['completed', 'already downloaded'] and not str(file_status.get(f['name'], {}).get('status', '')).startswith('error')]
                        files_to_download = error_files + not_downloaded_files
                        if files_to_download:
                            st.session_state['is_downloading'] = True
                            download_dir = ensure_download_dir(current_folder)
                            def set_downloading_false():
                                st.session_state['is_downloading'] = False
                            import threading
                            threading.Thread(
                                target=download_all_parallel,
                                args=(files_to_download, [f['name'] for f in files_to_download], download_dir, st.session_state['pause_flag'], st.session_state['stop_flag'], st.session_state['file_status'], set_downloading_false, current_folder),
                                daemon=True
                            ).start()
                        try:
                            st.rerun()
                        except AttributeError:
                            pass
                else:
                    if st.button("Pause", key="pause_btn"):
                        st.session_state['pause_flag']['value'] = True
                        try:
                            st.rerun()
                        except AttributeError:
                            pass
            with col_stop:
                if st.button("Stop", key="stop_btn"):
                    st.session_state['stop_flag']['value'] = True
                    st.session_state['is_downloading'] = False
                    # No automatic folder removal here!
                    try:
                        st.rerun()
                    except AttributeError:
                        pass
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
        progress_placeholder.progress(progress, text=f"Progress: {processed_files}/{total_selected} processed ({completed_files} successful, {failed_files} failed)")
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
        time.sleep(poll_interval)
    # Final update after downloads
    file_status = st.session_state.get('file_status', {})
    completed_files = sum(1 for name in selected if file_status.get(name, {}).get('status') in ['completed', 'already downloaded'])
    failed_files = sum(1 for name in selected if str(file_status.get(name, {}).get('status', '')).startswith('error'))
    total_selected = len(selected)
    processed_files = completed_files + failed_files
    progress = processed_files / total_selected if total_selected > 0 else 0
    progress_placeholder.progress(progress, text=f"Progress: {processed_files}/{total_selected} processed ({completed_files} successful, {failed_files} failed)")
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
    # Merge functionality moved to video_encoder.sh