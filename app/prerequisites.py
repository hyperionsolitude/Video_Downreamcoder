"""Install prerequisites and detect hardware acceleration."""

from typing import Dict

import streamlit as st

from .platform_utils import PLATFORM_CONFIG
from .shell_utils import (
    TerminalOutput,
    check_command_exists,
    run_shell_command,
    run_shell_command_with_output,
)
from .sudo_utils import run_sudo_command_with_password


def install_prerequisites():
    """Install required packages using cross-platform package managers."""
    if "terminal_output" not in st.session_state:
        st.session_state.terminal_output = TerminalOutput()

    terminal = st.session_state.terminal_output
    terminal.add_line(
        f"Starting prerequisites installation on {PLATFORM_CONFIG['os']}...", "info"
    )
    st.info(f"Installing prerequisites for {PLATFORM_CONFIG['os']}...")

    if PLATFORM_CONFIG["is_macos"]:
        return install_prerequisites_macos(terminal)
    elif PLATFORM_CONFIG["is_linux"]:
        return install_prerequisites_linux(terminal)
    elif PLATFORM_CONFIG["is_windows"]:
        return install_prerequisites_windows(terminal)
    else:
        st.error(f"❌ Unsupported operating system: {PLATFORM_CONFIG['os']}")
        terminal.add_line(f"Unsupported OS: {PLATFORM_CONFIG['os']}", "error")
        return False


def install_prerequisites_macos(terminal):
    """Install prerequisites on macOS using Homebrew."""
    st.info("🍎 Installing prerequisites on macOS...")
    if not PLATFORM_CONFIG.get("homebrew_installed", False):
        st.warning("⚠️ Homebrew not found. Installing Homebrew first...")
        terminal.add_line("Installing Homebrew...", "info")
        install_cmd = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        result = run_shell_command_with_output(install_cmd, timeout=300)
        if not result["success"]:
            st.error("❌ Failed to install Homebrew. Please install it manually from https://brew.sh")
            terminal.add_line("Failed to install Homebrew", "error")
            return False
        st.success("✅ Homebrew installed!")
        terminal.add_line("Homebrew installed successfully", "info")

    packages = ["ffmpeg", "wget", "curl", "aria2", "node"]
    st.info("🔧 Installing system packages via Homebrew...")
    for package in packages:
        st.info(f"Installing {package}...")
        result = run_shell_command_with_output(f"brew install {package}", timeout=120)
        if not result["success"]:
            st.warning(f"Failed to install {package}")
            terminal.add_line(f"Failed to install {package}", "error")
        else:
            st.success(f"✅ {package} installed!")
            terminal.add_line(f"Successfully installed {package}", "info")

    st.info("🎥 Installing yt-dlp...")
    result = run_shell_command_with_output("python3 -m pip install --user yt-dlp", timeout=120)
    if not result["success"]:
        result = run_shell_command_with_output("pip3 install --user yt-dlp", timeout=120)
    if not result["success"]:
        result = run_shell_command_with_output("pip install --user yt-dlp", timeout=120)
    if not result["success"]:
        st.warning("Failed to install yt-dlp. Try manually: python3 -m pip install --user yt-dlp")
        terminal.add_line("Failed to install yt-dlp", "error")
    else:
        st.success("✅ yt-dlp installed!")
        terminal.add_line("yt-dlp installed successfully", "info")

    st.info("🌐 Installing webtorrent-cli (for direct torrent streaming)...")
    if not check_command_exists("npm"):
        st.warning("npm not found. Node should have been installed with system packages. Install manually if needed.")
        terminal.add_line("npm not found; skipping webtorrent-cli", "error")
    else:
        result = run_shell_command_with_output("npm install -g webtorrent-cli", timeout=300)
        if not result["success"]:
            st.warning("Failed to install webtorrent-cli. Try manually: npm install -g webtorrent-cli")
            terminal.add_line("Failed to install webtorrent-cli", "error")
        else:
            st.success("✅ webtorrent-cli installed!")
            terminal.add_line("webtorrent-cli installed successfully", "info")

    terminal.add_line("macOS prerequisites installation completed!", "info")
    st.success("🎉 Prerequisites installation completed!")
    return True


