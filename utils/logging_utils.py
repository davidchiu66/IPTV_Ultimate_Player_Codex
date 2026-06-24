"""Shared capped logging helpers."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path

from utils.app_paths import APP_STORAGE_DIRNAME, user_data_dir


APP_LOG_FILENAME = "app.log"
MPV_RUNTIME_LOG_FILENAME = "mpv_runtime.log"
DEFAULT_LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_CHECK_INTERVAL_BYTES = 64 * 1024


def log_dir() -> Path:
    """Return the writable per-user log directory."""
    candidates = []
    try:
        candidates.append(user_data_dir() / "logs")
    except Exception:
        pass
    candidates.append(Path(tempfile.gettempdir()) / APP_STORAGE_DIRNAME / "logs")

    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except Exception:
            continue
    return Path.cwd()


def app_log_path() -> Path:
    """Return the single application log file path."""
    return log_dir() / APP_LOG_FILENAME


def mpv_runtime_log_path() -> Path:
    """Return the dedicated libmpv runtime log file path."""
    return log_dir() / MPV_RUNTIME_LOG_FILENAME


def log_max_bytes(default: int = DEFAULT_LOG_MAX_BYTES) -> int:
    """Return configured max log size in bytes."""
    try:
        value = int(os.environ.get("IPTV_LOG_MAX_BYTES", default))
    except (TypeError, ValueError):
        value = int(default)
    return max(512 * 1024, value)


def cap_log_file(path: str | os.PathLike[str] | None = None, max_bytes: int | None = None) -> None:
    """Keep only the tail of the log when it grows beyond the cap."""
    log_path = Path(path) if path is not None else app_log_path()
    max_size = int(max_bytes or log_max_bytes())
    try:
        if not log_path.exists() or log_path.stat().st_size <= max_size:
            return
        keep_bytes = max_size // 2
        with log_path.open("rb") as handle:
            handle.seek(max(0, log_path.stat().st_size - keep_bytes))
            tail = handle.read()
        marker = (
            f"\n--- log trimmed at {datetime.now().isoformat(timespec='seconds')} "
            f"to keep size under {max_size} bytes ---\n"
        ).encode("utf-8")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("wb") as handle:
            handle.write(marker)
            handle.write(tail)
    except Exception:
        pass


class CappedLogHandle:
    """Text append handle that periodically trims the target log file."""

    def __init__(self, path: str | os.PathLike[str] | None = None, max_bytes: int | None = None) -> None:
        self.path = Path(path) if path is not None else app_log_path()
        self.max_bytes = int(max_bytes or log_max_bytes())
        self._bytes_since_check = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        cap_log_file(self.path, self.max_bytes)
        self._handle = self.path.open("a", encoding="utf-8", buffering=1)

    def write(self, text: str) -> int:
        """Write text and trim the file if it has grown too large."""
        if not isinstance(text, str):
            text = str(text)
        written = self._handle.write(text)
        self._bytes_since_check += len(text.encode("utf-8", errors="replace"))
        if self._bytes_since_check >= LOG_CHECK_INTERVAL_BYTES:
            self._maybe_trim()
        return written

    def flush(self) -> None:
        """Flush pending data to disk."""
        self._handle.flush()

    def close(self) -> None:
        """Close the underlying file handle."""
        self._handle.close()

    def _maybe_trim(self) -> None:
        self._bytes_since_check = 0
        try:
            self._handle.flush()
            if self.path.exists() and self.path.stat().st_size > self.max_bytes:
                self._handle.close()
                cap_log_file(self.path, self.max_bytes)
                self._handle = self.path.open("a", encoding="utf-8", buffering=1)
        except Exception:
            pass


def append_capped_log_line(line: str, path: str | os.PathLike[str] | None = None) -> bool:
    """Append one line to the capped app log."""
    log_path = Path(path) if path is not None else app_log_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        cap_log_file(log_path)
        with log_path.open("a", encoding="utf-8", buffering=1) as handle:
            handle.write(line if line.endswith("\n") else f"{line}\n")
        cap_log_file(log_path)
        return True
    except Exception:
        return False
