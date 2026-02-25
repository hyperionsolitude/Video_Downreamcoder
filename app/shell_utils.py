import os
import subprocess
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

import streamlit as st


class TerminalOutput:
    def __init__(self) -> None:
        self.output_queue: "queue.Queue[str]" = __import__("queue").Queue()
        self.max_lines = 100
        self.command_count = 0

    def add_line(self, text: str, cmd_type: str = "info") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        if cmd_type == "command":
            self.command_count += 1
            formatted_text = (
                f"<span style='color: #00ff00; font-weight: bold;'>[{timestamp}] $ {text}</span>"
            )
        elif cmd_type == "error":
            formatted_text = (
                f"<span style='color: #ff4444; font-weight: bold;'>[{timestamp}] ❌ {text}</span>"
            )
        elif cmd_type == "warning":
            formatted_text = (
                f"<span style='color: #ffaa00; font-weight: bold;'>[{timestamp}] ⚠️ {text}</span>"
            )
        elif cmd_type == "success":
            formatted_text = (
                f"<span style='color: #00ff88; font-weight: bold;'>[{timestamp}] ✅ {text}</span>"
            )
        elif cmd_type == "info":
            formatted_text = f"<span style='color: #00aaff;'>[{timestamp}] ℹ️ {text}</span>"
        else:
            formatted_text = f"<span style='color: #ffffff;'>[{timestamp}] {text}</span>"

        self.output_queue.put(formatted_text)

    def get_output(self) -> List[str]:
        lines: List[str] = []
        while not self.output_queue.empty() and len(lines) < self.max_lines:
            try:
                lines.append(self.output_queue.get_nowait())
            except __import__("queue").Empty:
                break
        return lines[-self.max_lines :]

    def clear(self) -> None:
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except __import__("queue").Empty:
                break


def ensure_terminal() -> TerminalOutput:
    if "terminal_output" not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()
    return st.session_state.terminal_output


def run_shell_command_with_output(
    cmd: str,
    cwd: Optional[str] = None,
    timeout: int = 300,
    show_in_terminal: bool = True,
) -> Dict[str, Any]:
    if "terminal_output" not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()
    if "active_download_processes" not in st.session_state:
        st.session_state.active_download_processes = []
    if "stop_downloads" not in st.session_state:
        st.session_state["stop_downloads"] = False

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
            universal_newlines=True,
            start_new_session=True,
        )
        try:
            st.session_state.active_download_processes.append(process)
        except Exception:
            pass

        stdout_lines: List[str] = []

        while True:
            if st.session_state.get("stop_downloads"):
                try:
                    import signal as _signal, os as _os

                    try:
                        _os.killpg(process.pid, _signal.SIGTERM)
                    except Exception:
                        process.terminate()
                except Exception:
                    pass
                break
            output = process.stdout.readline()
            if output == "" and process.poll() is not None:
                break
            if output:
                line = output.strip()
                stdout_lines.append(line)
                if show_in_terminal:
                    terminal.add_line(line, "output")

        try:
            process.wait(timeout=timeout)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

        try:
            st.session_state.active_download_processes = [
                p for p in st.session_state.active_download_processes if p is not process
            ]
        except Exception:
            pass

        return {
            "success": process.returncode == 0,
            "stdout": "\n".join(stdout_lines),
            "stderr": "",
            "returncode": process.returncode,
        }

    except subprocess.TimeoutExpired:
        if show_in_terminal:
            terminal.add_line("Command timed out", "error")
        return {
            "success": False,
            "stdout": "",
            "stderr": "Command timed out",
            "returncode": -1,
        }
    except Exception as e:
        if show_in_terminal:
            terminal.add_line(f"Error: {str(e)}", "error")
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


def run_shell_command(
    cmd: str,
    cwd: Optional[str] = None,
    timeout: int = 300,
    interactive: bool = False,
) -> Dict[str, Any]:
    if interactive:
        return run_shell_command_with_output(cmd, cwd, timeout, show_in_terminal=True)
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Command timed out",
            "returncode": -1,
        }
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


def check_command_exists(command: str) -> bool:
    result = run_shell_command(f"which {command}")
    return result["success"]