def install_prerequisites_linux(terminal):
    """Install prerequisites on Linux using appropriate package manager."""
    st.info("🐧 Installing prerequisites on Linux...")
    sudo_check = run_shell_command("sudo -n true", timeout=5)
    needs_password = not sudo_check["success"]
    password = st.session_state.get("sudo_password", None)
    if needs_password and not password:
        st.error("❌ No password provided for sudo commands.")
        return False
    if needs_password and password:
        st.info("🔍 Verifying password...")
        test_result = run_sudo_command_with_password("true", password, timeout=10)
        if not test_result["success"]:
            st.error("❌ Invalid password. Please try again.")
            terminal.add_line("Invalid sudo password provided", "error")
            return False
        st.success("✅ Password verified!")
        terminal.add_line("Sudo password verified successfully", "info")

    if PLATFORM_CONFIG["package_manager"] == "apt":
        return install_prerequisites_apt(terminal, needs_password, password)
    elif PLATFORM_CONFIG["package_manager"] == "dnf":
        return install_prerequisites_dnf(terminal, needs_password, password)
    elif PLATFORM_CONFIG["package_manager"] == "pacman":
        return install_prerequisites_pacman(terminal, needs_password, password)
    else:
        st.error(f"❌ Unsupported package manager: {PLATFORM_CONFIG['package_manager']}")
        terminal.add_line(f"Unsupported package manager: {PLATFORM_CONFIG['package_manager']}", "error")
        return False


def install_prerequisites_apt(terminal, needs_password, password):
    """Install prerequisites using apt (Ubuntu/Debian)."""
    st.info("📦 Updating package list...")
    if needs_password:
        result = run_sudo_command_with_password("apt update", password, timeout=60)
    else:
        result = run_shell_command_with_output("sudo apt update", timeout=60)
    if not result["success"]:
        st.error("❌ Failed to update package list.")
        terminal.add_line("Failed to update package list", "error")
        return False
    st.success("✅ Package list updated!")

    packages = PLATFORM_CONFIG["system_packages"]
    st.info("🔧 Installing system packages...")
    all_packages = " ".join(packages)
    if needs_password:
        result = run_sudo_command_with_password(f"apt install -y {all_packages}", password, timeout=300)
    else:
        result = run_shell_command_with_output(f"sudo apt install -y {all_packages}", timeout=300)
    if not result["success"]:
        st.warning("⚠️ Some system packages may have failed to install. Trying individual packages...")
        terminal.add_line("Trying individual package installation...", "info")
        for package in packages:
            st.info(f"Installing {package}...")
            if needs_password:
                result = run_sudo_command_with_password(f"apt install -y {package}", password, timeout=60)
            else:
                result = run_shell_command_with_output(f"sudo apt install -y {package}", timeout=60)
            if not result["success"]:
                st.warning(f"Failed to install {package}")
                terminal.add_line(f"Failed to install {package}", "error")
            else:
                st.success(f"✅ {package} installed!")
    else:
        st.success("✅ All system packages installed!")

    st.info("🎥 Installing yt-dlp...")
    result = run_shell_command_with_output("python3 -m pip install --user yt-dlp", timeout=120)
    if not result["success"]:
        result = run_shell_command_with_output("pip3 install --user yt-dlp", timeout=120)
    if not result["success"]:
        result = run_shell_command_with_output("pip install --user yt-dlp", timeout=120)
    if not result["success"]:
        st.warning("Failed to install yt-dlp via pip. Try manually: python3 -m pip install --user yt-dlp")
        terminal.add_line("Failed to install yt-dlp", "error")
    else:
        st.success("✅ yt-dlp installed!")
        terminal.add_line("yt-dlp installed successfully", "info")

    st.info("🌐 Installing webtorrent-cli (for direct torrent streaming)...")
    if not check_command_exists("npm"):
        st.warning("npm not found. Node.js/npm should have been installed with system packages above. Install manually if needed.")
        terminal.add_line("npm not found; skipping webtorrent-cli", "error")
    else:
        if needs_password and password:
            result = run_sudo_command_with_password("npm install -g webtorrent-cli", password, timeout=300)
        else:
            result = run_shell_command_with_output("sudo npm install -g webtorrent-cli", timeout=300)
        if not result["success"]:
            st.warning("Failed to install webtorrent-cli via npm. Try manually: sudo npm install -g webtorrent-cli")
            terminal.add_line("Failed to install webtorrent-cli", "error")
        else:
            st.success("✅ webtorrent-cli installed!")
            terminal.add_line("webtorrent-cli installed successfully", "info")

    terminal.add_line("Linux prerequisites installation completed!", "info")
    st.success("🎉 Prerequisites installation completed!")
    return True


