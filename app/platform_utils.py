import os
import platform
import subprocess
from typing import Any, Dict

import distro  # type: ignore


def detect_platform() -> Dict[str, Any]:
    """Detect the current platform and return platform-specific configurations."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    config: Dict[str, Any] = {
        "os": system,
        "arch": machine,
        "is_macos": system == "darwin",
        "is_linux": system == "linux",
        "is_windows": system == "windows",
        "is_arm": "arm" in machine or "aarch64" in machine,
        "is_apple_silicon": system == "darwin" and ("arm" in machine or "aarch64" in machine),
        "package_manager": None,
        "ffmpeg_install_cmd": None,
        "system_packages": [],
        "hardware_acceleration": [],
    }

    if config["is_macos"]:
        config["package_manager"] = "homebrew"
        config["ffmpeg_install_cmd"] = "brew install ffmpeg"
        config["system_packages"] = ["ffmpeg", "wget", "curl", "aria2", "node"]
        config["hardware_acceleration"] = ["videotoolbox", "metal"]

        try:
            subprocess.run(["brew", "--version"], capture_output=True, check=True)
            config["homebrew_installed"] = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            config["homebrew_installed"] = False

    elif config["is_linux"]:
        try:
            distro_info = distro.linux_distribution(full_distribution_name=False)
            distro_name = distro_info[0].lower()

            if "ubuntu" in distro_name or "debian" in distro_name:
                config["package_manager"] = "apt"
                config["ffmpeg_install_cmd"] = "sudo apt install ffmpeg"
                config["system_packages"] = [
                    "ffmpeg",
                    "wget",
                    "curl",
                    "aria2",
                    "nodejs",
                    "npm",
                    "python3-pip",
                    "python3-venv",
                    "python3-dev",
                    "libffi-dev",
                    "libssl-dev",
                ]
            elif "fedora" in distro_name or "rhel" in distro_name or "centos" in distro_name:
                config["package_manager"] = "dnf"
                config["ffmpeg_install_cmd"] = "sudo dnf install ffmpeg"
                config["system_packages"] = [
                    "ffmpeg",
                    "wget",
                    "curl",
                    "aria2",
                    "nodejs",
                    "npm",
                    "python3-pip",
                    "python3-venv",
                    "python3-devel",
                    "libffi-devel",
                    "openssl-devel",
                ]
            elif "arch" in distro_name:
                config["package_manager"] = "pacman"
                config["ffmpeg_install_cmd"] = "sudo pacman -S ffmpeg"
                config["system_packages"] = [
                    "ffmpeg",
                    "wget",
                    "curl",
                    "aria2",
                    "nodejs",
                    "npm",
                    "python-pip",
                    "python-virtualenv",
                ]
            else:
                config["package_manager"] = "unknown"
                config["ffmpeg_install_cmd"] = "Please install ffmpeg manually"
                config["system_packages"] = ["ffmpeg", "wget", "curl", "aria2", "nodejs", "npm"]
        except Exception:
            config["package_manager"] = "unknown"
            config["ffmpeg_install_cmd"] = "Please install ffmpeg manually"
            config["system_packages"] = ["ffmpeg", "wget", "curl", "aria2", "nodejs", "npm"]

        config["hardware_acceleration"] = ["nvenc", "qsv", "vaapi"]

    elif config["is_windows"]:
        config["package_manager"] = "chocolatey"
        config["ffmpeg_install_cmd"] = "choco install ffmpeg"
        config["system_packages"] = ["ffmpeg", "wget", "curl", "aria2", "nodejs"]
        config["hardware_acceleration"] = ["nvenc", "qsv"]

    return config


PLATFORM_CONFIG = detect_platform()

