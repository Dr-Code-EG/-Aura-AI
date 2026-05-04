"""Compute a stable device fingerprint.

The fingerprint must:

* be deterministic across reboots / relaunches on the *same* machine
* be different on a different machine, even if the same Windows user
  account is restored from a backup
* not be trivially spoofable by editing a config file (we hash a
  combination of OS-level identifiers + a hardware property the user
  cannot change without buying new hardware)

Implementation details per platform:

Windows
    Reads ``MachineGuid`` out of
    ``HKLM\\SOFTWARE\\Microsoft\\Cryptography`` (a per-installation
    GUID), the primary MAC address from ``uuid.getnode()``, and the
    hostname.

Linux / macOS
    Falls back to ``/etc/machine-id`` (Linux) or
    ``IOPlatformUUID`` (macOS), plus MAC + hostname. We don't ship
    binaries for those platforms but the fallback keeps the unit
    tests runnable on the CI Linux runner.
"""

from __future__ import annotations

import hashlib
import platform
import socket
import sys
import uuid
from pathlib import Path


def _windows_machine_guid() -> str:
    try:
        import winreg  # type: ignore
    except ImportError:
        return ""
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except OSError:
        return ""


def _linux_machine_id() -> str:
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return ""


def _macos_platform_uuid() -> str:
    try:
        import subprocess
        out = subprocess.check_output(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        for line in out.decode(errors="ignore").splitlines():
            if "IOPlatformUUID" in line:
                return line.split("=")[-1].strip().strip('"')
    except Exception:
        pass
    return ""


def _primary_mac() -> str:
    return f"{uuid.getnode():012x}"


def device_fingerprint() -> str:
    """Return a hex SHA-256 of platform+hostname+machine-id+mac."""
    parts: list[str] = [
        sys.platform,
        platform.system(),
        socket.gethostname(),
        _primary_mac(),
    ]
    if sys.platform.startswith("win"):
        parts.append(_windows_machine_guid())
    elif sys.platform == "darwin":
        parts.append(_macos_platform_uuid())
    else:
        parts.append(_linux_machine_id())
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return h


def device_label() -> str:
    """Short human-readable label the admin can see in the dashboard."""
    return f"{platform.system()} / {socket.gethostname()}"
