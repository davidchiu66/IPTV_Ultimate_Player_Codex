"""Application version helpers."""

from __future__ import annotations

import os
from pathlib import Path

from utils.app_paths import resource_path


DEFAULT_APP_VERSION = "0.0.0-dev"
VERSION_RESOURCE = "app_version.txt"


def get_app_version() -> str:
    """Return the display version from env or bundled build metadata."""
    env_version = os.environ.get("APP_VERSION", "").strip()
    if env_version:
        return env_version

    try:
        version_path = Path(resource_path(VERSION_RESOURCE))
        if version_path.is_file():
            version = version_path.read_text(encoding="utf-8-sig").strip()
            if version:
                return version
    except OSError:
        pass

    return DEFAULT_APP_VERSION
