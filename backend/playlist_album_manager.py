import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.media_types import is_local_media, resource_type_key
from utils.app_paths import user_config_path


PLAYLIST_SCHEMA_VERSION = 1


class PlaylistAlbumManager:
    """Manage persisted local playback albums."""

    def __init__(self, storage_path: str | Path | None = None):
        self.storage_path = Path(storage_path) if storage_path else user_config_path("playlists.json")
        self.data: dict[str, Any] = {
            "version": PLAYLIST_SCHEMA_VERSION,
            "active_album_id": "default",
            "albums": [],
        }
        self.load()

    @staticmethod
    def now_iso() -> str:
        """Return an ISO timestamp with local timezone."""
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    @staticmethod
    def normalize_path(path: str) -> str:
        """Normalize a local filesystem path."""
        if not path:
            return ""
        try:
            return os.path.normpath(os.path.abspath(os.path.expanduser(str(path))))
        except Exception:
            return os.path.normpath(str(path))

    @classmethod
    def path_key(cls, path: str) -> str:
        """Return a comparable path key."""
        return os.path.normcase(cls.normalize_path(path))

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:16]

    @classmethod
    def item_id(cls, path: str) -> str:
        """Build a stable item id from path."""
        return cls._hash_text(cls.path_key(path))

    @classmethod
    def album_id(cls, name: str, source_dir: str = "") -> str:
        """Build a stable album id."""
        raw = f"{name}|{cls.path_key(source_dir)}|{cls.now_iso()}"
        return cls._hash_text(raw)

    @staticmethod
    def default_settings() -> dict[str, Any]:
        """Return default per-album playback settings."""
        return {
            "auto_play_next": True,
            "skip_intro": False,
            "intro_seconds": 0,
            "skip_outro": False,
            "outro_seconds": 0,
            "remember_playback": False,
        }

    def default_album(self) -> dict[str, Any]:
        """Return the default album structure."""
        now = self.now_iso()
        return {
            "id": "default",
            "name": "默认专辑",
            "source_dir": "",
            "recursive": False,
            "items": [],
            "settings": self.default_settings(),
            "created_at": now,
            "updated_at": now,
        }

    def load(self) -> None:
        """Load albums from disk."""
        loaded = {}
        existed = self.storage_path.exists()
        if self.storage_path.exists():
            try:
                loaded = json.loads(self.storage_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                loaded = {}
        if isinstance(loaded, dict):
            self.data["version"] = loaded.get("version") or PLAYLIST_SCHEMA_VERSION
            self.data["active_album_id"] = loaded.get("active_album_id") or "default"
            self.data["albums"] = list(loaded.get("albums") or [])
        self._ensure_default_album()
        self._normalize_albums()
        if not existed:
            self.save()

    def save(self) -> None:
        """Persist albums to disk."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _ensure_default_album(self) -> None:
        albums = self.data.setdefault("albums", [])
        if not any(album.get("id") == "default" for album in albums if isinstance(album, dict)):
            albums.insert(0, self.default_album())

    def _normalize_albums(self) -> None:
        albums = []
        for album in self.data.get("albums", []):
            if not isinstance(album, dict):
                continue
            normalized = dict(album)
            normalized["id"] = str(normalized.get("id") or self.album_id(normalized.get("name") or "专辑"))
            normalized["name"] = str(normalized.get("name") or "未命名专辑")
            normalized["source_dir"] = self.normalize_path(normalized.get("source_dir") or "")
            normalized["recursive"] = bool(normalized.get("recursive"))
            settings = self.default_settings()
            settings.update(normalized.get("settings") or {})
            settings["intro_seconds"] = max(0, int(settings.get("intro_seconds") or 0))
            settings["outro_seconds"] = max(0, int(settings.get("outro_seconds") or 0))
            settings["remember_playback"] = bool(settings.get("remember_playback"))
            normalized["settings"] = settings
            normalized["items"] = [self._normalize_item(item) for item in normalized.get("items") or [] if isinstance(item, dict)]
            memory = normalized.get("playback_memory") or {}
            normalized["playback_memory"] = self._normalize_memory(memory)
            normalized["created_at"] = normalized.get("created_at") or self.now_iso()
            normalized["updated_at"] = normalized.get("updated_at") or normalized["created_at"]
            albums.append(normalized)
        self.data["albums"] = albums
        self._ensure_default_album()

    def _normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        path = self.normalize_path(item.get("path") or "")
        return {
            "id": str(item.get("id") or self.item_id(path)),
            "name": str(item.get("name") or os.path.basename(path)),
            "path": path,
            "type": resource_type_key(path),
            "duration": item.get("duration"),
        }

    def _normalize_memory(self, memory: dict[str, Any]) -> dict[str, Any]:
        """Return normalized playback memory metadata."""
        if not isinstance(memory, dict):
            return {}
        path = self.normalize_path(memory.get("path") or "")
        try:
            position = max(0.0, float(memory.get("position") or 0.0))
        except (TypeError, ValueError):
            position = 0.0
        try:
            duration = max(0.0, float(memory.get("duration") or 0.0))
        except (TypeError, ValueError):
            duration = 0.0
        item_id = str(memory.get("item_id") or self.item_id(path) if path else "")
        if not item_id or not path or position <= 0:
            return {}
        return {
            "item_id": item_id,
            "path": path,
            "position": position,
            "duration": duration,
            "updated_at": str(memory.get("updated_at") or self.now_iso()),
        }

    def albums(self, validate: bool = True) -> list[dict[str, Any]]:
        """Return albums, optionally annotating item status."""
        result = []
        for album in self.data.get("albums", []):
            copy_album = dict(album)
            copy_album["settings"] = dict(album.get("settings") or {})
            copy_album["playback_memory"] = dict(album.get("playback_memory") or {})
            copy_album["items"] = [dict(item) for item in album.get("items") or []]
            if validate:
                for item in copy_album["items"]:
                    item.update(self.validate_item(item))
            result.append(copy_album)
        return result

    def get_album(self, album_id: str | None = None, validate: bool = False) -> dict[str, Any] | None:
        """Return an album by id."""
        target = album_id or self.data.get("active_album_id") or "default"
        for album in self.albums(validate=validate):
            if album.get("id") == target:
                return album
        return None

    def set_active_album(self, album_id: str) -> None:
        """Persist active album id."""
        if self.get_album(album_id):
            self.data["active_album_id"] = album_id
            self.save()

    def scan_directory(self, dir_path: str, recursive: bool = False) -> list[dict[str, Any]]:
        """Scan local media files under a directory."""
        root = self.normalize_path(dir_path)
        items: list[dict[str, Any]] = []
        if not os.path.isdir(root):
            return items
        if recursive:
            iterator = (
                os.path.join(base, name)
                for base, _dirs, files in os.walk(root)
                for name in files
            )
        else:
            iterator = (
                os.path.join(root, name)
                for name in os.listdir(root)
            )
        for path in iterator:
            try:
                if os.path.isfile(path) and is_local_media(path):
                    normalized = self.normalize_path(path)
                    items.append(
                        {
                            "id": self.item_id(normalized),
                            "name": os.path.basename(normalized),
                            "path": normalized,
                            "type": resource_type_key(normalized),
                            "duration": None,
                        }
                    )
            except OSError:
                continue
        items.sort(key=lambda item: str(item.get("name") or "").lower())
        return items

    def create_album_from_directory(self, dir_path: str, name: str = "", recursive: bool = False) -> dict[str, Any]:
        """Create a persisted album from a folder."""
        source_dir = self.normalize_path(dir_path)
        album_name = name.strip() if name else os.path.basename(source_dir) or "新建专辑"
        now = self.now_iso()
        album = {
            "id": self.album_id(album_name, source_dir),
            "name": album_name,
            "source_dir": source_dir,
            "recursive": bool(recursive),
            "items": self.scan_directory(source_dir, recursive=recursive),
            "settings": self.default_settings(),
            "created_at": now,
            "updated_at": now,
        }
        self.data.setdefault("albums", []).append(album)
        self.data["active_album_id"] = album["id"]
        self.save()
        return album

    def update_album(self, album_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        """Update album metadata and settings."""
        for album in self.data.get("albums", []):
            if album.get("id") != album_id:
                continue
            if "name" in updates:
                album["name"] = str(updates.get("name") or album.get("name") or "未命名专辑")
            if "source_dir" in updates:
                album["source_dir"] = self.normalize_path(updates.get("source_dir") or "")
            if "recursive" in updates:
                album["recursive"] = bool(updates.get("recursive"))
            if "settings" in updates and isinstance(updates["settings"], dict):
                settings = self.default_settings()
                settings.update(album.get("settings") or {})
                settings.update(updates["settings"])
                settings["intro_seconds"] = max(0, int(settings.get("intro_seconds") or 0))
                settings["outro_seconds"] = max(0, int(settings.get("outro_seconds") or 0))
                settings["remember_playback"] = bool(settings.get("remember_playback"))
                album["settings"] = settings
            if updates.get("rescan"):
                album["items"] = self.scan_directory(album.get("source_dir") or "", bool(album.get("recursive")))
            album["updated_at"] = self.now_iso()
            self.save()
            return dict(album)
        return None

    def playback_memory(self, album_id: str) -> dict[str, Any]:
        """Return persisted playback memory for an album."""
        album = self.get_album(album_id, validate=False)
        if not album:
            return {}
        return self._normalize_memory(album.get("playback_memory") or {})

    def update_playback_memory(
        self,
        album_id: str,
        item_id: str,
        path: str,
        position: float,
        duration: float = 0.0,
    ) -> bool:
        """Persist the last playback position for an album."""
        normalized_path = self.normalize_path(path)
        memory = self._normalize_memory(
            {
                "item_id": item_id or self.item_id(normalized_path),
                "path": normalized_path,
                "position": position,
                "duration": duration,
                "updated_at": self.now_iso(),
            }
        )
        if not memory:
            return False
        for album in self.data.get("albums", []):
            if album.get("id") != album_id:
                continue
            album["playback_memory"] = memory
            album["updated_at"] = self.now_iso()
            self.save()
            return True
        return False

    def delete_album(self, album_id: str) -> bool:
        """Delete an album relationship without deleting files."""
        if album_id == "default":
            return False
        before = len(self.data.get("albums", []))
        self.data["albums"] = [album for album in self.data.get("albums", []) if album.get("id") != album_id]
        changed = len(self.data["albums"]) != before
        if changed:
            if self.data.get("active_album_id") == album_id:
                self.data["active_album_id"] = "default"
            self.save()
        return changed

    def validate_item(self, item: dict[str, Any]) -> dict[str, str]:
        """Return item status metadata."""
        path = item.get("path") or ""
        if not os.path.exists(path):
            return {"status": "missing", "status_text": "已失效"}
        if not is_local_media(path):
            return {"status": "unsupported", "status_text": "类型异常"}
        return {"status": "ok", "status_text": "有效"}

    def adjacent_item(self, album_id: str, current_item_id: str, step: int) -> dict[str, Any] | None:
        """Return adjacent playable item in an album."""
        album = self.get_album(album_id, validate=True)
        if not album:
            return None
        items = [item for item in album.get("items") or [] if item.get("status") == "ok"]
        if len(items) < 2:
            return None
        ids = [str(item.get("id") or "") for item in items]
        try:
            index = ids.index(str(current_item_id or ""))
        except ValueError:
            index = -1
        return items[(index + step) % len(items)]
