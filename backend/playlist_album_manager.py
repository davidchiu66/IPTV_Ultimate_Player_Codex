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
            "excluded_paths": [],
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
            normalized["excluded_paths"] = [
                self.path_key(path)
                for path in normalized.get("excluded_paths") or []
                if self.path_key(path)
            ]
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

    def _merge_rescan_items(
        self,
        existing_items: list[dict[str, Any]],
        scanned_items: list[dict[str, Any]],
        excluded_paths: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Keep the user's manual item order while appending newly discovered files."""
        excluded = {self.path_key(path) for path in excluded_paths or [] if self.path_key(path)}
        scanned_by_path = {
            self.path_key(item.get("path") or ""): self._normalize_item(item)
            for item in scanned_items
            if item.get("path") and self.path_key(item.get("path") or "") not in excluded
        }
        used_paths: set[str] = set()
        merged: list[dict[str, Any]] = []

        for item in existing_items or []:
            old_item = self._normalize_item(item)
            path_key = self.path_key(old_item.get("path") or "")
            if path_key in excluded:
                continue
            scanned_item = scanned_by_path.get(path_key)
            if not scanned_item:
                if old_item.get("path") and os.path.isfile(old_item.get("path") or "") and is_local_media(old_item.get("path") or ""):
                    merged.append(old_item)
                    used_paths.add(path_key)
                continue
            refreshed = dict(old_item)
            refreshed["id"] = scanned_item.get("id") or refreshed.get("id")
            refreshed["name"] = scanned_item.get("name") or refreshed.get("name")
            refreshed["path"] = scanned_item.get("path") or refreshed.get("path")
            refreshed["type"] = scanned_item.get("type") or refreshed.get("type")
            if refreshed.get("duration") is None:
                refreshed["duration"] = scanned_item.get("duration")
            merged.append(refreshed)
            used_paths.add(path_key)

        for item in scanned_items or []:
            normalized = self._normalize_item(item)
            path_key = self.path_key(normalized.get("path") or "")
            if path_key and path_key not in used_paths and path_key not in excluded:
                merged.append(normalized)
                used_paths.add(path_key)
        return merged

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
            "excluded_paths": [],
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
                scanned_items = self.scan_directory(album.get("source_dir") or "", bool(album.get("recursive")))
                album["items"] = self._merge_rescan_items(
                    album.get("items") or [],
                    scanned_items,
                    album.get("excluded_paths") or [],
                )
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

    def add_items(self, album_id: str, paths: list[str]) -> int:
        """Add local media files to an album without duplicating existing items."""
        normalized_paths: list[str] = []
        seen_paths: set[str] = set()
        for path in paths or []:
            normalized = self.normalize_path(path)
            path_key = self.path_key(normalized)
            if not normalized or path_key in seen_paths:
                continue
            try:
                if not os.path.isfile(normalized) or not is_local_media(normalized):
                    continue
            except OSError:
                continue
            seen_paths.add(path_key)
            normalized_paths.append(normalized)
        if not normalized_paths:
            return 0

        for album in self.data.get("albums", []):
            if album.get("id") != album_id:
                continue
            items = list(album.get("items") or [])
            existing_paths = {
                self.path_key(item.get("path") or "")
                for item in items
                if self.path_key(item.get("path") or "")
            }
            excluded_paths = {
                self.path_key(path)
                for path in album.get("excluded_paths") or []
                if self.path_key(path)
            }
            added_count = 0
            for path in normalized_paths:
                path_key = self.path_key(path)
                if path_key in existing_paths:
                    excluded_paths.discard(path_key)
                    continue
                items.append(
                    {
                        "id": self.item_id(path),
                        "name": os.path.basename(path),
                        "path": path,
                        "type": resource_type_key(path),
                        "duration": None,
                    }
                )
                existing_paths.add(path_key)
                excluded_paths.discard(path_key)
                added_count += 1
            if added_count <= 0:
                if set(album.get("excluded_paths") or []) != excluded_paths:
                    album["excluded_paths"] = sorted(excluded_paths)
                    album["updated_at"] = self.now_iso()
                    self.save()
                return 0
            album["items"] = items
            album["excluded_paths"] = sorted(excluded_paths)
            album["updated_at"] = self.now_iso()
            self.save()
            return added_count
        return 0

    def remove_items(self, album_id: str, item_ids: list[str]) -> int:
        """Remove items from an album without deleting files from disk."""
        selected_ids = {str(item_id or "") for item_id in item_ids if str(item_id or "")}
        if not selected_ids:
            return 0
        for album in self.data.get("albums", []):
            if album.get("id") != album_id:
                continue
            items = list(album.get("items") or [])
            kept_items = [item for item in items if str(item.get("id") or "") not in selected_ids]
            removed_count = len(items) - len(kept_items)
            if removed_count <= 0:
                return 0
            excluded_paths = {
                self.path_key(path)
                for path in album.get("excluded_paths") or []
                if self.path_key(path)
            }
            for item in items:
                if str(item.get("id") or "") in selected_ids:
                    path_key = self.path_key(item.get("path") or "")
                    if path_key:
                        excluded_paths.add(path_key)
            album["items"] = kept_items
            album["excluded_paths"] = sorted(excluded_paths)
            memory = album.get("playback_memory") or {}
            if str(memory.get("item_id") or "") in selected_ids:
                album["playback_memory"] = {}
            album["updated_at"] = self.now_iso()
            self.save()
            return removed_count
        return 0

    def move_items(self, album_id: str, item_ids: list[str], action: str) -> bool:
        """Move selected items inside an album while preserving their relative order."""
        selected_ids = {str(item_id or "") for item_id in item_ids if str(item_id or "")}
        action = str(action or "").strip().lower()
        if not selected_ids or action not in {"top", "up", "down", "bottom"}:
            return False

        for album in self.data.get("albums", []):
            if album.get("id") != album_id:
                continue
            items = list(album.get("items") or [])
            if len(items) < 2:
                return False
            original_ids = [str(item.get("id") or "") for item in items]

            if action == "top":
                selected = [item for item in items if str(item.get("id") or "") in selected_ids]
                unselected = [item for item in items if str(item.get("id") or "") not in selected_ids]
                moved_items = selected + unselected
            elif action == "bottom":
                selected = [item for item in items if str(item.get("id") or "") in selected_ids]
                unselected = [item for item in items if str(item.get("id") or "") not in selected_ids]
                moved_items = unselected + selected
            elif action == "up":
                moved_items = list(items)
                for index in range(1, len(moved_items)):
                    current_selected = str(moved_items[index].get("id") or "") in selected_ids
                    previous_selected = str(moved_items[index - 1].get("id") or "") in selected_ids
                    if current_selected and not previous_selected:
                        moved_items[index - 1], moved_items[index] = moved_items[index], moved_items[index - 1]
            else:
                moved_items = list(items)
                for index in range(len(moved_items) - 2, -1, -1):
                    current_selected = str(moved_items[index].get("id") or "") in selected_ids
                    next_selected = str(moved_items[index + 1].get("id") or "") in selected_ids
                    if current_selected and not next_selected:
                        moved_items[index], moved_items[index + 1] = moved_items[index + 1], moved_items[index]

            moved_ids = [str(item.get("id") or "") for item in moved_items]
            if moved_ids == original_ids:
                return False
            album["items"] = moved_items
            album["updated_at"] = self.now_iso()
            self.save()
            return True
        return False

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
