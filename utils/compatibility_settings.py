import os
import sys
from typing import Any

from utils.proxy_settings import load_settings, save_settings


SAFE_MODE_ENV = "IPTV_SAFE_MODE"
FORCE_CUSTOM_CHROME_ENV = "IPTV_FORCE_CUSTOM_CHROME"
SAFE_MODE_ARGS = {"--safe-mode", "--compat-mode", "--compatibility-mode"}
DEFAULT_SAFE_MODE = False


def _truthy(value: Any) -> bool:
    """Return True when a loosely formatted config/env value is enabled."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "safe", "compat"}


def get_compatibility_settings() -> dict[str, bool]:
    """Load persisted compatibility settings."""
    settings = load_settings()
    compatibility = settings.get("compatibility")
    if not isinstance(compatibility, dict):
        compatibility = {}
    return {
        "safe_mode": bool(compatibility.get("safe_mode", DEFAULT_SAFE_MODE)),
    }


def set_compatibility_safe_mode(enabled: bool) -> None:
    """Persist the startup compatibility mode preference."""
    settings = load_settings()
    compatibility = settings.get("compatibility")
    if not isinstance(compatibility, dict):
        compatibility = {}
    compatibility["safe_mode"] = bool(enabled)
    settings["compatibility"] = compatibility
    save_settings(settings)


def is_safe_mode_enabled(argv: list[str] | None = None) -> bool:
    """Return whether the current process should use conservative graphics settings."""
    args = set(argv if argv is not None else sys.argv)
    if args.intersection(SAFE_MODE_ARGS):
        return True
    if _truthy(os.environ.get(SAFE_MODE_ENV)):
        return True
    return bool(get_compatibility_settings().get("safe_mode", DEFAULT_SAFE_MODE))


def should_install_custom_chrome() -> bool:
    """Return whether frameless custom title bars should be enabled."""
    if _truthy(os.environ.get(FORCE_CUSTOM_CHROME_ENV)):
        return True
    return not is_safe_mode_enabled()


def _append_chromium_flags(flags: list[str]) -> None:
    """Append Qt WebEngine Chromium flags without duplicating existing values."""
    current = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
    parts = [current] if current else []
    for flag in flags:
        if flag not in current:
            parts.append(flag)
    if parts:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(parts)


def configure_compatibility_environment(argv: list[str] | None = None) -> dict[str, Any]:
    """Apply startup environment switches before QApplication is created."""
    safe_mode = is_safe_mode_enabled(argv)
    if not safe_mode:
        return {"safe_mode": False, "qt_opengl": os.environ.get("QT_OPENGL", "")}

    os.environ.setdefault("QT_OPENGL", "software")
    os.environ.setdefault("QSG_RHI_BACKEND", "opengl")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    _append_chromium_flags(["--disable-gpu"])
    return {
        "safe_mode": True,
        "qt_opengl": os.environ.get("QT_OPENGL", ""),
        "qsg_rhi_backend": os.environ.get("QSG_RHI_BACKEND", ""),
        "qt_quick_backend": os.environ.get("QT_QUICK_BACKEND", ""),
        "qtwebengine_flags": os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", ""),
    }
