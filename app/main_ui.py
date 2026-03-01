"""
Streamlit UI: main page and layout.
"""
import asyncio
import os
import subprocess

import streamlit as st

from .config import BASE_DOWNLOAD_DIR, VIDEO_EXTENSIONS
from .path_utils import get_base_download_dir, get_folder_name_from_url, is_youtube_url, ensure_download_dir
from .shell_utils import TerminalOutput, check_command_exists, ensure_terminal, run_shell_command
from .platform_utils import PLATFORM_CONFIG
from .prerequisites import install_prerequisites, install_torrent_options, detect_hardware_acceleration
from .download import (
    fetch_video_links,
    download_all_files,
    prepare_streaming_urls,
    stream_all_in_vlc,
    start_torrent_download_with_aria2,
    stream_torrent_via_webtorrent,
)
from .encoding import (
    create_video_encoder_script,
    list_video_files,
    get_video_info,
    encode_videos_direct,
    encode_videos_shell,
)
from .torrent import is_torrent_link, collect_torrent_video_files


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
    
    # Run torrent-only install if user clicked "Install torrent options" (e.g. when webtorrent was missing)
    if st.session_state.get('install_torrent_options_started', False):
        if 'terminal_output' not in st.session_state:
            st.session_state.terminal_output = TerminalOutput()
        with st.spinner("Installing torrent options (Node.js + webtorrent-cli)..."):
            ok = install_torrent_options(st.session_state.terminal_output)
        st.session_state['install_torrent_options_started'] = False
        if ok:
            st.success("Torrent options installed. Try streaming again.")
        st.rerun()
    
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
                commands = ['ffmpeg', 'wget', 'curl', 'yt-dlp', 'aria2c', 'webtorrent']
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
                terminal = ensure_terminal()
                terminal.clear()
                st.rerun()
        
        with col_auto:
            auto_refresh = st.checkbox("🔄 Auto-refresh (2s)", value=True, help="Automatically refresh terminal every 2 seconds")
        
        # Get terminal output (ensure terminal is initialized first)
        terminal = ensure_terminal()
        terminal_output = terminal.get_output()
        
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
    
    # Torrent download section
    with st.expander("Torrent Download (magnet or .torrent URL)", expanded=False):
        torrent_url = st.text_input("Torrent / magnet link:", "", key="torrent_url_input")
        torrent_folder = st.text_input(
            "Torrent download folder name",
            "torrents",
            key="torrent_folder_name",
            help="Subfolder inside the base download directory where torrent contents will be saved.",
        )
        uploaded_torrent = st.file_uploader(
            "Or select a local .torrent file",
            type=["torrent"],
            key="torrent_file_upload",
            help="If provided, the uploaded .torrent file will be saved and used for downloading."
        )
        # Compute current target directory for reuse below
        base_dir = get_base_download_dir()
        default_torrent_dir = os.path.join(base_dir, torrent_folder)
        st.info(f"📂 Torrent files will be saved under: `{default_torrent_dir}`")
        if st.button("Start Torrent Download", key="start_torrent_download"):
            if not torrent_url:
                st.warning("Please enter a torrent or magnet link.")
            else:
                os.makedirs(default_torrent_dir, exist_ok=True)
                if not check_command_exists("aria2c"):
                    st.error("The aria2c command is required for torrent downloads. For example on macOS: brew install aria2.")
                else:
                    started = start_torrent_download_with_aria2(torrent_url, default_torrent_dir)
                    if started:
                        st.success(f"Started torrent download into: {default_torrent_dir}. Check the Terminal Output section for live logs.")
        if st.button("Start Torrent from Local .torrent", key="start_torrent_from_file"):
            if not uploaded_torrent:
                st.warning("Please select a .torrent file first.")
            else:
                os.makedirs(default_torrent_dir, exist_ok=True)
                local_torrent_path = os.path.join(default_torrent_dir, uploaded_torrent.name)
                try:
                    with open(local_torrent_path, "wb") as f:
                        f.write(uploaded_torrent.getbuffer())
                except Exception as e:
                    st.error(f"Failed to save uploaded .torrent file: {e}")
                else:
                    if not check_command_exists("aria2c"):
                        st.error("The aria2c command is required for torrent downloads. For example on macOS: brew install aria2.")
                    else:
                        started = start_torrent_download_with_aria2(local_torrent_path, default_torrent_dir)
                        if started:
                            st.success(f"Started torrent download from local .torrent into: {default_torrent_dir}. Check the Terminal Output section for live logs.")
        # Torrent control buttons: pause/resume/stop
        col_t_pause, col_t_resume, col_t_stop = st.columns(3)
        with col_t_pause:
            if st.button("⏸️ Pause Torrent Activity", key="pause_torrent_downloads"):
                try:
                    import subprocess as _sp
                    _sp.run(["pkill", "-STOP", "aria2c"], check=False)
                    _sp.run(["pkill", "-STOP", "webtorrent"], check=False)
                    st.session_state['torrent_paused'] = True
                    st.info("Requested pause of aria2c/webtorrent torrent activity.")
                except Exception:
                    st.warning("Attempted to pause torrents, but an error occurred.")
        with col_t_resume:
            if st.button("▶️ Resume Torrent Activity", key="resume_torrent_downloads"):
                try:
                    import subprocess as _sp
                    _sp.run(["pkill", "-CONT", "aria2c"], check=False)
                    _sp.run(["pkill", "-CONT", "webtorrent"], check=False)
                    st.session_state['torrent_paused'] = False
                    st.info("Requested resume of aria2c/webtorrent torrent activity.")
                except Exception:
                    st.warning("Attempted to resume torrents, but an error occurred.")
        with col_t_stop:
            # Dedicated control to stop any running torrent downloads/streams
            if st.button("⏹️ Stop Torrent Downloads", key="stop_torrent_downloads"):
                # Signal stop to any shell-based downloads
                st.session_state['stop_downloads'] = True
                try:
                    import subprocess as _sp, time as _t
                    _sp.run(["pkill", "-TERM", "aria2c"], check=False)
                    _t.sleep(0.2)
                    _sp.run(["pkill", "-KILL", "aria2c"], check=False)
                    _sp.run(["pkill", "-TERM", "webtorrent"], check=False)
                    _t.sleep(0.2)
                    _sp.run(["pkill", "-KILL", "webtorrent"], check=False)
                except Exception:
                    pass
                st.info("Requested termination of aria2c/webtorrent torrent activity. Check the Terminal Output for confirmation.")

        # Stop torrents and delete all torrent data for the configured folder
        if st.button("🧹 Stop & Delete Torrent Data", key="stop_delete_torrent_data"):
            st.session_state['stop_downloads'] = True
            # First, stop any running torrent processes
            try:
                import subprocess as _sp, time as _t
                _sp.run(["pkill", "-TERM", "aria2c"], check=False)
                _t.sleep(0.2)
                _sp.run(["pkill", "-KILL", "aria2c"], check=False)
                _sp.run(["pkill", "-TERM", "webtorrent"], check=False)
                _t.sleep(0.2)
                _sp.run(["pkill", "-KILL", "webtorrent"], check=False)
            except Exception:
                pass
            # Then remove all files under the torrent folder (but keep the folder itself)
            if os.path.isdir(default_torrent_dir):
                try:
                    shutil.rmtree(default_torrent_dir)
                    os.makedirs(default_torrent_dir, exist_ok=True)
                    st.success(f"Stopped torrents and removed all torrent data under: {default_torrent_dir}")
                except Exception as e:
                    st.error(f"Stopped torrents but failed to fully delete torrent data: {e}")
        # Stream completed torrent files in VLC (from disk)
        if st.button("🎬 Stream Torrent Videos in VLC", key="stream_torrent_vlc"):
            if not os.path.isdir(default_torrent_dir):
                st.warning("No torrent download directory found yet. Start a torrent download first.")
            else:
                # Collect all video files under the torrent folder (recursive search)
                video_paths = []
                try:
                    for root, dirs, files_in_dir in os.walk(default_torrent_dir):
                        for entry in files_in_dir:
                            if entry.lower().endswith(VIDEO_EXTENSIONS):
                                full = os.path.join(root, entry)
                                if os.path.isfile(full):
                                    video_paths.append(full)
                except Exception:
                    video_paths = []
                if not video_paths:
                    st.warning("No video files found in the torrent download folder yet.")
                else:
                    names = [os.path.relpath(p, default_torrent_dir) for p in video_paths]
                    urls = [Path(os.path.abspath(p)).as_uri() for p in video_paths]
                    try:
                        stream_all_in_vlc(urls, names)
                        st.success(f"Launched VLC with {len(urls)} torrent video file(s) from {default_torrent_dir}.")
                        st.info("Check your system for the VLC media player window.")
                    except Exception as e:
                        st.error(f"Failed to launch VLC for torrent videos: {e}")
        # Stream torrent directly in VLC without keeping full local files
        if st.button("🎬 Stream Torrent in VLC (no local file)", key="stream_torrent_direct_vlc"):
            # Prefer explicit torrent URL if provided; otherwise fall back to uploaded .torrent
            torrent_ref = None
            if torrent_url and is_torrent_link(torrent_url):
                torrent_ref = torrent_url.strip()
            elif uploaded_torrent:
                # Save the uploaded .torrent if not already saved, then use its path
                os.makedirs(default_torrent_dir, exist_ok=True)
                local_torrent_path = os.path.join(default_torrent_dir, uploaded_torrent.name)
                try:
                    with open(local_torrent_path, "wb") as f:
                        f.write(uploaded_torrent.getbuffer())
                    torrent_ref = local_torrent_path
                except Exception as e:
                    st.error(f"Failed to save uploaded .torrent file for streaming: {e}")
            if not torrent_ref:
                st.warning("Provide a magnet/.torrent URL or upload a .torrent file to stream.")
            else:
                started = stream_torrent_via_webtorrent(torrent_ref)
                if started:
                    st.info("Started torrent streaming via webtorrent; VLC should open automatically if installed.")
    
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
                # Keep the multiselect widget in sync so `selected` is populated
                st.session_state['file_selector'] = st.session_state['selected_files']
                st.rerun()
        with col_deselect:
            if st.button("Deselect All", key="deselect_all_files"):
                st.session_state['selected_files'] = []
                # Clear the multiselect widget state as well
                st.session_state['file_selector'] = []
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
                    # Reset stop flag before starting
                    st.session_state['stop_downloads'] = False
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
                    # Signal stop to shell processes
                    st.session_state['stop_downloads'] = True
                    # Primary stop mechanism: kill all wget/aria2c downloads immediately
                    try:
                        import subprocess as _sp, time as _t
                        _sp.run(["pkill", "-TERM", "-f", "wget --progress=bar:force"], check=False)
                        _t.sleep(0.2)
                        _sp.run(["pkill", "-KILL", "-f", "wget --progress=bar:force"], check=False)
                        _sp.run(["pkill", "-TERM", "aria2c"], check=False)
                        _t.sleep(0.2)
                        _sp.run(["pkill", "-KILL", "aria2c"], check=False)
                    except Exception:
                        pass
                    # Cleanup any tracked processes
                    try:
                        st.session_state['active_download_processes'] = []
                    except Exception:
                        pass
                    # Mark in-progress items as stopped in status dict
                    try:
                        file_status = st.session_state.get('file_status', {})
                        for name, info in list(file_status.items()):
                            if info.get('status') in ['downloading', 'paused']:
                                file_status[name] = {'status': 'stopped', 'progress': info.get('progress', 0)}
                        st.session_state['file_status'] = file_status
                    except Exception:
                        pass
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