def install_prerequisites_dnf(terminal, needs_password, password):
    """Install prerequisites using dnf (Fedora/RHEL/CentOS)."""
    st.info("📦 Updating package list...")
    if needs_password:
        result = run_sudo_command_with_password("dnf update -y", password, timeout=60)
    else:
        result = run_shell_command_with_output("sudo dnf update -y", timeout=60)
    if not result["success"]:
        st.warning("⚠️ Package list update failed, continuing...")

    packages = PLATFORM_CONFIG["system_packages"]
    st.info("🔧 Installing system packages...")
    all_packages = " ".join(packages)
    if needs_password:
        result = run_sudo_command_with_password(f"dnf install -y {all_packages}", password, timeout=300)
    else:
        result = run_shell_command_with_output(f"sudo dnf install -y {all_packages}", timeout=300)
    if not result["success"]:
        st.warning("⚠️ Some system packages may have failed to install. Trying individual packages...")
        for package in packages:
            st.info(f"Installing {package}...")
            if needs_password:
                result = run_sudo_command_with_password(f"dnf install -y {package}", password, timeout=60)
            else:
                result = run_shell_command_with_output(f"sudo dnf install -y {package}", timeout=60)
            if not result["success"]:
                st.warning(f"Failed to install {package}")
            else:
                st.success(f"✅ {package} installed!")
    else:
        st.success("✅ All system packages installed!")

    st.info("🎥 Installing yt-dlp...")
    result = run_shell_command_with_output("python3 -m pip install --user yt-dlp", timeout=120)
    if not result["success"]:
        result = run_shell_command_with_output("pip3 install --user yt-dlp", timeout=120)
    if not result["success"]:
        st.warning("Failed to install yt-dlp via pip. Try manually: python3 -m pip install --user yt-dlp")
        terminal.add_line("Failed to install yt-dlp", "error")
    else:
        st.success("✅ yt-dlp installed!")
        terminal.add_line("yt-dlp installed successfully", "info")

    st.info("🌐 Installing webtorrent-cli (for direct torrent streaming)...")
    if not check_command_exists("npm"):
        st.warning("npm not found. Install Node.js/npm with system packages above or manually.")
        terminal.add_line("npm not found; skipping webtorrent-cli", "error")
    else:
        if needs_password and password:
            result = run_sudo_command_with_password("npm install -g webtorrent-cli", password, timeout=300)
        else:
            result = run_shell_command_with_output("sudo npm install -g webtorrent-cli", timeout=300)
        if not result["success"]:
            st.warning("Failed to install webtorrent-cli. Try manually: sudo npm install -g webtorrent-cli")
            terminal.add_line("Failed to install webtorrent-cli", "error")
        else:
            st.success("✅ webtorrent-cli installed!")
            terminal.add_line("webtorrent-cli installed successfully", "info")

    terminal.add_line("Linux prerequisites installation completed!", "info")
    st.success("🎉 Prerequisites installation completed!")
    return True


