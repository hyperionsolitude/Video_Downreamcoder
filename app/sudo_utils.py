"""Run sudo commands with password (for install prerequisites)."""

import subprocess

import streamlit as st

from .shell_utils import TerminalOutput


def run_sudo_command_with_password(cmd, password, timeout=300):
    """Run sudo command with password provided via stdin."""
    if "terminal_output" not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()

    terminal = st.session_state.terminal_output
    terminal.add_line(f"$ echo '[password]' | sudo -S {cmd}", "command")

    try:
        full_cmd = f"echo '{password}' | sudo -S {cmd}"
        process = subprocess.Popen(
            full_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        stdout_lines = []
        while True:
            output = process.stdout.readline()
            if output == "" and process.poll() is not None:
                break
            if output:
                line = output.strip()
                if not any(
                    word in line.lower()
                    for word in ["password", "sorry", "authentication"]
                ):
                    stdout_lines.append(line)
                    terminal.add_line(line, "output")

        process.wait(timeout=timeout)
        return {
            "success": process.returncode == 0,
            "stdout": "\n".join(stdout_lines),
            "stderr": "",
            "returncode": process.returncode,
        }

    except subprocess.TimeoutExpired:
        terminal.add_line("Command timed out", "error")
        return {
            "success": False,
            "stdout": "",
            "stderr": "Command timed out",
            "returncode": -1,
        }
    except Exception as e:
        terminal.add_line(f"Error: {str(e)}", "error")
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
        }
