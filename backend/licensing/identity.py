"""
Installation Identity & Hardware Fingerprinting for AVENTRA.
Generates deterministic, unique installation identity without inspecting customer operational data.
"""

import os
import platform
import uuid
import hashlib
from typing import Dict, Any
from pydantic import BaseModel, Field


class InstallationFingerprint(BaseModel):
    installation_id: str = Field(..., description="Deterministic hardware/installation identity token")
    hostname: str
    os_system: str
    machine_arch: str
    mac_node_hash: str
    is_containerized: bool


def detect_container_environment() -> bool:
    """Detects if running inside Docker, Kubernetes, or containerized runtime."""
    if os.path.exists("/.dockerenv") or os.getenv("KUBERNETES_SERVICE_HOST"):
        return True
    cgroup_path = "/proc/1/cgroup"
    if os.path.exists(cgroup_path):
        try:
            with open(cgroup_path, "r") as f:
                content = f.read()
                if "docker" in content or "kubepods" in content or "containerd" in content:
                    return True
        except Exception:
            pass
    return False


def get_machine_guid() -> str:
    """Retrieves OS machine ID or persistent platform identifier."""
    # 1. Linux machine-id
    for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return f.read().strip()
            except Exception:
                pass

    # 2. Windows registry MachineGuid or fallback to stable node hash
    if platform.system() == "Windows":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                val, _ = winreg.QueryValueEx(key, "MachineGuid")
                if val:
                    return str(val)
        except Exception:
            pass

    # 3. Fallback deterministic MAC node representation
    node = uuid.getnode()
    return f"NODE-{node:012x}"


def generate_installation_identity(custom_override_id: str = None) -> InstallationFingerprint:
    """
    Generates a cryptographically strong, non-reversible installation fingerprint.
    Used by the customer to request an authorized vendor license.
    """
    if custom_override_id:
        inst_id = custom_override_id
    else:
        guid = get_machine_guid()
        system = platform.system()
        machine = platform.machine()
        hostname = platform.node()
        is_container = detect_container_environment()
        
        raw_seed = f"{guid}::{system}::{machine}::{is_container}"
        h = hashlib.sha256(raw_seed.encode("utf-8")).hexdigest().upper()
        # Format as AVN-INST-XXXX-XXXX-XXXX-XXXX
        inst_id = f"AVN-INST-{h[:4]}-{h[4:8]}-{h[8:12]}-{h[12:16]}"

    mac_hash = hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()[:16]

    return InstallationFingerprint(
        installation_id=inst_id,
        hostname=platform.node(),
        os_system=platform.system(),
        machine_arch=platform.machine(),
        mac_node_hash=mac_hash,
        is_containerized=detect_container_environment()
    )