def install_prerequisites_pacman(terminal, needs_password, password):
    """Install prerequisites using pacman (Arch Linux)."""
    st.info("📦 Updating package list...")
    if needs_password:
        result = run_sudo_command_with_password("pacman -Sy", password, timeout=60)
    else:
        result = run_shell_command_with_output("sudo pacman -Sy", timeout=60)
    if not result["success"]:
        st.warning("⚠️ Package list update failed, continuing...")

    packages = PLATFORM_CONFIG["system_packages"]
    st.info("🔧 Installing system packages...")
    all_packages = " ".join(packages)
    if needs_password:
        result = run_sudo_command_with_password(f"pacman -S --noconfirm {all_packages}", password, timeout=300)
    else:
        result = run_shell_command_with_output(f"sudo pacman -S --noconfirm {all_packages}", timeout=300)
    if not result["success"]:
        st.warning("⚠️ Some system packages may have failed to install. Trying individual packages...")
        for package in packages:
            st.info(f"Installing {package}...")
            if needs_password:
                result = run_sudo_command_with_password(f"pacman -S --noconfirm {package}", password, timeout=60)
            else:
                result = run_shell_command_with_output(f"sudo pacman -S --noconfirm {package}", timeout=60)
            if not result["success"]:
                st.warning(f"Failed to install {package}")
            else:
                st.success(f"✅ {package} installed!")
    else:
        st.success("✅ All system packages installed!")

    st.info("🎥 Installing yt-dlp...")
    result = run_shell_command_with_output("python3 -m pip install --user yt-dlp", timeout=120)
    if not result["success"]:
        result = run_shell_command_with_output("pip install --user yt-dlp", timeout=120)
    if not result["success"]:
        st.warning("Failed to install yt-dlp. Try manually: python3 -m pip install --user yt-dlp")
        terminal.add_line("Failed to install yt-dlp", "error")
    else:
        st.success("✅ yt-dlp installed!")
        terminal.add_line("yt-dlp installed successfully", "info")

    st.info("🌐 Installing webtorrent-cli (for direct torrent streaming)...")
    if not check_command_exists("npm"):
        st.warning("npm not found. Install Node.js/npm with system packages above or manually.")
        terminal.add_line("npm not found; skipping webtorrent-cli", "error")
    else:
        if needs_password and password:
            result = run_sudo_command_with_password("npm install -g webtorrent-cli", password, timeout=300)
        else:
            result = run_shell_command_with_output("sudo npm install -g webtorrent-cli", timeout=300)
        if not result["success"]:
            st.warning("Failed to install webtorrent-cli. Try manually: sudo npm install -g webtorrent-cli")
            terminal.add_line("Failed to install webtorrent-cli", "error")
        else:
            st.success("✅ webtorrent-cli installed!")
            terminal.add_line("webtorrent-cli installed successfully", "info")

    terminal.add_line("Linux prerequisites installation completed!", "info")
    st.success("🎉 Prerequisites installation completed!")
    return True


def install_prerequisites_windows(terminal):
    """Install prerequisites on Windows using Chocolatey."""
    st.info("🪟 Installing prerequisites on Windows...")
    choco_check = run_shell_command("choco --version", timeout=5)
    if not choco_check["success"]:
        st.warning("⚠️ Chocolatey not found. Please install it from https://chocolatey.org/install")
        terminal.add_line("Chocolatey not found", "error")
        return False

    packages = PLATFORM_CONFIG["system_packages"]
    st.info("🔧 Installing system packages via Chocolatey...")
    for package in packages:
        st.info(f"Installing {package}...")
        result = run_shell_command_with_output(f"choco install -y {package}", timeout=120)
        if not result["success"]:
            st.warning(f"Failed to install {package}")
            terminal.add_line(f"Failed to install {package}", "error")
        else:
            st.success(f"✅ {package} installed!")
            terminal.add_line(f"Successfully installed {package}", "info")

    st.info("🎥 Installing yt-dlp...")
    result = run_shell_command_with_output("python -m pip install --user yt-dlp", timeout=120)
    if not result["success"]:
        result = run_shell_command_with_output("pip install --user yt-dlp", timeout=120)
    if not result["success"]:
        st.warning("Failed to install yt-dlp. Try manually: pip install --user yt-dlp")
        terminal.add_line("Failed to install yt-dlp", "error")
    else:
        st.success("✅ yt-dlp installed!")
        terminal.add_line("yt-dlp installed successfully", "info")

    st.info("🌐 Installing webtorrent-cli (for direct torrent streaming)...")
    if not check_command_exists("npm"):
        st.warning("npm not found. Node.js should have been installed with Chocolatey. Install manually if needed.")
        terminal.add_line("npm not found; skipping webtorrent-cli", "error")
    else:
        result = run_shell_command_with_output("npm install -g webtorrent-cli", timeout=300)
        if not result["success"]:
            st.warning("Failed to install webtorrent-cli. Try manually: npm install -g webtorrent-cli")
            terminal.add_line("Failed to install webtorrent-cli", "error")
        else:
            st.success("✅ webtorrent-cli installed!")
            terminal.add_line("webtorrent-cli installed successfully", "info")

    terminal.add_line("Windows prerequisites installation completed!", "info")
    st.success("🎉 Prerequisites installation completed!")
    return True


