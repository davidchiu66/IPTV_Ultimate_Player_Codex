"""Application path helpers for source and PyInstaller builds."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
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
    candidates: list[Path] = []
    for value in (os.environ.get("LOCALAPPDATA"), os.environ.get("APPDATA")):
        if value:
            candidates.append(Path(value))
    if os.name == "nt":
        candidates.append(Path.home() / "AppData" / "Local")
    else:
        candidates.append(Path.home() / ".local" / "share")
    candidates.append(Path(tempfile.gettempdir()))

    for root in _unique_paths(candidates):
        path = root / APP_STORAGE_DIRNAME
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / f".write_test_{os.getpid()}"
            probe.mkdir()
            probe.rmdir()
            return path
        except OSError:
            continue

    path = Path.cwd() / APP_STORAGE_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _unique_paths(paths: list[Path]) -> list[Path]:
    """Return paths without duplicates while preserving order."""
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path.absolute())
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def legacy_data_paths(relative_path: str | os.PathLike[str]) -> list[Path]:
    """Return possible legacy read-only/source locations for a data path."""
    rel = Path(relative_path)
    if rel.is_absolute():
        return [rel]
    return _unique_paths(
        [
            Path.cwd() / rel,
            executable_root() / rel,
            bundled_root() / rel,
            source_root() / rel,
        ]
    )


def migrate_user_file(
    relative_path: str | os.PathLike[str],
    target_path: str | os.PathLike[str] | None = None,
) -> Path:
    """Copy a legacy file into the user data directory when no user file exists."""
    rel = Path(relative_path)
    target = Path(target_path) if target_path is not None else user_data_dir() / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return target

    try:
        target_key = str(target.resolve())
    except OSError:
        target_key = str(target.absolute())

    for candidate in legacy_data_paths(rel):
        try:
            if not candidate.is_file():
                continue
            if str(candidate.resolve()) == target_key:
                continue
            shutil.copy2(candidate, target)
            break
        except OSError:
            continue
    return target


def seed_user_directory(
    relative_dir: str | os.PathLike[str],
    target_dir: str | os.PathLike[str] | None = None,
) -> Path:
    """Copy bundled/source directory contents into an empty user directory."""
    rel = Path(relative_dir)
    target = Path(target_dir) if target_dir is not None else user_data_dir() / rel
    target.mkdir(parents=True, exist_ok=True)
    try:
        if any(target.iterdir()):
            return target
        target_key = str(target.resolve())
    except OSError:
        return target

    for source in legacy_data_paths(rel):
        try:
            if not source.is_dir():
                continue
            if str(source.resolve()) == target_key:
                continue
            items = list(source.iterdir())
            if not items:
                continue
            for item in items:
                destination = target / item.name
                if item.is_dir():
                    shutil.copytree(item, destination, dirs_exist_ok=True)
                elif item.is_file() and not destination.exists():
                    shutil.copy2(item, destination)
            break
        except OSError:
            continue
    return target


def user_config_dir() -> Path:
    """Return the writable user config directory."""
    path = user_data_dir() / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_config_path(filename: str | os.PathLike[str]) -> Path:
    """Return a writable config file path, migrating old relative config first."""
    name = Path(filename).name
    return migrate_user_file(Path("config") / name, user_config_dir() / name)


def user_channels_dir() -> Path:
    """Return the writable user channel resource directory."""
    return seed_user_directory("Channels", user_data_dir() / "Channels")


def user_epg_dir() -> Path:
    """Return the writable user EPG directory."""
    return seed_user_directory("EPGs", user_data_dir() / "EPGs")


def ensure_user_data_dirs() -> None:
    """Create all standard writable runtime directories."""
    user_config_dir()
    user_channels_dir()
    user_epg_dir()
    (user_data_dir() / "runtime").mkdir(parents=True, exist_ok=True)
    (user_data_dir() / "logs").mkdir(parents=True, exist_ok=True)


def runtime_path(relative_path: str | os.PathLike[str]) -> str:
    """Resolve a writable runtime file path."""
    rel = Path(relative_path)
    if rel.is_absolute():
        path = rel
    else:
        path = user_data_dir() / "runtime" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)
