"""Application path helpers for source and PyInstaller builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_STORAGE_DIRNAME = "IPTV_Ultimate_Player_Codex"


def source_root() -> Path:
    """Return the repository root when running from source."""
    return Path(__file__).resolve().parents[1]


def executable_root() -> Path:
    """Return the executable directory for frozen builds, otherwise source root."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return source_root()


def bundled_root() -> Path:
    """Return PyInstaller's resource root, falling back to the source root."""
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        return Path(bundle_dir)
    return source_root()


def resource_path(relative_path: str | os.PathLike[str]) -> str:
    """Resolve a read-only bundled resource path.

    PyInstaller one-folder builds keep data files under ``sys._MEIPASS``. Source
    runs keep them under the repository root. This helper checks both layouts.
    """
    rel = Path(relative_path)
    if rel.is_absolute():
        return str(rel)

    candidates = [
        bundled_root() / rel,
        executable_root() / rel,
        source_root() / rel,
        Path.cwd() / rel,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(bundled_root() / rel)


def user_data_dir() -> Path:
    """Return a writable per-user application data directory."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        root = Path(base)
    elif os.name == "nt":
        root = Path.home() / "AppData" / "Local"
    else:
        root = Path.home() / ".local" / "share"

    path = root / APP_STORAGE_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def runtime_path(relative_path: str | os.PathLike[str]) -> str:
    """Resolve a writable runtime file path."""
    rel = Path(relative_path)
    if rel.is_absolute():
        path = rel
    else:
        path = user_data_dir() / "runtime" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)