def install_torrent_options(terminal):
    """Install only Node.js (if missing) and webtorrent-cli for torrent streaming."""
    if "terminal_output" not in st.session_state:
        st.session_state.terminal_output = terminal
    st.info("🌐 Installing torrent options (Node.js + webtorrent-cli)...")
    terminal.add_line("Installing torrent options (Node.js + webtorrent-cli)...", "info")

    if not check_command_exists("npm"):
        if PLATFORM_CONFIG["is_macos"]:
            result = run_shell_command_with_output("brew install node", timeout=120)
        elif PLATFORM_CONFIG["is_linux"]:
            pm = PLATFORM_CONFIG.get("package_manager")
            if pm == "apt":
                result = run_shell_command_with_output("sudo apt update && sudo apt install -y nodejs npm", timeout=120)
            elif pm == "dnf":
                result = run_shell_command_with_output("sudo dnf install -y nodejs npm", timeout=120)
            elif pm == "pacman":
                result = run_shell_command_with_output("sudo pacman -S --noconfirm nodejs npm", timeout=120)
            else:
                result = {"success": False}
        elif PLATFORM_CONFIG["is_windows"]:
            result = run_shell_command_with_output("choco install -y nodejs", timeout=120)
        else:
            result = {"success": False}
        if not result.get("success"):
            st.warning("Could not install Node.js automatically. Use **Install Prerequisites** (may require password) or install Node from https://nodejs.org")
            terminal.add_line("Node.js installation failed", "error")
            return False
        st.success("✅ Node.js installed")
        terminal.add_line("Node.js installed", "info")
    else:
        terminal.add_line("Node.js/npm already available", "info")

    if PLATFORM_CONFIG["is_linux"]:
        result = run_shell_command_with_output("sudo npm install -g webtorrent-cli", timeout=300)
    else:
        result = run_shell_command_with_output("npm install -g webtorrent-cli", timeout=300)
    if not result.get("success"):
        st.warning("Failed to install webtorrent-cli. Try: npm install -g webtorrent-cli")
        terminal.add_line("Failed to install webtorrent-cli", "error")
        return False
    st.success("✅ webtorrent-cli installed! You can stream torrents now.")
    terminal.add_line("webtorrent-cli installed successfully", "info")
    return True


def detect_hardware_acceleration() -> Dict[str, bool]:
    """Detect available hardware acceleration using shell commands."""
    acceleration = {
        "nvenc": False,
        "qsv": False,
        "vaapi": False,
        "videotoolbox": False,
        "cpu": True,
    }
    hwaccel_result = run_shell_command("ffmpeg -hide_banner -hwaccels 2>/dev/null")
    if hwaccel_result["success"]:
        hwaccels = hwaccel_result["stdout"]
        if "videotoolbox" in hwaccels and PLATFORM_CONFIG["is_macos"]:
            acceleration["videotoolbox"] = True

    result = run_shell_command("ffmpeg -hide_banner -encoders 2>/dev/null")
    if result["success"]:
        encoders = result["stdout"]
        acceleration["nvenc"] = "h264_nvenc" in encoders or "hevc_nvenc" in encoders
        acceleration["qsv"] = "h264_qsv" in encoders or "hevc_qsv" in encoders
        acceleration["vaapi"] = "h264_vaapi" in encoders or "hevc_vaapi" in encoders
        if PLATFORM_CONFIG["is_macos"]:
            acceleration["videotoolbox"] = acceleration["videotoolbox"] and (
                "h264_videotoolbox" in encoders or "hevc_videotoolbox" in encoders
            )

    if acceleration["nvenc"]:
        test_result = run_shell_command("ffmpeg -f lavfi -i testsrc=duration=1:size=320x240:rate=1 -c:v h264_nvenc -f null - 2>&1")
        if not test_result["success"] or "No capable devices found" in test_result["stderr"]:
            acceleration["nvenc"] = False

    if acceleration["videotoolbox"] and PLATFORM_CONFIG["is_macos"]:
        test_result = run_shell_command("ffmpeg -f lavfi -i testsrc=duration=1:size=320x240:rate=1 -c:v h264_videotoolbox -q:v 20 -f null - 2>&1")
        if not test_result["success"] or "No capable devices found" in test_result["stderr"]:
            acceleration["videotoolbox"] = False

    return acceleration
