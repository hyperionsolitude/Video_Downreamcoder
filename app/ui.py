import os
from pathlib import Path

import streamlit as st

from .platform_utils import PLATFORM_CONFIG
from .shell_utils import ensure_terminal
from .torrent import collect_torrent_video_files, is_torrent_link, start_torrent_download_with_aria2, stream_torrent_via_webtorrent


BASE_DOWNLOAD_DIR = os.path.expanduser("~/Downloads/StreamlitDownloads")
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm")


def get_base_download_dir() -> str:
    base = st.session_state.get("base_download_dir", BASE_DOWNLOAD_DIR)
    return os.path.expanduser(base)


def render_header() -> None:
    st.set_page_config(
        page_title="Streamlit Download Manager",
        layout="wide",
        initial_sidebar_state="expanded",
        page_icon="📥",
    )
    st.markdown(
        """
    <div class="main-header">
        <h1>📥 Streamlit Download Manager</h1>
        <p>Advanced video downloading with shell integration and real-time progress tracking</p>
    </div>
    """,
        unsafe_allow_html=True,
    )


def render_terminal() -> None:
    terminal = ensure_terminal()

    st.markdown("### 📺 Terminal Output")
    col_refresh, col_clear, col_auto = st.columns([1, 1, 2])

    with col_refresh:
        if st.button("🔄 Refresh Terminal", help="Refresh terminal output"):
            st.rerun()

    with col_clear:
        if st.button("🗑️ Clear Terminal", help="Clear terminal output"):
            terminal.clear()
            st.rerun()

    with col_auto:
        auto_refresh = st.checkbox(
            "🔄 Auto-refresh (2s)",
            value=True,
            help="Automatically refresh terminal every 2 seconds",
        )

    terminal_output = terminal.get_output()
    if terminal_output:
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

    if auto_refresh and terminal_output:
        import time

        if "last_terminal_refresh" not in st.session_state:
            st.session_state["last_terminal_refresh"] = time.time()

        current_time = time.time()
        if current_time - st.session_state["last_terminal_refresh"] > 2:
            st.session_state["last_terminal_refresh"] = current_time
            st.rerun()


def render_download_location() -> None:
    with st.expander("Download Location", expanded=False):
        cur_base = st.text_input(
            "Base download directory",
            value=str(st.session_state.get("base_download_dir", get_base_download_dir())),
        )
        col_bd1, col_bd2 = st.columns([1, 1])
        with col_bd1:
            if st.button("Use Default"):
                st.session_state["base_download_dir"] = BASE_DOWNLOAD_DIR
                st.success(f"Set base directory to {BASE_DOWNLOAD_DIR}")
        with col_bd2:
            if st.button("Save Location"):
                st.session_state["base_download_dir"] = os.path.expanduser(cur_base)
                os.makedirs(st.session_state["base_download_dir"], exist_ok=True)
                st.success(f"Base directory set to {st.session_state['base_download_dir']}")


