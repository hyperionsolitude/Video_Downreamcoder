"""
Video encoding: script creation, listing, trimming, intro/outro detection, and FFmpeg encode.
"""
import os
import json
import shutil
import subprocess

import numpy as np
import streamlit as st
import librosa
from scipy.spatial.distance import cosine

from .config import VIDEO_EXTENSIONS
from .shell_utils import TerminalOutput, run_shell_command, run_shell_command_with_output
from .platform_utils import PLATFORM_CONFIG
from .prerequisites import detect_hardware_acceleration

# --- VIDEO ENCODING FUNCTIONS ---
def create_video_encoder_script(download_dir):
    """Create the video encoder script in the download directory"""
    script_path = os.path.join(download_dir, "video_encoder.sh")
    
    if not os.path.exists(script_path):
        # Copy the original script
        original_script = os.path.join(os.path.dirname(__file__), "..", "original", "video_encoder.sh")
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
