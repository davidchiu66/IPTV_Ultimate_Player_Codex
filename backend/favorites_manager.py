import copy
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.media_types import resource_type_key
from utils.app_paths import user_config_path


FAVORITES_SCHEMA_VERSION = 1


class FavoritesManager:
    """Manage resource and channel favorites with JSON persistence."""

    def __init__(self, storage_path: str | None = None):
        self.storage_path = Path(storage_path) if storage_path else user_config_path("favorites.json")
        self.data: dict[str, Any] = {
            "version": FAVORITES_SCHEMA_VERSION,
            "resource_favorites": [],
            "channel_favorites": [],
        }
        self.load()

    def load(self) -> None:
        """Load favorites from disk if the file exists."""
        if not self.storage_path.exists():
            return
        try:
            with self.storage_path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
        except Exception:
            return
        if not isinstance(loaded, dict):
            return
        self.data["version"] = loaded.get("version") or FAVORITES_SCHEMA_VERSION
        self.data["resource_favorites"] = list(loaded.get("resource_favorites") or [])
        self.data["channel_favorites"] = list(loaded.get("channel_favorites") or [])

    def save(self) -> None:
        """Persist favorites to disk."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_path.open("w", encoding="utf-8") as handle:
            json.dump(self.data, handle, ensure_ascii=False, indent=2)

    @staticmethod
    def now_iso() -> str:
        """Return a stable ISO timestamp."""
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    @staticmethod
    def normalize_path(path: str) -> str:
        """Normalize a filesystem path for display and de-duplication."""
        if not path:
            return ""
        try:
            normalized = os.path.abspath(os.path.expanduser(str(path)))
        except Exception:
            normalized = str(path)
        return os.path.normpath(normalized)

    @classmethod
    def path_key(cls, path: str) -> str:
        """Return a comparable path key."""
        return os.path.normcase(cls.normalize_path(path))

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:16]

    @classmethod
    def resource_id(cls, path: str) -> str:
        """Build a stable resource favorite id."""
        return cls._hash_text(cls.path_key(path))

    @staticmethod
    def resource_type(path: str) -> str:
        """Classify a resource favorite."""
        return resource_type_key(path)

    def list_resource_favorites(self, validate: bool = True) -> list[dict[str, Any]]:
        """Return resource favorites, optionally annotated with status."""
        items = [dict(item) for item in self.data.get("resource_favorites", [])]
        if validate:
            for item in items:
                if item.get("path"):
                    item["type"] = self.resource_type(item.get("path") or "")
                item.update(self.validate_resource_favorite(item))
        return items

    def is_resource_favorite(self, path: str) -> bool:
        """Return whether the path is already a resource favorite."""
        resource_id = self.resource_id(path)
        return any(item.get("id") == resource_id for item in self.data.get("resource_favorites", []))

    def add_resource_favorite(self, path: str, note: str = "") -> dict[str, Any]:
        """Add a resource favorite or return the existing one."""
        normalized = self.normalize_path(path)
        resource_id = self.resource_id(normalized)
        for item in self.data["resource_favorites"]:
            if item.get("id") == resource_id:
                return item
        item = {
            "id": resource_id,
            "name": os.path.basename(normalized) or normalized,
            "type": self.resource_type(normalized),
            "path": normalized,
            "added_at": self.now_iso(),
            "last_used_at": "",
            "note": note,
        }
        self.data["resource_favorites"].append(item)
        self.save()
        return item

    def remove_resource_favorite(self, favorite_id_or_path: str) -> bool:
        """Remove a resource favorite by id or path."""
        target_id = favorite_id_or_path
        if os.path.sep in str(favorite_id_or_path) or "/" in str(favorite_id_or_path):
            target_id = self.resource_id(favorite_id_or_path)
        before = len(self.data["resource_favorites"])
        self.data["resource_favorites"] = [
            item for item in self.data["resource_favorites"] if item.get("id") != target_id
        ]
        changed = len(self.data["resource_favorites"]) != before
        if changed:
            self.save()
        return changed

    def touch_resource(self, favorite_id: str) -> None:
        """Update last-used time for a resource favorite."""
        for item in self.data["resource_favorites"]:
            if item.get("id") == favorite_id:
                item["last_used_at"] = self.now_iso()
                self.save()
                return

    def validate_resource_favorite(self, item: dict[str, Any]) -> dict[str, str]:
        """Return status metadata for a resource favorite."""
        path = item.get("path") or ""
        if not os.path.exists(path):
            return {"status": "missing", "status_text": "已失效"}
        if self.resource_type(path) == "unknown":
            return {"status": "unsupported", "status_text": "类型异常"}
        return {"status": "ok", "status_text": "有效"}

    @classmethod
    def channel_fingerprint(cls, channel: dict[str, Any]) -> str:
        """Build a stable fingerprint for a channel."""
        tvg_id = str(channel.get("TvgId") or channel.get("tvg-id") or "").strip()
        manifest = str(channel.get("Manifest") or "").strip()
        name = str(channel.get("Name") or "").strip()
        if tvg_id and manifest:
            raw = f"tvg:{tvg_id}|{manifest}"
        else:
            raw = f"name:{name}|{manifest}"
        return cls._hash_text(raw.lower())

    def list_channel_favorites(
        self,
        current_channels: list[dict[str, Any]] | None = None,
        validate: bool = True,
    ) -> list[dict[str, Any]]:
        """Return channel favorites, optionally annotated with status."""
        items = [dict(item) for item in self.data.get("channel_favorites", [])]
        if validate:
            for item in items:
                item.update(self.validate_channel_favorite(item, current_channels))
        return items

    def is_channel_favorite(self, channel: dict[str, Any]) -> bool:
        """Return whether the channel is already a channel favorite."""
        fingerprint = self.channel_fingerprint(channel)
        return any(item.get("fingerprint") == fingerprint for item in self.data.get("channel_favorites", []))

    def add_channel_favorite(
        self,
        channel: dict[str, Any],
        source_path: str = "",
        source_name: str = "",
    ) -> dict[str, Any]:
        """Add a channel favorite with a full channel snapshot."""
        fingerprint = self.channel_fingerprint(channel)
        for item in self.data["channel_favorites"]:
            if item.get("fingerprint") == fingerprint:
                return item
        snapshot = copy.deepcopy(channel)
        item = {
            "id": fingerprint,
            "name": snapshot.get("Name") or "未命名频道",
            "category": snapshot.get("Category") or "",
            "source_path": self.normalize_path(source_path) if source_path else "",
            "source_name": source_name or "",
            "fingerprint": fingerprint,
            "channel": snapshot,
            "added_at": self.now_iso(),
            "last_used_at": "",
        }
        self.data["channel_favorites"].append(item)
        self.save()
        return item

    def remove_channel_favorite(self, favorite_id_or_channel: str | dict[str, Any]) -> bool:
        """Remove a channel favorite by id or channel data."""
        if isinstance(favorite_id_or_channel, dict):
            target_id = self.channel_fingerprint(favorite_id_or_channel)
        else:
            target_id = str(favorite_id_or_channel)
        before = len(self.data["channel_favorites"])
        self.data["channel_favorites"] = [
            item for item in self.data["channel_favorites"] if item.get("id") != target_id
        ]
        changed = len(self.data["channel_favorites"]) != before
        if changed:
            self.save()
        return changed

    def touch_channel(self, favorite_id: str) -> None:
        """Update last-used time for a channel favorite."""
        for item in self.data["channel_favorites"]:
            if item.get("id") == favorite_id:
                item["last_used_at"] = self.now_iso()
                self.save()
                return

    def validate_channel_favorite(
        self,
        item: dict[str, Any],
        current_channels: list[dict[str, Any]] | None = None,
    ) -> dict[str, str]:
        """Return status metadata for a channel favorite."""
        source_path = item.get("source_path") or ""
        if source_path and not os.path.exists(source_path):
            return {"status": "source_missing", "status_text": "来源失效"}
        current_channels = current_channels or []
        if current_channels:
            fingerprint = item.get("fingerprint")
            for channel in current_channels:
                if self.channel_fingerprint(channel) == fingerprint:
                    return {"status": "ok", "status_text": "有效"}
            return {"status": "changed", "status_text": "频道可能已变更"}
        return {"status": "snapshot", "status_text": "快照可用"}