def render_torrent_section() -> None:
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
            help="If provided, the uploaded .torrent file will be saved and used for downloading.",
        )

        base_dir = get_base_download_dir()
        default_torrent_dir = os.path.join(base_dir, torrent_folder)
        st.info(f"📂 Torrent files will be saved under: `{default_torrent_dir}`")

        if st.button("Start Torrent Download", key="start_torrent_download"):
            if not torrent_url:
                st.warning("Please enter a torrent or magnet link.")
            else:
                os.makedirs(default_torrent_dir, exist_ok=True)
                started = start_torrent_download_with_aria2(torrent_url, default_torrent_dir)
                if started:
                    st.success(
                        f"Started torrent download into: {default_torrent_dir}. "
                        "Check the Terminal Output section for live logs."
                    )

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
                    started = start_torrent_download_with_aria2(
                        local_torrent_path, default_torrent_dir
                    )
                    if started:
                        st.success(
                            "Started torrent download from local .torrent into: "
                            f"{default_torrent_dir}. Check the Terminal Output section for live logs."
                        )

        col_t_pause, col_t_resume, col_t_stop = st.columns(3)
        with col_t_pause:
            if st.button("⏸️ Pause Torrent Activity", key="pause_torrent_downloads"):
                try:
                    import subprocess as _sp

                    _sp.run(["pkill", "-STOP", "aria2c"], check=False)
                    _sp.run(["pkill", "-STOP", "webtorrent"], check=False)
                    st.session_state["torrent_paused"] = True
                    st.info("Requested pause of aria2c/webtorrent torrent activity.")
                except Exception:
                    st.warning("Attempted to pause torrents, but an error occurred.")
        with col_t_resume:
            if st.button("▶️ Resume Torrent Activity", key="resume_torrent_downloads"):
                try:
                    import subprocess as _sp

                    _sp.run(["pkill", "-CONT", "aria2c"], check=False)
                    _sp.run(["pkill", "-CONT", "webtorrent"], check=False)
                    st.session_state["torrent_paused"] = False
                    st.info("Requested resume of aria2c/webtorrent torrent activity.")
                except Exception:
                    st.warning("Attempted to resume torrents, but an error occurred.")
        with col_t_stop:
            if st.button("⏹️ Stop Torrent Downloads", key="stop_torrent_downloads"):
                st.session_state["stop_downloads"] = True
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
                st.info(
                    "Requested termination of aria2c/webtorrent torrent activity. "
                    "Check the Terminal Output for confirmation."
                )

        if st.button("🧹 Stop & Delete Torrent Data", key="stop_delete_torrent_data"):
            st.session_state["stop_downloads"] = True
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
            if os.path.isdir(default_torrent_dir):
                try:
                    import shutil

                    shutil.rmtree(default_torrent_dir)
                    os.makedirs(default_torrent_dir, exist_ok=True)
                    st.success(
                        f"Stopped torrents and removed all torrent data under: {default_torrent_dir}"
                    )
                except Exception as e:
                    st.error(f"Stopped torrents but failed to fully delete torrent data: {e}")

        if st.button("🎬 Stream Torrent Videos in VLC", key="stream_torrent_vlc"):
            if not os.path.isdir(default_torrent_dir):
                st.warning("No torrent download directory found yet. Start a torrent download first.")
            else:
                video_paths = collect_torrent_video_files(default_torrent_dir, VIDEO_EXTENSIONS)
                if not video_paths:
                    st.warning("No video files found in the torrent download folder yet.")
                else:
                    names = [os.path.relpath(p, default_torrent_dir) for p in video_paths]
                    urls = [Path(os.path.abspath(p)).as_uri() for p in video_paths]
                    from .streaming import stream_all_in_vlc  # lazy import to avoid cycles

                    try:
                        stream_all_in_vlc(urls, names)
                        st.success(
                            f"Launched VLC with {len(urls)} torrent video file(s) from {default_torrent_dir}."
                        )
                        st.info("Check your system for the VLC media player window.")
                    except Exception as e:
                        st.error(f"Failed to launch VLC for torrent videos: {e}")

        if st.button("🎬 Stream Torrent in VLC (no local file)", key="stream_torrent_direct_vlc"):
            torrent_ref = None
            if torrent_url and is_torrent_link(torrent_url):
                torrent_ref = torrent_url.strip()
            elif uploaded_torrent:
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
                    st.info(
                        "Started torrent streaming via webtorrent; VLC should open automatically "
                        "if installed."
                    )


def main() -> None:
    render_header()

    if "file_status" not in st.session_state:
        st.session_state["file_status"] = {}
    if "video_files" not in st.session_state:
        st.session_state["video_files"] = []
    if "selected_files" not in st.session_state:
        st.session_state["selected_files"] = []
    if "is_downloading" not in st.session_state:
        st.session_state["is_downloading"] = False
    if "base_download_dir" not in st.session_state:
        st.session_state["base_download_dir"] = BASE_DOWNLOAD_DIR

    render_download_location()
    render_torrent_section()
    render_terminal()

