import json
import os
import copy
import re
import subprocess
import threading
import time
import webbrowser
from urllib.parse import urlparse

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from backend.browser_probe import BrowserProbeSession, WEBENGINE_AVAILABLE, WEBENGINE_ERROR
from backend.epg_manager import EPGManager
from backend.favorites_manager import FavoritesManager
from backend.playlist_album_manager import PlaylistAlbumManager
from backend.playlist_manager import PlaylistManager
from backend.proxy_server import ProxyHTTPRequestHandler, ThreadedTCPServer
from backend.stream_resolver import resolve_channel
from ui.channel_editor_dialog import ChannelEditorDialog
from ui.player_panel import PlayerPanel
from ui.floating_clock import FloatingClock
from ui.toolbar_overlay import ToolbarOverlay
from ui.navigation_overlay import NavigationOverlay
from ui.channel_list_overlay import ChannelListOverlay
from ui.detail_overlay import DetailOverlay
from ui.playlist_album_settings_dialog import PlaylistAlbumSettingsDialog
from ui.playlist_overlay import PlaylistOverlay
from ui.settings_overlay import SettingsOverlay
from ui.about_dialog import AboutDialog
from ui import message_dialogs
from ui import input_dialogs
from utils.diagnostics import (
    classify_failure,
    format_failure_details,
    get_diagnostics_settings,
    log_event,
    new_trace_id,
    set_diagnostics_settings,
)
from utils.proxy_settings import (
    get_browser_port,
    get_browser_probe_timeout_ms,
    get_effective_proxy,
    get_system_proxy,
    get_user_proxy,
    set_browser_port,
    set_browser_probe_timeout_ms,
    set_user_proxy,
)
from utils.playback_settings import (
    get_live_playback_mode,
    get_local_playback_mode,
    set_live_playback_mode,
    set_local_playback_mode,
)
from utils.clock_settings import get_clock_show_weekday, set_clock_show_weekday
from utils.compatibility_settings import get_compatibility_settings, set_compatibility_safe_mode
from utils.media_types import (
    CHANNEL_RESOURCE_EXTENSIONS,
    LOCAL_AUDIO_EXTENSIONS,
    LOCAL_GIF_EXTENSIONS,
    LOCAL_IMAGE_EXTENSIONS,
    LOCAL_MEDIA_EXTENSIONS,
    LOCAL_VIDEO_EXTENSIONS,
    is_channel_resource,
    is_local_media,
    is_local_media_channel,
    is_resource_file,
    resource_type_label,
)
from utils.url_cleaning import clean_media_url
from utils.i18n import get_language, set_language
from utils.app_paths import resource_path, runtime_path, user_channels_dir, user_epg_dir
from ui.theme import APP_QSS
from ui.dialog_style import apply_light_dialog_style
from ui.window_chrome import handle_frameless_native_event, install_custom_window_chrome


HTML_FILE = "live.html"
TEMPLATE_FILE = resource_path("frontend/template.html")
BROWSER_HTML_FILE = runtime_path(HTML_FILE)
DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
DEFAULT_STARTUP_SIZE = QSize(1620, 980)
MIN_STARTUP_SIZE = QSize(960, 620)
STARTUP_SCREEN_RATIO = 0.90


def _url_origin(url):
    try:
        parsed = urlparse(str(url or "").strip())
    except Exception:
        return ""
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _browser_like_referer(page_url, media_url):
    page_origin = _url_origin(page_url)
    media_origin = _url_origin(media_url)
    if page_origin and media_origin and page_origin != media_origin:
        return f"{page_origin}/"
    return page_url or (f"{page_origin}/" if page_origin else "")


def _looks_like_direct_media_url(url):
    lower = str(url or "").strip().lower()
    if not lower:
        return False
    direct_tokens = (
        ".m3u8",
        ".mpd",
        ".flv",
        ".mp4",
        ".mkv",
        ".avi",
        ".ts",
        ".m4s",
    )
    return any(token in lower for token in direct_tokens)


def _is_explicit_http_media_url(url):
    lower = str(url or "").strip().lower()
    return lower.startswith(("http://", "https://")) and any(
        token in lower for token in (".mp4", ".m4v", ".mov", ".flv", ".m3u8", ".mpd")
    )


class OnlineResourceProgressDialog(QDialog):
    """Glass-style busy dialog for online resource loading."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("打开在线资源")
        self.setModal(True)
        self.setMinimumWidth(420)
        apply_light_dialog_style(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        title = QLabel("正在处理在线资源")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self.message_label = QLabel("-")
        self.message_label.setWordWrap(True)
        self.message_label.setObjectName("hintLabel")
        layout.addWidget(self.message_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setStyleSheet(
            """
            QProgressBar {
                background: rgba(8, 12, 18, 180);
                border: 1px solid rgba(120, 180, 255, 90);
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(105, 178, 255, 120),
                    stop:0.5 rgba(140, 205, 255, 230),
                    stop:1 rgba(105, 178, 255, 120)
                );
                border-radius: 4px;
            }
            """
        )
        layout.addWidget(self.progress_bar)

    def set_message(self, message: str) -> None:
        """Update the busy message."""
        self.message_label.setText(message or "")


class MainWindow(QMainWindow):
    epg_loaded_signal = Signal(int, int)
    epg_load_error_signal = Signal(str)
    epg_download_success_signal = Signal(str, bool)
    epg_download_error_signal = Signal(str)
    resource_scan_finished_signal = Signal(int, str, list, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("IPTV 播放器")
        self.playlist_mgr = PlaylistManager(channels_dir=user_channels_dir())
        self.epg_manager = EPGManager(epg_dir=user_epg_dir())
        self.favorites_mgr = FavoritesManager()
        self.playlist_album_mgr = PlaylistAlbumManager()
        self.current_config_path = ""
        self.current_channel = None
        self.cfg_files_cache = []
        self.discovered_epg_urls = []
        self.is_dirty = False
        self.current_m3u_url = None  # 记录当前加载的在线资源 URL

        self.httpd = None
        self.server_thread = None
        self.server_port = get_browser_port()
        self._fallback_dialog_open = False
        self._browser_probe_running = False
        self._last_probe_failure_info = None
        self._current_trace_id = ""
        self._resource_scan_id = 0
        self._resource_scan_threads = []
        self._last_adjacent_switch_at = 0.0
        self._playlist_outro_triggered = False
        self._playlist_intro_applied_key = ""
        self._playlist_memory_record_key = ""
        self._playlist_memory_last_saved_at = 0.0
        self._playlist_memory_last_saved_position = -1.0
        self._pending_playlist_memory_seek = None
        self._fullscreen_cursor_hidden = False
        self._fullscreen_cursor_hide_timer = QTimer(self)
        self._fullscreen_cursor_hide_timer.setSingleShot(True)
        self._fullscreen_cursor_hide_timer.setInterval(2500)
        self._fullscreen_cursor_hide_timer.timeout.connect(self._hide_fullscreen_cursor_if_idle)
        self._online_progress_dialog = None
        self._epg_load_warning_shown = False
        self._playback_queue_context = {
            "kind": "",
            "current_key": "",
            "source": "",
        }

        # 优化缓存
        self._frontend_channels_cache = None
        self._browser_cache = None

        self.epg_loaded_signal.connect(self._on_epg_loaded)
        self.epg_load_error_signal.connect(self._on_epg_load_error)
        self.epg_download_success_signal.connect(self._on_epg_download_success)
        self.epg_download_error_signal.connect(self._on_epg_download_error)
        self.resource_scan_finished_signal.connect(self._on_resource_scan_finished)

        self.resize(self._safe_startup_size())
        self._build_ui()
        self._apply_styles()
        self._refresh_favorites_views()
        self._refresh_playlist_overlay()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        if os.path.isdir(self.playlist_mgr.channels_dir):
            self.refresh_directory(self.playlist_mgr.channels_dir)
        self.load_local_epg()

    def center_on_screen(self):
        screen = self.screen() or QGuiApplication.primaryScreen()
        if not screen:
            return
        safe_size = self._safe_startup_size(screen)
        if self.width() > safe_size.width() or self.height() > safe_size.height():
            self.resize(
                min(self.width(), safe_size.width()),
                min(self.height(), safe_size.height()),
            )
        available = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

    def _safe_startup_size(self, screen=None) -> QSize:
        """Return a startup size that keeps title-bar controls inside the screen."""
        screen = screen or self.screen() or QGuiApplication.primaryScreen()
        if not screen:
            return QSize(DEFAULT_STARTUP_SIZE)

        available = screen.availableGeometry()
        max_width = max(1, int(available.width() * STARTUP_SCREEN_RATIO))
        max_height = max(1, int(available.height() * STARTUP_SCREEN_RATIO))

        min_width = min(MIN_STARTUP_SIZE.width(), max_width)
        min_height = min(MIN_STARTUP_SIZE.height(), max_height)
        width = max(min_width, min(DEFAULT_STARTUP_SIZE.width(), max_width))
        height = max(min_height, min(DEFAULT_STARTUP_SIZE.height(), max_height))
        return QSize(width, height)

    def _build_ui(self):
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪")

        # ===== 隐藏状态栏以获得完整播放区域 =====
        self.statusBar().setVisible(False)

        # 播放器作为中心组件（全屏沉浸）
        self.player_panel = PlayerPanel()
        self.setCentralWidget(self.player_panel)
        self.player_panel.enable_immersive_mode()

        # 方案 A：覆盖层的父级改为始终存在的 video_stack_host
        # 这样即使 mpv_widget 尚未创建，覆盖层也能正常显示
        host = self.player_panel.video_stack_host

        # ---- 悬浮组件（均浮于视频之上）----
        self.floating_clock = FloatingClock(host, show_weekday=get_clock_show_weekday())

        self.toolbar_overlay = ToolbarOverlay(host)
        self.nav_overlay = NavigationOverlay(host)
        self.channel_list_overlay = ChannelListOverlay(host)
        self.detail_overlay = DetailOverlay(host)
        self.playlist_overlay = PlaylistOverlay(host)
        self.settings_overlay = SettingsOverlay(host)

        # 工具栏只保留全局入口：频道资源、设置
        self.toolbar_overlay.add_settings_button(lambda: self.toolbar_overlay.settings_requested.emit())
        self._position_floating()

        # ---- 信号连接 ----
        # 播放器：边缘触发（顶部=工具栏，最左=导航）
        self.player_panel.top_edge_entered.connect(self._show_toolbar)
        self.player_panel.left_edge_entered.connect(self._show_left_edge_panel)
        self.player_panel.right_edge_entered.connect(self._show_playlist_overlay)
        self.player_panel.fullscreen_toggle_requested.connect(self._toggle_fullscreen)
        # 播放控制条：☰ 菜单 / 频道详情 / 上一个 / 下一个
        self.player_panel.menu_requested.connect(self._show_navigation)
        self.player_panel.detail_requested.connect(self._show_detail)
        self.player_panel.load_epg_requested.connect(self.load_local_epg)
        self.player_panel.download_epg_requested.connect(self.download_epg_dialog)
        self.player_panel.prev_channel_requested.connect(self._play_prev_channel)
        self.player_panel.next_channel_requested.connect(self._play_next_channel)
        self.player_panel.loading_overlay_raised.connect(self._raise_interactive_overlays)
        self.player_panel.local_media_finished.connect(self._on_local_media_finished)
        self.player_panel.playback_progress_changed.connect(self._on_playback_progress_changed)

        # 播放器：播放控制
        self.player_panel.channel_play_requested.connect(self.play_channel)
        self.player_panel.stop_requested.connect(self.stop_playback)
        self.player_panel.open_external_requested.connect(self.open_browser_player)
        self.player_panel.open_external_with_browser_requested.connect(self.open_browser_player_with_choice)
        self.player_panel.playback_failed.connect(self._on_playback_failed)

        # 工具栏：频道资源、设置和浏览器观看
        self.toolbar_overlay.open_resource_requested.connect(self.open_channel_resources)
        self.toolbar_overlay.settings_requested.connect(self._show_settings)
        self.toolbar_overlay.open_browser_requested.connect(self.open_browser_player)
        self.toolbar_overlay.choose_browser_requested.connect(self.open_browser_player_with_choice)
        self.toolbar_overlay.stop_requested.connect(self.stop_playback)
        self.settings_overlay.settings_saved.connect(self._on_settings_saved)

        # 导航覆盖层
        self.nav_overlay.open_directory_requested.connect(self.open_directory)
        self.nav_overlay.open_url_requested.connect(self.open_m3u_url)
        self.nav_overlay.refresh_requested.connect(
            lambda: self.refresh_directory(self.playlist_mgr.channels_dir)
        )
        self.nav_overlay.file_selected.connect(self._on_file_selected)
        self.nav_overlay.delete_file_requested.connect(self.delete_channel_file)
        self.nav_overlay.resource_favorite_toggle_requested.connect(self._toggle_resource_favorite)
        self.nav_overlay.resource_favorite_selected.connect(self._on_resource_favorite_selected)
        self.nav_overlay.resource_favorite_removed.connect(self._remove_resource_favorite)
        self.nav_overlay.channel_favorite_selected.connect(self._on_channel_favorite_selected)
        self.nav_overlay.channel_favorite_removed.connect(self._remove_channel_favorite)
        self.nav_overlay.favorites_refresh_requested.connect(self._refresh_favorites_views)

        # 频道列表覆盖层
        self.channel_list_overlay.channel_selected.connect(self.play_channel)
        self.channel_list_overlay.channel_favorite_toggle_requested.connect(self._toggle_channel_favorite)

        # 播放列表覆盖层
        self.playlist_overlay.album_changed.connect(self._on_playlist_album_changed)
        self.playlist_overlay.create_album_requested.connect(self._create_playlist_album)
        self.playlist_overlay.delete_album_requested.connect(self._delete_playlist_album)
        self.playlist_overlay.edit_album_requested.connect(self._edit_playlist_album)
        self.playlist_overlay.refresh_album_requested.connect(self._refresh_playlist_album)
        self.playlist_overlay.item_selected.connect(self._on_playlist_item_selected)
        self.playlist_overlay.memory_play_requested.connect(self._play_playlist_from_memory)

        # 详情覆盖层
        self.detail_overlay.add_requested.connect(self.add_channel)
        self.detail_overlay.edit_requested.connect(self.edit_channel)
        self.detail_overlay.delete_requested.connect(self.delete_channel)

    def _position_floating(self):
        """重新定位悬浮时钟到右上角（相对 video_stack_host 区域）"""
        if hasattr(self, "floating_clock"):
            if self._should_reduce_fullscreen_overlays():
                self.floating_clock.hide()
                return
            host = self.player_panel.video_stack_host
            self.floating_clock.position_at_top_right(host.width())
            self.floating_clock.show()
            self.floating_clock.raise_()

    def _annotate_channel_favorites(self):
        """Attach transient favorite fingerprints to current channel objects."""
        for channel in self.playlist_mgr.streams:
            if isinstance(channel, dict):
                channel["_FavoriteFingerprint"] = self.favorites_mgr.channel_fingerprint(channel)

    def _refresh_favorites_views(self):
        """Refresh favorite tabs and star states."""
        if not hasattr(self, "nav_overlay"):
            return
        self._annotate_channel_favorites()
        resource_items = self.favorites_mgr.list_resource_favorites(validate=True)
        channel_items = self._validated_channel_favorites()
        resource_paths = [item.get("path") for item in resource_items if item.get("path")]
        channel_fingerprints = {
            item.get("fingerprint") for item in self.favorites_mgr.data.get("channel_favorites", []) if item.get("fingerprint")
        }
        self.nav_overlay.set_resource_favorite_paths(resource_paths)
        self.nav_overlay.set_resource_favorites(resource_items)
        self.nav_overlay.set_channel_favorites(channel_items)
        self.channel_list_overlay.set_channel_favorite_fingerprints(channel_fingerprints)

    def _validated_channel_favorites(self) -> list[dict]:
        """Return channel favorites with source-file validation."""
        items = self.favorites_mgr.list_channel_favorites(validate=False)
        current_fingerprints = {
            self.favorites_mgr.channel_fingerprint(channel)
            for channel in self.playlist_mgr.streams
            if isinstance(channel, dict)
        }
        current_config_key = (
            FavoritesManager.path_key(self.current_config_path)
            if self.current_config_path
            else ""
        )
        source_cache: dict[str, dict[str, object]] = {}
        validated: list[dict] = []

        for item in items:
            favorite = dict(item)
            fingerprint = str(favorite.get("fingerprint") or "")
            source_path = str(favorite.get("source_path") or "")

            if source_path and not os.path.exists(source_path):
                favorite.update({"status": "source_missing", "status_text": "来源失效"})
            elif fingerprint and fingerprint in current_fingerprints:
                favorite.update({"status": "ok", "status_text": "有效"})
            elif source_path:
                source_key = FavoritesManager.path_key(source_path)
                if source_key and source_key == current_config_key and self.playlist_mgr.streams:
                    favorite.update({"status": "changed", "status_text": "频道可能已变更"})
                else:
                    favorite.update(self._validate_channel_favorite_source(source_path, fingerprint, source_cache))
            else:
                favorite.update({"status": "snapshot", "status_text": "快照可用"})
            validated.append(favorite)

        return validated

    def _validate_channel_favorite_source(
        self,
        source_path: str,
        fingerprint: str,
        source_cache: dict[str, dict[str, object]],
    ) -> dict[str, str]:
        """Validate a channel favorite by parsing its original source file once."""
        source_key = FavoritesManager.path_key(source_path)
        if source_key not in source_cache:
            manager = PlaylistManager(channels_dir=self.playlist_mgr.channels_dir)
            success, error = manager.load_file(source_path)
            if success:
                fingerprints = {
                    self.favorites_mgr.channel_fingerprint(channel)
                    for channel in manager.streams
                    if isinstance(channel, dict)
                }
                source_cache[source_key] = {
                    "success": True,
                    "error": "",
                    "fingerprints": fingerprints,
                }
            else:
                source_cache[source_key] = {
                    "success": False,
                    "error": error or "无法读取来源文件",
                    "fingerprints": set(),
                }

        cached = source_cache[source_key]
        if not cached.get("success"):
            return {"status": "source_error", "status_text": "来源读取失败"}
        fingerprints = cached.get("fingerprints")
        if isinstance(fingerprints, set) and fingerprint in fingerprints:
            return {"status": "ok", "status_text": "有效"}
        return {"status": "changed", "status_text": "频道可能已变更"}

    def _resource_queue_key(self, path: str) -> str:
        """Return a stable key for a resource path."""
        return FavoritesManager.path_key(path)

    def _channel_queue_key(self, channel: dict | None) -> str:
        """Return a stable key for a channel item."""
        if not isinstance(channel, dict):
            return ""
        return self.favorites_mgr.channel_fingerprint(channel)

    def _set_playback_queue_context(self, kind: str, current_key: str = "", source: str = "") -> None:
        """Remember which queue should answer previous/next commands."""
        kind_text = str(kind or "")
        if kind_text != "playlist_album":
            self._pending_playlist_memory_seek = None
        self._playback_queue_context = {
            "kind": kind_text,
            "current_key": str(current_key or ""),
            "source": str(source or ""),
        }

    def _current_queue_key(self, kind: str) -> str:
        """Return the current key for the requested queue kind."""
        context = self._playback_queue_context or {}
        key = str(context.get("current_key") or "")
        if key:
            return key
        if kind in {"channel_list", "channel_favorites"}:
            return self._channel_queue_key(self.current_channel)
        if kind in {"resource_files", "resource_favorites"}:
            channel = self.current_channel or {}
            return self._resource_queue_key(channel.get("Manifest") or "")
        if kind == "playlist_album":
            channel = self.current_channel or {}
            return str(channel.get("_PlaylistItemId") or "")
        return ""

    def _adjacent_index(self, keys: list[str], current_key: str, step: int) -> int | None:
        """Find the adjacent index in a cyclic queue."""
        valid_keys = [str(key or "") for key in keys]
        if len(valid_keys) < 2:
            return None
        try:
            current_index = valid_keys.index(str(current_key or ""))
        except ValueError:
            current_index = -1
        return (current_index + step) % len(valid_keys)

    def _play_channel_from_queue(self, channel: dict, kind: str, key: str) -> bool:
        """Play a channel and keep the active queue context."""
        if not isinstance(channel, dict) or not channel:
            return False
        self.play_channel(copy.deepcopy(channel), queue_kind=kind, queue_key=key)
        return True

    def _play_resource_from_queue(self, path: str, kind: str, key: str) -> bool:
        """Open a resource path and keep the active queue context."""
        if not path:
            return False
        if not os.path.exists(path):
            self.statusBar().showMessage(f"资源已失效：{os.path.basename(path)}", 4000)
            return False
        self._on_file_selected(path, queue_kind=kind, queue_key=key)
        return True

    def _play_adjacent_channel_list(self, step: int) -> bool:
        """Play previous/next item from the loaded channel list."""
        streams = [channel for channel in self.playlist_mgr.streams if isinstance(channel, dict)]
        if len(streams) < 2:
            if streams:
                self.statusBar().showMessage("当前频道列表没有其他频道可切换", 3000)
            return False
        keys = [self._channel_queue_key(channel) for channel in streams]
        index = self._adjacent_index(keys, self._current_queue_key("channel_list"), step)
        if index is None:
            return False
        return self._play_channel_from_queue(streams[index], "channel_list", keys[index])

    def _play_adjacent_channel_favorite(self, step: int) -> bool:
        """Play previous/next item from channel favorites."""
        favorites = [
            item for item in self.favorites_mgr.list_channel_favorites(validate=False)
            if isinstance(item.get("channel"), dict)
        ]
        if len(favorites) < 2:
            if favorites:
                self.statusBar().showMessage("频道收藏没有其他频道可切换", 3000)
            return False
        keys = [
            str(item.get("id") or item.get("fingerprint") or self._channel_queue_key(item.get("channel")))
            for item in favorites
        ]
        index = self._adjacent_index(keys, self._current_queue_key("channel_favorites"), step)
        if index is None:
            return False
        favorite = favorites[index]
        favorite_id = keys[index]
        if favorite_id:
            self.favorites_mgr.touch_channel(favorite_id)
        self.nav_overlay.hide_with_animation()
        self._refresh_favorites_views()
        return self._play_channel_from_queue(favorite.get("channel") or {}, "channel_favorites", favorite_id)

    def _play_adjacent_resource_file(self, step: int) -> bool:
        """Open previous/next item from the current resource directory."""
        paths = [path for path in self.cfg_files_cache if is_resource_file(path)]
        if len(paths) < 2:
            if paths:
                self.statusBar().showMessage("当前资源目录没有其他资源可切换", 3000)
            return False
        keys = [self._resource_queue_key(path) for path in paths]
        index = self._adjacent_index(keys, self._current_queue_key("resource_files"), step)
        if index is None:
            return False
        return self._play_resource_from_queue(paths[index], "resource_files", keys[index])

    def _play_adjacent_resource_favorite(self, step: int) -> bool:
        """Open previous/next item from resource favorites."""
        favorites = [
            item for item in self.favorites_mgr.list_resource_favorites(validate=False)
            if item.get("path") and is_resource_file(item.get("path"))
        ]
        if len(favorites) < 2:
            if favorites:
                self.statusBar().showMessage("资源收藏没有其他资源可切换", 3000)
            return False
        keys = [
            str(item.get("id") or self.favorites_mgr.resource_id(item.get("path") or ""))
            for item in favorites
        ]
        current_key = self._current_queue_key("resource_favorites")
        start_index = self._adjacent_index(keys, current_key, step)
        if start_index is None:
            return False
        index = start_index
        for _ in range(len(favorites)):
            favorite = favorites[index]
            path = favorite.get("path") or ""
            key = keys[index]
            if os.path.exists(path):
                if key:
                    self.favorites_mgr.touch_resource(key)
                self.nav_overlay.hide_with_animation()
                self._refresh_favorites_views()
                return self._play_resource_from_queue(path, "resource_favorites", key)
            index = (index + step) % len(favorites)
        self.statusBar().showMessage("资源收藏中的文件都已失效，无法切换", 4000)
        self._refresh_favorites_views()
        return False

    def _play_adjacent_playlist_album(self, step: int, auto_advance: bool = False) -> bool:
        """Open previous/next item from the active playlist album."""
        context = self._playback_queue_context or {}
        album_id = str(context.get("source") or self.playlist_album_mgr.data.get("active_album_id") or "default")
        current_key = self._current_queue_key("playlist_album")
        item = self.playlist_album_mgr.adjacent_item(album_id, current_key, step)
        if not item:
            if not auto_advance:
                self.statusBar().showMessage("当前播放专辑没有其他媒体可切换", 3000)
            return False
        return self._play_playlist_item(album_id, item)

    def _play_adjacent_item(self, step: int) -> None:
        """Dispatch previous/next commands according to the active playback queue."""
        now = time.monotonic()
        if now - self._last_adjacent_switch_at < 0.25:
            return
        self._last_adjacent_switch_at = now
        kind = str((self._playback_queue_context or {}).get("kind") or "")
        handlers = {
            "channel_favorites": self._play_adjacent_channel_favorite,
            "resource_favorites": self._play_adjacent_resource_favorite,
            "playlist_album": self._play_adjacent_playlist_album,
            "resource_files": self._play_adjacent_resource_file,
            "channel_list": self._play_adjacent_channel_list,
        }
        handler = handlers.get(kind)
        if handler:
            handler(step)
            return
        if self._play_adjacent_channel_list(step):
            return
        if self._play_adjacent_resource_file(step):
            return
        self.statusBar().showMessage("没有可切换的上一个/下一个项目", 3000)

    def _toggle_resource_favorite(self, path):
        """Add or remove a resource favorite."""
        if not path:
            return
        if self.favorites_mgr.is_resource_favorite(path):
            self.favorites_mgr.remove_resource_favorite(path)
            self.statusBar().showMessage(f"已取消资源收藏：{os.path.basename(path)}", 3000)
        else:
            self.favorites_mgr.add_resource_favorite(path)
            self.statusBar().showMessage(f"已添加资源收藏：{os.path.basename(path)}", 3000)
        self._refresh_favorites_views()

    def _toggle_channel_favorite(self, channel):
        """Add or remove a channel favorite."""
        if not channel:
            return
        source_name = getattr(self.playlist_mgr, "current_file_base_name", "") or os.path.basename(self.current_config_path or "")
        if self.favorites_mgr.is_channel_favorite(channel):
            self.favorites_mgr.remove_channel_favorite(channel)
            self.statusBar().showMessage(f"已取消频道收藏：{channel.get('Name', '未命名')}", 3000)
        else:
            self.favorites_mgr.add_channel_favorite(channel, self.current_config_path, source_name)
            self.statusBar().showMessage(f"已添加频道收藏：{channel.get('Name', '未命名')}", 3000)
        self._refresh_favorites_views()

    def _refresh_playlist_overlay(self) -> None:
        """Refresh local playlist overlay contents."""
        if not hasattr(self, "playlist_overlay"):
            return
        albums = self.playlist_album_mgr.albums(validate=True)
        active_id = self.playlist_album_mgr.data.get("active_album_id") or "default"
        self.playlist_overlay.set_albums(albums, active_id)

    def _show_playlist_overlay(self) -> None:
        """Show the right-side local playback playlist."""
        if self.playlist_overlay.isVisible():
            self.playlist_overlay.reset_hide_timer()
            self.playlist_overlay.raise_()
            return
        if self.settings_overlay.isVisible():
            self.settings_overlay.hide_with_animation()
        if self.channel_list_overlay.isVisible():
            self.channel_list_overlay.hide_with_animation()
        if self.nav_overlay.isVisible():
            self.nav_overlay.hide_with_animation()
        if self.detail_overlay.isVisible():
            self.detail_overlay.hide_with_animation()
        self._refresh_playlist_overlay()
        self.playlist_overlay.show_with_animation()
        self.playlist_overlay.raise_()
        self._sync_player_controls_suppression()

    def _on_playlist_album_changed(self, album_id: str) -> None:
        """Persist active playlist album."""
        self.playlist_album_mgr.set_active_album(album_id)

    def _create_playlist_album(self) -> None:
        """Create a new playlist album from a folder."""
        dialog = PlaylistAlbumSettingsDialog(self, create_mode=True)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        source_dir = values.get("source_dir") or ""
        if not source_dir or not os.path.isdir(source_dir):
            message_dialogs.warning(self, "播放列表", "请选择有效的专辑文件夹。")
            return
        album = self.playlist_album_mgr.create_album_from_directory(
            source_dir,
            name=values.get("name") or "",
            recursive=bool(values.get("recursive")),
        )
        self.playlist_album_mgr.update_album(album.get("id") or "", {"settings": values.get("settings") or {}})
        self._refresh_playlist_overlay()
        self.statusBar().showMessage(f"已创建播放专辑：{album.get('name')}", 3000)

    def _edit_playlist_album(self, album_id: str) -> None:
        """Edit album settings."""
        album = self.playlist_album_mgr.get_album(album_id, validate=False)
        if not album:
            return
        dialog = PlaylistAlbumSettingsDialog(self, album=album)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        self.playlist_album_mgr.update_album(album_id, values)
        self._refresh_playlist_overlay()
        self.statusBar().showMessage("播放专辑设置已保存", 3000)

    def _delete_playlist_album(self, album_id: str) -> None:
        """Delete an album relationship."""
        album = self.playlist_album_mgr.get_album(album_id, validate=False)
        name = (album or {}).get("name") or "该专辑"
        reply = message_dialogs.question(
            self,
            "删除专辑",
            f"确定删除“{name}”吗？不会删除原始媒体文件。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        if self.playlist_album_mgr.delete_album(album_id):
            self._refresh_playlist_overlay()
            self.statusBar().showMessage("播放专辑已删除", 3000)

    def _refresh_playlist_album(self, album_id: str) -> None:
        """Rescan an album source folder."""
        self.playlist_album_mgr.update_album(album_id, {"rescan": True})
        self._refresh_playlist_overlay()
        self.statusBar().showMessage("播放专辑已刷新", 3000)

    def _on_playlist_item_selected(self, album_id: str, item_id: str, path: str) -> None:
        """Play a selected playlist item."""
        item = {"id": item_id, "path": path}
        self._play_playlist_item(album_id, item)

    def _play_playlist_from_memory(self, album_id: str) -> None:
        """Play the remembered item and seek to its last position."""
        memory = self.playlist_album_mgr.playback_memory(album_id)
        if not memory:
            message_dialogs.information(self, "播放列表", "当前播放列表没有播放记忆点。")
            return

        album = self.playlist_album_mgr.get_album(album_id, validate=True)
        if not album:
            message_dialogs.information(self, "播放列表", "当前播放列表没有播放记忆点。")
            return

        memory_item_id = str(memory.get("item_id") or "")
        memory_path = self.playlist_album_mgr.normalize_path(memory.get("path") or "")
        items = [item for item in album.get("items") or [] if item.get("status") == "ok"]
        item = next((entry for entry in items if str(entry.get("id") or "") == memory_item_id), None)
        if item is None and memory_path:
            memory_key = self.playlist_album_mgr.path_key(memory_path)
            item = next(
                (
                    entry for entry in items
                    if self.playlist_album_mgr.path_key(entry.get("path") or "") == memory_key
                ),
                None,
            )
        if item is None:
            message_dialogs.warning(self, "播放列表", "播放记忆点对应的媒体已失效。")
            self._refresh_playlist_overlay()
            return

        try:
            position = max(0.0, float(memory.get("position") or 0.0))
        except (TypeError, ValueError):
            position = 0.0
        if position <= 0:
            message_dialogs.information(self, "播放列表", "当前播放列表没有播放记忆点。")
            return

        if self._play_playlist_item(album_id, item):
            self._pending_playlist_memory_seek = {
                "album_id": album_id,
                "item_id": str(item.get("id") or memory_item_id),
                "position": position,
            }
            self.playlist_overlay.hide_with_animation()

    def _play_playlist_item(self, album_id: str, item: dict) -> bool:
        """Play a local media item from a playlist album."""
        path = item.get("path") or ""
        if not path or not os.path.exists(path):
            message_dialogs.warning(self, "播放列表", "该媒体文件已失效，无法播放。")
            self._refresh_playlist_overlay()
            return False
        item_id = str(item.get("id") or self.playlist_album_mgr.item_id(path))
        self._pending_playlist_memory_seek = None
        self._playlist_memory_record_key = ""
        self._playlist_memory_last_saved_at = 0.0
        self._playlist_memory_last_saved_position = -1.0
        self._playlist_outro_triggered = False
        self._playlist_intro_applied_key = ""
        self._play_local_media_file(path, queue_kind="playlist_album", queue_key=item_id, queue_source=album_id)
        if self.current_channel:
            self.current_channel["_PlaylistAlbumId"] = album_id
            self.current_channel["_PlaylistItemId"] = item_id
        self._set_playback_queue_context("playlist_album", item_id, album_id)
        return True

    def _active_playlist_album(self) -> dict | None:
        """Return the album for current playlist playback context."""
        context = self._playback_queue_context or {}
        if context.get("kind") != "playlist_album":
            return None
        album_id = str(context.get("source") or "")
        return self.playlist_album_mgr.get_album(album_id, validate=False)

    def _active_playlist_settings(self) -> dict:
        """Return settings for active playlist album."""
        album = self._active_playlist_album() or {}
        settings = dict(album.get("settings") or {})
        defaults = self.playlist_album_mgr.default_settings()
        defaults.update(settings)
        return defaults

    def _on_local_media_finished(self, _channel: dict) -> None:
        """Auto-advance local playlist playback after natural end."""
        context = self._playback_queue_context or {}
        if context.get("kind") != "playlist_album":
            return
        settings = self._active_playlist_settings()
        if not settings.get("auto_play_next", True):
            return
        self._play_adjacent_playlist_album(1, auto_advance=True)

    @staticmethod
    def _format_memory_position(seconds: float) -> str:
        """Format a playback memory position."""
        value = max(0, int(seconds or 0))
        hours, remainder = divmod(value, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def _apply_pending_playlist_memory_seek(self, context: dict, duration_value: float) -> bool:
        """Apply delayed seek for playlist memory playback."""
        pending = self._pending_playlist_memory_seek
        if not pending:
            return False
        album_id = str(context.get("source") or "")
        item_id = str(context.get("current_key") or "")
        if album_id != str(pending.get("album_id") or "") or item_id != str(pending.get("item_id") or ""):
            return False
        try:
            position = max(0.0, float(pending.get("position") or 0.0))
        except (TypeError, ValueError):
            position = 0.0
        if position <= 0:
            self._pending_playlist_memory_seek = None
            return False
        if duration_value > 0:
            position = min(position, max(0.0, duration_value - 0.5))
        self.player_panel.seek_absolute(position)
        self._playlist_intro_applied_key = item_id
        self._playlist_outro_triggered = False
        self._pending_playlist_memory_seek = None
        self.statusBar().showMessage(f"已从记忆点 {self._format_memory_position(position)} 开始播放", 3000)
        return True

    def _maybe_record_playlist_playback_memory(self, context: dict, position_value: float, duration_value: float, settings: dict) -> None:
        """Persist playlist playback memory with throttling."""
        if not settings.get("remember_playback"):
            return
        album_id = str(context.get("source") or "")
        item_id = str(context.get("current_key") or "")
        path = (self.current_channel or {}).get("Manifest") or ""
        if not album_id or not item_id or not path or not os.path.exists(path):
            return
        if duration_value <= 0 or position_value < 1.0:
            return

        record_key = f"{album_id}|{item_id}"
        now = time.monotonic()
        if record_key != self._playlist_memory_record_key:
            self._playlist_memory_record_key = record_key
            self._playlist_memory_last_saved_at = 0.0
            self._playlist_memory_last_saved_position = -1.0

        if (
            now - self._playlist_memory_last_saved_at < 5.0
            and abs(position_value - self._playlist_memory_last_saved_position) < 10.0
        ):
            return

        if self.playlist_album_mgr.update_playback_memory(
            album_id,
            item_id,
            path,
            position_value,
            duration_value,
        ):
            self._playlist_memory_last_saved_at = now
            self._playlist_memory_last_saved_position = position_value

    def _on_playback_progress_changed(self, position, duration) -> None:
        """Handle playlist intro/outro skipping."""
        context = self._playback_queue_context or {}
        if context.get("kind") != "playlist_album":
            return
        try:
            position_value = float(position or 0.0)
            duration_value = float(duration or 0.0)
        except (TypeError, ValueError):
            return
        if duration_value <= 0:
            return
        settings = self._active_playlist_settings()
        current_key = str(context.get("current_key") or "")
        if self._apply_pending_playlist_memory_seek(context, duration_value):
            return
        self._maybe_record_playlist_playback_memory(context, position_value, duration_value, settings)
        intro_seconds = int(settings.get("intro_seconds") or 0)
        if (
            settings.get("skip_intro")
            and intro_seconds > 0
            and current_key
            and self._playlist_intro_applied_key != current_key
            and position_value < max(0, intro_seconds - 0.5)
        ):
            self._playlist_intro_applied_key = current_key
            mpv_widget = getattr(self.player_panel, "mpv_widget", None)
            if mpv_widget is not None:
                mpv_widget.seek_fraction(min(0.98, intro_seconds / duration_value))
            return
        outro_seconds = int(settings.get("outro_seconds") or 0)
        if (
            settings.get("auto_play_next", True)
            and settings.get("skip_outro")
            and outro_seconds > 0
            and not self._playlist_outro_triggered
            and duration_value - position_value <= outro_seconds
        ):
            self._playlist_outro_triggered = True
            self._play_adjacent_playlist_album(1, auto_advance=True)

    def _on_resource_favorite_selected(self, path, favorite_id):
        """Use a resource favorite."""
        if not path or not os.path.exists(path):
            message_dialogs.warning(self, "资源收藏", "该收藏资源已失效，原文件不存在。")
            self._refresh_favorites_views()
            return
        if favorite_id:
            self.favorites_mgr.touch_resource(favorite_id)
        self._on_file_selected(
            path,
            queue_kind="resource_favorites",
            queue_key=favorite_id or self.favorites_mgr.resource_id(path),
        )
        self._refresh_favorites_views()

    def _remove_resource_favorite(self, favorite_id):
        """Remove a resource favorite relationship."""
        if self.favorites_mgr.remove_resource_favorite(favorite_id):
            self.statusBar().showMessage("已取消资源收藏", 3000)
        self._refresh_favorites_views()

    def _on_channel_favorite_selected(self, channel, favorite_id):
        """Play a channel favorite snapshot."""
        if not channel:
            message_dialogs.warning(self, "频道收藏", "该频道收藏缺少频道快照。")
            return
        if favorite_id:
            self.favorites_mgr.touch_channel(favorite_id)
        self.nav_overlay.hide_with_animation()
        self.play_channel(
            copy.deepcopy(channel),
            queue_kind="channel_favorites",
            queue_key=favorite_id or self._channel_queue_key(channel),
        )
        self._refresh_favorites_views()

    def _remove_channel_favorite(self, favorite_id):
        """Remove a channel favorite relationship."""
        if self.favorites_mgr.remove_channel_favorite(favorite_id):
            self.statusBar().showMessage("已取消频道收藏", 3000)
        self._refresh_favorites_views()

    def _is_live_playback_context(self):
        """Return whether the left edge should open the channel list."""
        if not self.playlist_mgr.streams:
            return False

        mpv_widget = getattr(self.player_panel, "mpv_widget", None)
        channel = self.current_channel or getattr(mpv_widget, "current_channel", None) or {}
        if channel and is_local_media_channel(channel):
            return False

        if self.current_config_path and is_channel_resource(self.current_config_path):
            return True
        if channel:
            return not is_local_media_channel(channel)
        return False

    def _show_left_edge_panel(self):
        """Show channel list for live playback, otherwise show resource library."""
        if self._is_live_playback_context():
            self._show_channel_list()
        else:
            self._show_navigation()

    def _show_channel_list(self):
        """显示频道列表覆盖层（与详情互斥）"""
        if self.channel_list_overlay.isVisible():
            return  # 已滑入，避免重复触发
        if self.detail_overlay.isVisible():
            self.detail_overlay.hide_with_animation()
        if self.nav_overlay.isVisible():
            self.nav_overlay.hide_with_animation()
        if self.playlist_overlay.isVisible():
            self.playlist_overlay.hide_with_animation()
        if self.settings_overlay.isVisible():
            self.settings_overlay.hide_with_animation()

        self.channel_list_overlay.show_with_animation()
        self.channel_list_overlay.raise_()
        self._sync_player_controls_suppression()

    def _show_detail(self):
        """显示详情覆盖层（与频道列表互斥）"""
        if self.detail_overlay.isVisible():
            return  # 已滑入，避免重复触发
        if self.channel_list_overlay.isVisible():
            self.channel_list_overlay.hide_with_animation()
        if self.nav_overlay.isVisible():
            self.nav_overlay.hide_with_animation()
        if self.playlist_overlay.isVisible():
            self.playlist_overlay.hide_with_animation()
        if self.settings_overlay.isVisible():
            self.settings_overlay.hide_with_animation()

        self.detail_overlay.set_channel(self.current_channel)
        self.detail_overlay.show_with_animation()
        self.detail_overlay.raise_()
        self._sync_player_controls_suppression()

    def _show_navigation(self):
        """显示资源库覆盖层。"""
        if self.nav_overlay.isVisible():
            return  # 已滑入，鼠标仍在最左边也不重复滑入
        if self.channel_list_overlay.isVisible():
            self.channel_list_overlay.hide_with_animation()
        if self.detail_overlay.isVisible():
            self.detail_overlay.hide_with_animation()
        if self.playlist_overlay.isVisible():
            self.playlist_overlay.hide_with_animation()
        if self.settings_overlay.isVisible():
            self.settings_overlay.hide_with_animation()

        self.nav_overlay.show_with_animation()
        self.nav_overlay.raise_()
        self._sync_player_controls_suppression()

    def _show_settings(self):
        """显示右侧应用设置面板。"""
        if self.settings_overlay.isVisible():
            return
        if self.channel_list_overlay.isVisible():
            self.channel_list_overlay.hide_with_animation()
        if self.nav_overlay.isVisible():
            self.nav_overlay.hide_with_animation()
        if self.detail_overlay.isVisible():
            self.detail_overlay.hide_with_animation()
        if self.playlist_overlay.isVisible():
            self.playlist_overlay.hide_with_animation()

        effective_proxy, proxy_source = get_effective_proxy(self.current_channel or {})
        diagnostics = get_diagnostics_settings()
        self.settings_overlay.set_values(
            get_system_proxy(),
            get_user_proxy(),
            effective_proxy,
            proxy_source,
            get_browser_probe_timeout_ms(),
            self.server_port,
            diagnostics.get("enabled", False),
            diagnostics.get("level", "error"),
            get_local_playback_mode(),
            get_live_playback_mode(),
            get_language(),
            get_clock_show_weekday(),
            get_compatibility_settings().get("safe_mode", False),
        )
        self.settings_overlay.show_with_animation()
        self.settings_overlay.raise_()
        self._sync_player_controls_suppression()

    def _show_toolbar(self):
        """显示工具栏覆盖层（鼠标移到顶部边缘）"""
        if self.toolbar_overlay.isVisible():
            return  # 已显示，避免重复触发
        self.toolbar_overlay.show_with_animation()

    def _sync_player_controls_suppression(self):
        """侧边交互面板可见时，暂停播放控制条自动滑入。"""
        side_overlay_visible = any(
            overlay.isVisible()
            for overlay in (
                self.nav_overlay,
                self.channel_list_overlay,
                self.detail_overlay,
                self.playlist_overlay,
                self.settings_overlay,
            )
        )
        self.player_panel.set_controls_suppressed(side_overlay_visible)
        if side_overlay_visible and hasattr(self.player_panel, "_disable_triggers_interaction"):
            self.player_panel._disable_triggers_interaction()
        elif not side_overlay_visible and hasattr(self.player_panel, "_enable_triggers_interaction"):
            self.player_panel._enable_triggers_interaction()
        self._raise_interactive_overlays()

    def _raise_interactive_overlays(self):
        """Keep side panels above the loading mask so they stay clickable."""
        if hasattr(self, "floating_clock"):
            if self._should_reduce_fullscreen_overlays():
                self.floating_clock.hide()
            else:
                self.floating_clock.show()
                self.floating_clock.raise_()
        for overlay in (
            self.toolbar_overlay,
            self.nav_overlay,
            self.channel_list_overlay,
            self.detail_overlay,
            self.playlist_overlay,
            self.settings_overlay,
        ):
            if overlay.isVisible():
                overlay.raise_()

    def _toggle_fullscreen(self):
        """切换主窗口全屏。整窗切换可保持覆盖层层级与父子关系不变，
        避免把原生 mpv 窗口单独提升为顶层窗口导致覆盖层错位/失效。"""
        entering = not self.isFullScreen()
        self._log_fullscreen_state("fullscreen.toggle.before", entering=entering)
        if self.isFullScreen():
            self.showNormal()
            self._restore_fullscreen_cursor()
            self._fullscreen_cursor_hide_timer.stop()
        else:
            self.showFullScreen()
            self._schedule_fullscreen_cursor_hide()
        # 等待新尺寸生效后重新对齐覆盖层
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._reposition_visible_overlays)
        QTimer.singleShot(0, self._apply_fullscreen_overlay_policy)
        QTimer.singleShot(200, lambda entering=entering: self._log_fullscreen_state("fullscreen.toggle.after", entering=entering))

    def _fullscreen_debug_info(self) -> dict:
        host = self.player_panel.video_stack_host
        screen = self.windowHandle().screen() if self.windowHandle() else QGuiApplication.primaryScreen()
        info = {
            "window_fullscreen": self.isFullScreen(),
            "window_maximized": self.isMaximized(),
            "window_geometry": {
                "x": self.x(),
                "y": self.y(),
                "w": self.width(),
                "h": self.height(),
            },
            "host_geometry": {
                "x": host.x(),
                "y": host.y(),
                "w": host.width(),
                "h": host.height(),
            },
            "current_is_local": is_local_media_channel(self.current_channel or {}),
            "overlay_reduced": self._should_reduce_fullscreen_overlays(),
            "floating_clock_visible": bool(getattr(self, "floating_clock", None) and self.floating_clock.isVisible()),
            "toolbar_visible": bool(getattr(self, "toolbar_overlay", None) and self.toolbar_overlay.isVisible()),
            "side_overlay_visible": self._side_overlay_visible(),
        }
        if screen is not None:
            geometry = screen.geometry()
            available = screen.availableGeometry()
            info.update(
                {
                    "screen_name": screen.name(),
                    "screen_geometry": {
                        "x": geometry.x(),
                        "y": geometry.y(),
                        "w": geometry.width(),
                        "h": geometry.height(),
                    },
                    "screen_available": {
                        "x": available.x(),
                        "y": available.y(),
                        "w": available.width(),
                        "h": available.height(),
                    },
                    "device_pixel_ratio": screen.devicePixelRatio(),
                    "logical_dpi": screen.logicalDotsPerInch(),
                    "physical_dpi": screen.physicalDotsPerInch(),
                    "refresh_rate": screen.refreshRate(),
                }
            )
        return info

    def _log_fullscreen_state(self, event: str, entering: bool = False) -> None:
        channel = self.current_channel or {}
        try:
            log_event(
                event,
                "info",
                trace_id=str(channel.get("_TraceId") or self._current_trace_id or ""),
                channel=channel,
                entering=bool(entering),
                state=self._fullscreen_debug_info(),
            )
        except Exception:
            pass

    def _should_reduce_fullscreen_overlays(self) -> bool:
        """Whether always-on overlays should be reduced during playback."""
        return False

    def _apply_fullscreen_overlay_policy(self) -> None:
        if not hasattr(self, "floating_clock"):
            return
        if self._should_reduce_fullscreen_overlays():
            self.floating_clock.hide()
            return
        self._position_floating()

    def _apply_local_fullscreen_renderer_policy(self, entering: bool | None = None) -> None:
        """Fullscreen no longer reloads local playback; local media uses one stable renderer."""
        return

    def _event_belongs_to_main_window(self, watched) -> bool:
        """Return whether an application event belongs to this window."""
        if isinstance(watched, QWidget):
            return watched.window() is self
        return False

    def _side_overlay_visible(self) -> bool:
        """Return whether a side overlay is currently visible."""
        return any(
            overlay.isVisible()
            for overlay in (
                self.nav_overlay,
                self.channel_list_overlay,
                self.detail_overlay,
                self.playlist_overlay,
                self.settings_overlay,
            )
        )

    def _schedule_fullscreen_cursor_hide(self) -> None:
        """Restart the no-mouse-activity cursor hide timer."""
        if not self.isFullScreen():
            self._fullscreen_cursor_hide_timer.stop()
            self._restore_fullscreen_cursor()
            return
        self._fullscreen_cursor_hide_timer.start()

    def _restore_fullscreen_cursor(self) -> None:
        """Restore the cursor if this window hid it for fullscreen playback."""
        if not self._fullscreen_cursor_hidden:
            return
        QApplication.restoreOverrideCursor()
        self._fullscreen_cursor_hidden = False

    def _hide_fullscreen_cursor_if_idle(self) -> None:
        """Hide the cursor after a short idle period in fullscreen playback."""
        if not self.isFullScreen() or self._side_overlay_visible():
            self._restore_fullscreen_cursor()
            return
        if not self._fullscreen_cursor_hidden:
            QApplication.setOverrideCursor(Qt.BlankCursor)
            self._fullscreen_cursor_hidden = True

    def eventFilter(self, watched, event):
        """Track fullscreen input activity so the cursor can auto-hide."""
        if self.isFullScreen() and self._event_belongs_to_main_window(watched):
            if event.type() in (
                QEvent.MouseMove,
                QEvent.MouseButtonPress,
                QEvent.MouseButtonRelease,
                QEvent.Wheel,
                QEvent.KeyPress,
            ):
                self._restore_fullscreen_cursor()
                self._schedule_fullscreen_cursor_hide()
        return super().eventFilter(watched, event)

    def _reposition_visible_overlays(self):
        """窗口尺寸变化后，重新对齐时钟及当前可见的覆盖层。
        若覆盖层正在播放滑入/滑出动画，先停止以免动画用旧尺寸覆盖新位置。"""
        self._position_floating()
        host = self.player_panel.video_stack_host
        w, h = host.width(), host.height()

        from PySide6.QtCore import QAbstractAnimation

        # 工具栏：可见时贴合顶部、铺满宽度
        if self.toolbar_overlay.isVisible():
            anim = getattr(self.toolbar_overlay, "animation", None)
            # 只有动画不在运行时才重新定位，避免打断滑入动画
            if anim is None or anim.state() == QAbstractAnimation.Stopped:
                self.toolbar_overlay.setGeometry(0, 0, w, self.toolbar_overlay.height())
                self.toolbar_overlay.raise_()

        # 侧边覆盖层：可见时按 side 重新贴边（高度铺满，留 10px 边距）
        for ov in (self.nav_overlay, self.channel_list_overlay, self.detail_overlay, self.playlist_overlay, self.settings_overlay):
            if not ov.isVisible():
                continue
            anim = getattr(ov, "animation", None)
            # 只有动画不在运行时才重新定位，避免打断滑入动画
            if anim is None or anim.state() == QAbstractAnimation.Stopped:
                ow = ov.overlay_width
                x = 10 if ov.side == 'left' else (w - ow - 10)
                ov.setGeometry(x, 10, ow, h - 20)
                ov.raise_()

    def keyPressEvent(self, event):
        """快捷键处理：Esc 退出全屏，F1/F11 切换全屏"""
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self._log_fullscreen_state("fullscreen.escape.before", entering=False)
            self.showNormal()
            self._restore_fullscreen_cursor()
            self._fullscreen_cursor_hide_timer.stop()
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._reposition_visible_overlays)
            QTimer.singleShot(0, self._apply_fullscreen_overlay_policy)
            QTimer.singleShot(200, lambda: self._log_fullscreen_state("fullscreen.escape.after", entering=False))
            return
        elif event.key() in (Qt.Key_F1, Qt.Key_F11):
            self._toggle_fullscreen()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_visible_overlays()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            self._apply_fullscreen_overlay_policy()
            self._log_fullscreen_state("window.state_changed", entering=self.isFullScreen())

    def showEvent(self, event):
        super().showEvent(event)
        self._position_floating()
        # 布局稳定后再次定位，避免首帧时钟位置偏移
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._position_floating)
        # MPV 初始化后，确保所有覆盖层在正确的 z-order
        QTimer.singleShot(200, self._raise_all_overlays)

    def _raise_all_overlays(self):
        """确保所有覆盖层和触发区域在 MPV 窗口之上"""
        if self._should_reduce_fullscreen_overlays():
            self.floating_clock.hide()
        else:
            self.floating_clock.show()
            self.floating_clock.raise_()
        # 提升所有覆盖层
        self.toolbar_overlay.raise_()
        self.nav_overlay.raise_()
        self.channel_list_overlay.raise_()
        self.detail_overlay.raise_()
        self.playlist_overlay.raise_()
        self.settings_overlay.raise_()
        # 提升边缘悬停区域
        if self.player_panel._triggers_enabled:
            self.player_panel.top_edge.raise_()
            self.player_panel.left_edge.raise_()
            self.player_panel.right_edge.raise_()

    def _apply_styles(self):
        """Apply the shared glassmorphism application theme."""
        self.setStyleSheet(APP_QSS)
        title_bar = install_custom_window_chrome(self, show_window_controls=True, resizable=False)
        if title_bar is not None and not getattr(self, "_about_title_logo_connected", False):
            title_bar.logo.clicked.connect(self.show_about_dialog)
            self._about_title_logo_connected = True

    def show_about_dialog(self) -> None:
        """Show the application about dialog from the custom title icon."""
        dialog = AboutDialog(self)
        dialog.exec()

    def nativeEvent(self, event_type, message):  # type: ignore[override]
        """Keep invisible resize borders after switching to a frameless title bar."""
        handled, result = handle_frameless_native_event(self, event_type, message)
        if handled:
            return True, result
        return super().nativeEvent(event_type, message)

    def refresh_directory(self, dir_path):
        if not os.path.isdir(dir_path):
            self.statusBar().showMessage(f"目录不存在：{dir_path}")
            return

        self._resource_scan_id += 1
        scan_id = self._resource_scan_id
        self.cfg_files_cache = []
        self.nav_overlay.update_info(
            dir_path=dir_path,
            file_count=0,
        )
        self.nav_overlay.set_scanning(dir_path)
        self.statusBar().showMessage(f"正在扫描资源目录：{dir_path}")

        worker = threading.Thread(
            target=self._scan_resource_directory_worker,
            args=(scan_id, dir_path),
            daemon=True,
        )
        self._resource_scan_threads = [t for t in self._resource_scan_threads if t.is_alive()]
        self._resource_scan_threads.append(worker)
        worker.start()

    def _scan_resource_directory_worker(self, scan_id, dir_path):
        files = []
        error = ""
        try:
            with os.scandir(dir_path) as entries:
                for entry in entries:
                    try:
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        if is_resource_file(entry.path):
                            files.append(entry.path)
                    except OSError:
                        continue
        except Exception as exc:
            error = str(exc)

        files.sort(key=lambda p: os.path.basename(p).lower())
        self.resource_scan_finished_signal.emit(scan_id, dir_path, files, error)

    def _on_resource_scan_finished(self, scan_id, dir_path, files, error):
        if scan_id != self._resource_scan_id:
            return
        if error:
            self.statusBar().showMessage(f"扫描资源目录失败：{error}")
            self.nav_overlay.update_info(dir_path=dir_path, file_count=0)
            self.nav_overlay.set_files([])
            return

        self.cfg_files_cache = list(files)
        self.nav_overlay.update_info(
            dir_path=dir_path,
            file_count=len(self.cfg_files_cache),
        )
        self.nav_overlay.set_files(self.cfg_files_cache)
        self._refresh_favorites_views()
        self.statusBar().showMessage(f"已扫描 {len(self.cfg_files_cache)} 个资源文件")

    def open_channel_resources(self):
        self._show_navigation()
        self.refresh_directory(self.playlist_mgr.channels_dir)

    def open_directory(self):
        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "选择资源目录",
            self.playlist_mgr.channels_dir
        )
        if selected_dir:
            self.playlist_mgr.channels_dir = selected_dir
            self._show_navigation()
            self.refresh_directory(selected_dir)

    def _on_settings_saved(
        self,
        user_proxy,
        timeout_ms,
        browser_port,
        diagnostics_enabled=False,
        diagnostics_level="error",
        local_playback_mode="smooth",
        live_playback_mode="smooth",
        language="zh_CN",
        clock_show_weekday=True,
        safe_mode=False,
    ):
        old_port = self.server_port
        set_user_proxy(user_proxy, enabled=True)
        set_browser_probe_timeout_ms(timeout_ms)
        set_browser_port(browser_port)
        set_diagnostics_settings(diagnostics_enabled, diagnostics_level)
        set_local_playback_mode(local_playback_mode)
        set_live_playback_mode(live_playback_mode)
        set_language(language)
        set_clock_show_weekday(clock_show_weekday)
        previous_safe_mode = bool(get_compatibility_settings().get("safe_mode", False))
        set_compatibility_safe_mode(safe_mode)
        self.floating_clock.set_show_weekday(clock_show_weekday)
        self._position_floating()
        self.player_panel.apply_language()
        self.server_port = int(browser_port)
        if old_port != self.server_port and self.httpd:
            self.statusBar().showMessage(
                f"设置已保存；浏览器端口已改为 {self.server_port}，重启本地服务后生效"
            )
        elif previous_safe_mode != bool(safe_mode):
            self.statusBar().showMessage("设置已保存；兼容/安全启动模式将在重启后生效")
        else:
            self.statusBar().showMessage("设置已保存")

    def open_m3u_url(self):
        """打开在线资源 URL。"""
        from ui.online_m3u_dialog import OnlineM3uDialog
        from PySide6.QtWidgets import QDialog

        dialog = OnlineM3uDialog(self)
        if dialog.exec() == QDialog.Accepted:
            action, url = dialog.get_result()
            if url:
                if action == 'play':
                    self._open_online_resource(url, save=False)
                elif action == 'save':
                    self._open_online_resource(url, save=True)

    def _online_url_extension(self, url):
        """Return the lowercase extension from an online resource URL path."""
        parsed = urlparse(str(url or "").strip())
        return os.path.splitext(parsed.path or "")[1].lower()

    def _online_resource_name(self, url):
        """Build a readable resource name from a URL."""
        parsed = urlparse(str(url or "").strip())
        name = os.path.basename(parsed.path or "")
        return name or parsed.netloc or "online_resource"

    def _is_online_channel_file_extension(self, extension):
        """Return whether an extension should be handled as a channel resource file."""
        return extension in (CHANNEL_RESOURCE_EXTENSIONS - {".m3u8"})

    def _is_online_media_extension(self, extension):
        """Return whether an extension should be handled as a directly playable media URL."""
        return extension in (LOCAL_MEDIA_EXTENSIONS | {".m3u8", ".mpd"})

    def _guess_online_manifest_type(self, url, content_type=""):
        """Guess the ManifestType for a directly playable online resource."""
        extension = self._online_url_extension(url)
        lower_type = str(content_type or "").lower()
        if extension == ".m3u8" or "mpegurl" in lower_type:
            return "hls"
        if extension == ".mpd" or "dash" in lower_type:
            return "mpd"
        if extension == ".flv" or "flv" in lower_type:
            return "flv"
        if extension in LOCAL_AUDIO_EXTENSIONS or lower_type.startswith("audio/"):
            return "audio"
        if extension in LOCAL_GIF_EXTENSIONS or "gif" in lower_type:
            return "gif"
        if extension in LOCAL_IMAGE_EXTENSIONS or lower_type.startswith("image/"):
            return "image"
        if extension in LOCAL_VIDEO_EXTENSIONS or lower_type.startswith("video/"):
            return "mp4"
        return "online"

    def _looks_like_online_channel_file(self, url, content_type="", body_text=""):
        """Return whether the response appears to be a channel resource file."""
        extension = self._online_url_extension(url)
        if self._looks_like_hls_media_playlist(content_type, body_text):
            return False
        if self._is_online_channel_file_extension(extension):
            return True
        lower_type = str(content_type or "").lower()
        sample = str(body_text or "").lstrip()
        sample_lower = sample[:4096].lower()
        non_empty_lines = [line.strip() for line in sample.splitlines() if line.strip()]
        if len(non_empty_lines) == 1 and self._extract_online_media_url(sample, url):
            return False
        if "mpegurl" in lower_type and "#extinf" in sample_lower:
            return True
        if "json" in lower_type and any(token in sample_lower for token in ("manifest", "channels", "streams", "url")):
            return True
        if lower_type.startswith("text/") and any(token in sample_lower for token in ("#extinf", "group-title", "manifest", "http://", "https://")):
            return True
        return sample.startswith("#EXTM3U") and "#EXTINF" in sample

    def _looks_like_hls_media_playlist(self, content_type="", body_text=""):
        """Return whether text is an HLS media playlist rather than a channel list."""
        lower_type = str(content_type or "").lower()
        sample = str(body_text or "").lstrip()
        sample_lower = sample[:8192].lower()
        hls_markers = (
            "#ext-x-targetduration",
            "#ext-x-media-sequence",
            "#ext-x-stream-inf",
            "#ext-x-playlist-type",
            "#ext-x-map",
            "#ext-x-endlist",
            "#ext-x-version",
        )
        if any(marker in sample_lower for marker in hls_markers):
            return True
        return "mpegurl" in lower_type and sample.startswith("#EXTM3U") and "group-title" not in sample_lower

    def _extract_online_media_url(self, body_text="", base_url=""):
        """Extract a directly playable media URL from a small text response."""
        text = str(body_text or "").strip()
        if not text:
            return ""
        candidates: list[str] = []
        lines = [line.strip().strip("'\"") for line in text.splitlines() if line.strip()]
        if len(lines) == 1 and lines[0].startswith(("http://", "https://")):
            candidates.append(lines[0])
        candidates.extend(re.findall(r"https?://[^\s'\"<>]+", text))

        for candidate in candidates:
            cleaned = candidate.rstrip("),;]")
            extension = self._online_url_extension(cleaned)
            if self._is_online_media_extension(extension):
                return cleaned
        return ""

    def _is_online_direct_media_response(self, url, content_type="", body_text=""):
        """Return whether a response should be played directly as online media."""
        extension = self._online_url_extension(url)
        lower_type = str(content_type or "").lower()
        return (
            self._is_online_media_extension(extension)
            or self._looks_like_hls_media_playlist(content_type, body_text)
            or lower_type.startswith(("video/", "audio/", "image/"))
            or "dash+xml" in lower_type
            or "mpegurl" in lower_type
        )

    def _online_request_headers(self):
        """Return browser-like headers for online resource downloads."""
        return {
            "User-Agent": DEFAULT_BROWSER_USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
        }

    def _show_online_resource_message(self, message, timeout=0, busy=False):
        """Show online-resource progress and flush the event loop once."""
        self.statusBar().showMessage(message, timeout)
        if busy:
            if self._online_progress_dialog is None:
                dialog = OnlineResourceProgressDialog(self)
                self._online_progress_dialog = dialog
            self._online_progress_dialog.set_message(message)
            self._online_progress_dialog.show()
            self._online_progress_dialog.raise_()
        QApplication.processEvents()

    def _finish_online_resource_progress(self):
        """Close the online-resource busy dialog if it is visible."""
        dialog = self._online_progress_dialog
        self._online_progress_dialog = None
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()
            QApplication.processEvents()

    def _download_online_resource(self, url):
        """Download an online resource while allowing invalid HTTPS certificates."""
        import requests
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(
            url,
            timeout=20,
            verify=False,
            headers=self._online_request_headers(),
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        return response

    def _probe_online_resource(self, url):
        """Probe an online URL without downloading large media bodies."""
        import requests
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        headers = self._online_request_headers()
        headers["Range"] = "bytes=0-4095"
        response = requests.get(
            url,
            timeout=12,
            verify=False,
            headers=headers,
            stream=True,
        )
        response.raise_for_status()
        body = b""
        try:
            body = next(response.iter_content(4096), b"") or b""
        finally:
            response.close()
        encoding = response.encoding or response.apparent_encoding or "utf-8"
        try:
            text = body.decode(encoding, errors="replace")
        except Exception:
            text = body.decode("utf-8", errors="replace")
        return {
            "content_type": response.headers.get("Content-Type", ""),
            "body_text": text,
            "final_url": response.url or url,
            "status_code": response.status_code,
        }

    def _save_online_channel_file_response(self, url, response):
        """Save a downloaded online channel resource and return the local path."""
        extension = self._online_url_extension(url)
        if not extension or extension not in CHANNEL_RESOURCE_EXTENSIONS:
            extension = ".m3u"
        default_name = os.path.splitext(self._online_resource_name(url))[0] or "online_resource"
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存在线资源文件",
            os.path.join(self.playlist_mgr.channels_dir, f"{default_name}{extension}"),
            "频道资源 (*.m3u *.m3u8 *.txt *.cfg *.json);;所有文件 (*.*)",
        )
        if not save_path:
            return ""
        with open(save_path, "w", encoding="utf-8") as handle:
            handle.write(response.text)
        return save_path

    def _save_online_media_descriptor(self, url, content_type=""):
        """Save a directly playable online media URL as a reusable JSON resource."""
        name = self._online_resource_name(url)
        base_name = os.path.splitext(name)[0] or "online_media"
        channel = {
            "Name": name,
            "Category": "在线资源",
            "Manifest": url,
            "ManifestType": self._guess_online_manifest_type(url, content_type),
            "UseLocalProxy": False,
        }
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存在线媒体资源",
            os.path.join(self.playlist_mgr.channels_dir, f"{base_name}.json"),
            "JSON 资源 (*.json);;所有文件 (*.*)",
        )
        if not save_path:
            return "", {}
        with open(save_path, "w", encoding="utf-8") as handle:
            json.dump({"Channels": [channel]}, handle, ensure_ascii=False, indent=2)
        return save_path, channel

    def _play_online_media_url(self, url, content_type="", saved_path=""):
        """Play an online video/audio/image/GIF URL directly."""
        name = self._online_resource_name(url)
        channel = {
            "Name": name,
            "Category": "在线资源",
            "Manifest": url,
            "ManifestType": self._guess_online_manifest_type(url, content_type),
            "_IsOnlineMedia": True,
        }
        self.nav_overlay.hide_with_animation()
        if saved_path:
            self.load_config(saved_path)
        self.play_channel(
            channel,
            queue_kind="online_resource",
            queue_key=url,
            queue_source=saved_path or url,
        )

    def _load_online_channel_resource_file(self, path, url, save=False, final_url=""):
        """Load an online channel resource file and report empty/invalid results."""
        loaded = self.load_config(path)
        if not loaded:
            self._show_online_resource_message("在线资源加载失败", 3000)
            return False

        channel_count = len(self.playlist_mgr.streams)
        if channel_count <= 0:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as handle:
                    body_text = handle.read(8192)
            except OSError:
                body_text = ""
            media_url = self._extract_online_media_url(body_text, final_url or url)
            if media_url or self._looks_like_hls_media_playlist("", body_text):
                target_url = media_url or final_url or url
                content_type = "" if media_url else "application/vnd.apple.mpegurl"
                self._play_online_media_url(target_url, content_type)
                self._show_online_resource_message(f"正在打开在线媒体：{self._online_resource_name(target_url)}", 3000)
                return True
            message_dialogs.warning(
                self,
                "未解析到频道",
                "在线资源已下载，但没有解析出任何频道信息。\n\n"
                "可能原因：\n"
                "1. 该地址不是频道资源文件；\n"
                "2. 文件格式不受支持或内容为空；\n"
                "3. 源站返回了错误页面、鉴权页面或过期内容。\n\n"
                f"URL：{url}",
            )
            self._show_online_resource_message("在线资源未解析到频道", 5000)
            return False

        self.current_m3u_url = url
        action_text = "已保存并加载" if save else "已加载"
        self._show_online_resource_message(
            f"{action_text}在线资源（{channel_count} 个频道）",
            5000,
        )
        self.nav_overlay.hide_with_animation()
        QTimer.singleShot(350, self._show_channel_list)
        return True

    def _open_online_resource(self, url, save=False):
        """Open or save an online channel file or directly playable media URL."""
        import tempfile

        url = str(url or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            message_dialogs.warning(self, "无法打开在线资源", "请输入有效的 http 或 https 地址")
            return

        try:
            extension = self._online_url_extension(url)
            content_type = ""
            body_text = ""

            if self._is_online_media_extension(extension):
                if save:
                    saved_path, _channel = self._save_online_media_descriptor(url)
                    if not saved_path:
                        self._show_online_resource_message("已取消", 2000)
                        return
                    self._play_online_media_url(url, saved_path=saved_path)
                    self._show_online_resource_message(f"已保存并打开在线媒体：{os.path.basename(saved_path)}", 5000)
                else:
                    self._play_online_media_url(url)
                    self._show_online_resource_message(f"正在打开在线媒体：{self._online_resource_name(url)}", 3000)
                return

            if not self._is_online_channel_file_extension(extension):
                self._show_online_resource_message(f"正在探测在线资源：{url}...", busy=True)
                probe = self._probe_online_resource(url)
                self._finish_online_resource_progress()
                content_type = probe.get("content_type", "")
                body_text = probe.get("body_text", "")
                final_url = probe.get("final_url") or url
                media_url = self._extract_online_media_url(body_text, final_url)
                if not self._looks_like_online_channel_file(final_url, content_type, body_text):
                    target_url = media_url or final_url
                    if save:
                        saved_path, _channel = self._save_online_media_descriptor(target_url, content_type)
                        if not saved_path:
                            self._show_online_resource_message("已取消", 2000)
                            return
                        self._play_online_media_url(target_url, content_type, saved_path=saved_path)
                        self._show_online_resource_message(f"已保存并打开在线媒体：{os.path.basename(saved_path)}", 5000)
                    else:
                        self._play_online_media_url(target_url, content_type)
                        self._show_online_resource_message(f"正在打开在线媒体：{self._online_resource_name(target_url)}", 3000)
                    return

            self._show_online_resource_message(f"正在下载在线资源：{url}...", busy=True)
            response = self._download_online_resource(url)
            self._finish_online_resource_progress()
            response_content_type = response.headers.get("Content-Type", "")
            response_text = response.text
            final_url = response.url or url
            media_url = self._extract_online_media_url(response_text, final_url)
            if not self._looks_like_online_channel_file(final_url, response_content_type, response_text):
                target_url = media_url or final_url
                if save:
                    saved_path, _channel = self._save_online_media_descriptor(target_url, response_content_type)
                    if not saved_path:
                        self._show_online_resource_message("已取消", 2000)
                        return
                    self._play_online_media_url(target_url, response_content_type, saved_path=saved_path)
                    self._show_online_resource_message(f"已保存并打开在线媒体：{os.path.basename(saved_path)}", 5000)
                else:
                    self._play_online_media_url(target_url, response_content_type)
                    self._show_online_resource_message(f"正在打开在线媒体：{self._online_resource_name(target_url)}", 3000)
                return

            if save:
                temp_path = self._save_online_channel_file_response(url, response)
                if not temp_path:
                    self._show_online_resource_message("已取消", 2000)
                    return
            else:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=self._online_url_extension(url) or ".m3u",
                    delete=False,
                    encoding="utf-8",
                ) as handle:
                    handle.write(response_text)
                    temp_path = handle.name

            self._load_online_channel_resource_file(temp_path, url, save=save, final_url=final_url)

        except Exception as e:
            self._finish_online_resource_progress()
            try:
                import requests
            except Exception:
                requests = None
            if requests is not None and isinstance(e, requests.Timeout):
                message_dialogs.critical(
                    self,
                    "加载失败",
                    "下载超时，请检查网络连接或稍后重试"
                )
                self._show_online_resource_message("下载超时", 3000)
                return
            if requests is not None and isinstance(e, requests.HTTPError):
                message_dialogs.critical(
                    self,
                    "加载失败",
                    f"HTTP 错误 {e.response.status_code}：{e.response.reason}"
                )
                self._show_online_resource_message("下载失败", 3000)
                return
            if requests is not None and isinstance(e, requests.RequestException):
                message_dialogs.critical(
                    self,
                    "加载失败",
                    f"网络错误：{str(e)}"
                )
                self._show_online_resource_message("下载失败", 3000)
                return
            message_dialogs.critical(
                self,
                "加载失败",
                f"加载失败：{str(e)}"
            )
            self._show_online_resource_message("加载失败", 3000)
        finally:
            self._finish_online_resource_progress()

    def _on_file_selected(self, path, queue_kind="resource_files", queue_key=None):
        """文件被选中后的处理：频道资源加载列表，本地媒体直接播放。"""
        if path and os.path.isfile(path):
            # 先隐藏导航面板
            self.nav_overlay.hide_with_animation()

            if is_local_media(path):
                self._play_local_media_file(path, queue_kind=queue_kind, queue_key=queue_key)
                return

            if not is_channel_resource(path):
                message_dialogs.warning(self, "无法打开资源", f"暂不支持该资源类型：{os.path.basename(path)}")
                return

            if str(queue_kind or "").startswith("resource_"):
                self._set_playback_queue_context(
                    queue_kind,
                    queue_key or self._resource_queue_key(path),
                    path,
                )
            # 加载配置文件
            self.load_config(path)
            # 延迟显示频道列表，等待导航面板滑出动画完成（300ms 动画 + 50ms 缓冲）
            from PySide6.QtCore import QTimer
            QTimer.singleShot(350, self._show_channel_list)

    def _play_local_media_file(self, path, queue_kind="resource_files", queue_key=None, queue_source=None):
        abs_path = os.path.abspath(path)
        type_label = resource_type_label(abs_path)
        channel = {
            "Name": os.path.basename(abs_path),
            "Category": f"本地{type_label}",
            "Manifest": abs_path,
            "ManifestType": "local",
            "_IsLocalMedia": True,
        }
        self.statusBar().showMessage(f"正在打开本地媒体：{os.path.basename(abs_path)}")
        self.play_channel(
            channel,
            queue_kind=queue_kind,
            queue_key=queue_key or self._resource_queue_key(abs_path),
            queue_source=queue_source,
        )

    def load_config(self, filepath):
        self.discovered_epg_urls = []
        success, err = self.playlist_mgr.load_file(filepath, on_epg_found=self._on_epg_url_discovered)

        if not success:
            message_dialogs.critical(self, "加载失败", f"无法加载文件：{err}")
            return False

        self.current_config_path = filepath
        self.is_dirty = False

        # 清除缓存
        self._frontend_channels_cache = None
        self._browser_cache = None

        self._annotate_channel_favorites()
        self.player_panel.set_channels(self.playlist_mgr.streams)
        self.channel_list_overlay.set_channels(
            self.playlist_mgr.streams,
            source_name=getattr(self.playlist_mgr, "current_file_base_name", "") or os.path.splitext(os.path.basename(filepath))[0],
        )
        self._refresh_favorites_views()
        self.nav_overlay.update_info(
            dir_path=self.playlist_mgr.channels_dir,
            file_count=len(self.cfg_files_cache),
        )

        channel_count = len(self.playlist_mgr.streams)
        self.statusBar().showMessage(f"已加载 {channel_count} 个频道 - {os.path.basename(filepath)}")

        # 自动重新生成 live.html，确保浏览器刷新时显示最新频道
        self._regenerate_live_html()

        if self.discovered_epg_urls and not self._fallback_dialog_open:
            self._prompt_auto_download_epg()
        return True

    def _on_epg_url_discovered(self, url):
        if url and url not in self.discovered_epg_urls:
            self.discovered_epg_urls.append(url)

    def _prompt_auto_download_epg(self):
        if self._fallback_dialog_open:
            return

        self._fallback_dialog_open = True
        reply = message_dialogs.question(
            self,
            "发现节目单",
            f"检测到 {len(self.discovered_epg_urls)} 个节目单地址，是否自动下载？",
            QMessageBox.Yes | QMessageBox.No
        )
        self._fallback_dialog_open = False

        if reply == QMessageBox.Yes:
            for url in self.discovered_epg_urls:
                self.epg_manager.download_epg(
                    url,
                    auto=True,
                    on_success=lambda path, skipped: self.epg_download_success_signal.emit(path, skipped),
                    on_error=lambda err: self.epg_download_error_signal.emit(err)
                )

    def save_current_config(self):
        if not self.current_config_path:
            message_dialogs.warning(self, "保存", "没有打开的配置文件")
            return

        try:
            epg_url = self.discovered_epg_urls[0] if self.discovered_epg_urls else ""
            self.playlist_mgr.save_file(self.current_config_path, epg_url=epg_url)
            self.is_dirty = False
            self.statusBar().showMessage(f"已保存 - {os.path.basename(self.current_config_path)}")
        except Exception as e:
            message_dialogs.critical(self, "保存失败", str(e))

    def play_channel(self, channel, queue_kind=None, queue_key=None, queue_source=None):
        if not channel:
            return

        if queue_kind is None:
            queue_kind = "resource_files" if is_local_media_channel(channel) else "channel_list"
        if queue_key is None:
            if queue_kind in {"channel_list", "channel_favorites"}:
                queue_key = self._channel_queue_key(channel)
            elif queue_kind in {"resource_files", "resource_favorites"}:
                queue_key = self._resource_queue_key(channel.get("Manifest") or "")
        self._set_playback_queue_context(queue_kind, queue_key or "", queue_source or channel.get("Name") or "")

        existing_trace_id = channel.get("_TraceId")
        self._current_trace_id = str(existing_trace_id or new_trace_id())
        channel["_TraceId"] = self._current_trace_id
        self.current_channel = channel
        self._apply_fullscreen_overlay_policy()
        log_event(
            "playback.start",
            "info",
            trace_id=self._current_trace_id,
            channel=channel,
            config_path=self.current_config_path,
        )
        if self.detail_overlay.isVisible():
            self.detail_overlay.set_channel(channel)
        self.player_panel.play_channel(channel)

        # 清除浏览器缓存（频道可能改变）
        self._browser_cache = None

    def play_selected_channel(self):
        channel = self.player_panel.get_selected_channel()
        if channel:
            self.play_channel(channel)

    def _play_relative_channel(self, step):
        """按当前播放来源切换上/下一个项目（越界回绕）。"""
        self._play_adjacent_item(step)

    def _play_prev_channel(self):
        self._play_relative_channel(-1)

    def _play_next_channel(self):
        self._play_relative_channel(1)

    def _retry_current_channel(self):
        channel = self.current_channel
        if not channel:
            return
        try:
            self.player_panel.play_channel(channel, _reload=True)
        except TypeError:
            self.play_channel(channel)

    def stop_playback(self):
        self.player_panel.stop_playback()
        self._apply_fullscreen_overlay_policy()

    def _show_probe_retry_dialog(self, name, format_name, kind, code, detail, error_info=None):
        error_info = dict(error_info or {})
        error_info.update({
            "kind": kind,
            "code": code,
            "detail": detail,
            "name": name,
            "failure_stage": error_info.get("failure_stage") or "probe",
            "failure_action": error_info.get("failure_action") or "browser-probe",
            "trace_id": error_info.get("trace_id") or self._current_trace_id,
        })
        failure = classify_failure(error_info)
        dialog = message_dialogs.create_message_box(self, "")
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle("播放失败")
        dialog.setText(f"{failure['title']}：{name}")
        dialog.setInformativeText(
            f"协议：{format_name}\n"
            f"类型：{kind or 'unknown'}\n"
            f"代码：{code or 'unknown'}\n\n"
            f"原因：{failure['summary']}\n"
            f"建议：{failure['suggestion']}\n\n"
            f"错误详情：{detail or '未能探测到可播放地址'}\n\n"
            f"是否重试探测，或改用浏览器播放？"
        )
        dialog.setDetailedText(format_failure_details(error_info))
        retry_button = dialog.addButton("重试探测", QMessageBox.AcceptRole)
        default_button = dialog.addButton("默认浏览器播放", QMessageBox.ActionRole)
        choose_button = dialog.addButton("选择浏览器播放", QMessageBox.ActionRole)
        dialog.addButton("取消播放", QMessageBox.RejectRole)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked == retry_button:
            self._try_browser_probe()
        elif clicked == default_button:
            self.open_browser_player()
        elif clicked == choose_button:
            self.open_browser_player_with_choice()

    def _show_next_channel_dialog(self, name, format_name, code, detail, http_status, error_info=None):
        error_info = dict(error_info or {})
        error_info.update({
            "kind": "mpv",
            "code": code,
            "detail": detail,
            "name": name,
            "http_status": http_status,
            "failure_action": error_info.get("failure_action") or "next-channel",
            "trace_id": error_info.get("trace_id") or self._current_trace_id,
        })
        failure = classify_failure(error_info)
        detail_text = detail or "直播链接当前不可用"
        if http_status in {404, 410, 451}:
            detail_text = detail or "直播链接已不存在或不可访问"
        elif http_status == 400:
            detail_text = detail or "直播链接请求无效，可能已失效或签名过期"
        elif http_status in {500, 502, 503, 504}:
            detail_text = detail or "直播源服务器当前异常"

        dialog = message_dialogs.create_message_box(self, "")
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle("播放失败")
        dialog.setText(f"{failure['title']}：{name}")
        dialog.setInformativeText(
            f"协议：{format_name}\n"
            f"代码：{code or 'unknown'}\n"
            f"HTTP：{http_status or 'unknown'}\n\n"
            f"原因：{failure['summary']}\n"
            f"建议：{failure['suggestion']}\n\n"
            f"错误详情：{detail_text}\n\n"
            f"是否播放下一个频道？"
        )
        dialog.setDetailedText(format_failure_details(error_info))
        next_button = dialog.addButton("播放下一个", QMessageBox.AcceptRole)
        retry_button = dialog.addButton("重试当前", QMessageBox.ActionRole)
        dialog.addButton("取消播放", QMessageBox.RejectRole)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked == next_button:
            self._play_next_channel()
        elif clicked == retry_button:
            self._retry_current_channel()

    def configure_browser_probe_dialog(self):
        current_timeout_ms = get_browser_probe_timeout_ms()
        current_timeout_seconds = max(1, current_timeout_ms // 1000)
        value, ok = input_dialogs.get_int(
            self,
            "探测超时",
            "浏览器探测超时（秒）：",
            current_timeout_seconds,
            3,
            120,
        )
        if not ok:
            return
        timeout_ms = int(value) * 1000
        set_browser_probe_timeout_ms(timeout_ms)
        self.statusBar().showMessage(f"浏览器探测超时已设置为 {value}s")

    def _retry_expired_resolved_media(self, error_info):
        """解析出的临时媒体地址失败时，回到原始页面强制重新解析一次。"""
        code_text = str(error_info.get("code") or "")
        retryable_failure = (
            code_text == "idle-active"
            or code_text == "source-dead"
            or code_text.startswith("http-")
        )
        if not retryable_failure:
            return False

        current = dict(self.current_channel or {})
        if current.get("_TokenRefreshRetried"):
            return False

        failed_url = str(error_info.get("url") or "").strip()
        resolved_info = error_info.get("resolved_info") or {}
        source_url = (
            str(error_info.get("source_url") or "").strip()
            or str(resolved_info.get("final_url") or "").strip()
            or str(current.get("_ResolvedSourceUrl") or "").strip()
            or str(current.get("_OriginalManifest") or "").strip()
        )
        if not source_url or not failed_url or source_url == failed_url:
            return False
        if _looks_like_direct_media_url(source_url):
            return False

        retry_channel = dict(current)
        retry_channel["Manifest"] = source_url
        retry_channel["_TokenRefreshRetried"] = True
        retry_channel.pop("_ResolvedInfo", None)
        retry_channel.pop("_BrowserProbeResult", None)
        retry_channel.pop("_ResolvedSourceUrl", None)

        trace_id = self._current_trace_id or str(retry_channel.get("_TraceId") or new_trace_id())
        self._current_trace_id = trace_id
        retry_channel["_TraceId"] = trace_id
        self.current_channel = retry_channel
        if self.detail_overlay.isVisible():
            self.detail_overlay.set_channel(retry_channel)
        log_event(
            "playback.refresh_expired_media",
            "info",
            trace_id=trace_id,
            channel=retry_channel,
            expired_url=failed_url,
            source_url=source_url,
        )
        self.statusBar().showMessage("临时播放地址可能已过期，正在回到原始页面重新解析...")
        try:
            self.player_panel.play_channel(retry_channel, _reload=True)
            return True
        except Exception as exc:
            log_event(
                "playback.refresh_expired_media.failed",
                "error",
                trace_id=trace_id,
                channel=retry_channel,
                error=str(exc),
            )
            self.statusBar().showMessage(f"回源重新解析失败：{exc}")
            return False

    def _on_playback_failed(self, error_info):
        error_info = dict(error_info or {})
        error_info.setdefault("trace_id", self._current_trace_id)
        kind = error_info.get("kind", "unknown")
        code = error_info.get("code", "")
        detail = error_info.get("detail", "")
        name = error_info.get("name", "未知频道")
        url = error_info.get("url", "")
        http_status = error_info.get("http_status")
        failure_action = error_info.get("failure_action", "")
        format_name = self._detect_stream_format_for_ui(self.current_channel or {}, url)
        log_event(
            "playback.failed",
            "error",
            trace_id=self._current_trace_id,
            channel=self.current_channel,
            error=error_info,
            classification=classify_failure(error_info),
        )
        self.player_panel.set_loading(False)
        if self._retry_expired_resolved_media(error_info):
            return

        direct_media_failure = _looks_like_direct_media_url(url)
        should_probe = (
            code == "need-js-probe"
            or (code == "idle-active" and not direct_media_failure)
            or (failure_action == "browser-probe" and not direct_media_failure)
        )
        if should_probe and not self._browser_probe_running:
            if self._try_browser_probe():
                return
            probe_failure = self._last_probe_failure_info or {}
            code = probe_failure.get("code") or "probe-failed"
            detail = probe_failure.get("detail") or detail
            failure_action = "browser-probe"
            error_info.update(
                {
                    "code": code,
                    "detail": detail,
                    "failure_stage": "probe",
                    "failure_action": failure_action,
                    "probe_result": probe_failure.get("result", {}),
                }
            )

        if self._fallback_dialog_open:
            return

        self._fallback_dialog_open = True
        try:
            if failure_action == "local-failed" or (self.current_channel or {}).get("_IsLocalMedia"):
                failure = classify_failure(error_info)
                dialog = message_dialogs.create_message_box(self, "")
                dialog.setIcon(QMessageBox.Warning)
                dialog.setWindowTitle("本地媒体播放失败")
                dialog.setText(f"无法播放本地媒体：{name}")
                dialog.setInformativeText(
                    f"协议：{format_name}\n"
                    f"类型：{kind or 'unknown'}\n"
                    f"代码：{code or 'unknown'}\n\n"
                    f"原因：{failure['summary']}\n"
                    f"建议：请确认文件存在、未被占用，且当前 libmpv 支持该容器和编码。\n\n"
                    f"错误详情：{detail or '未知错误'}"
                )
                dialog.setDetailedText(format_failure_details(error_info, {"format": format_name}))
                dialog.addButton("确定", QMessageBox.AcceptRole)
                dialog.exec()
                return
            if failure_action == "next-channel":
                self._show_next_channel_dialog(name, format_name, code, detail, http_status, error_info)
                return
            if code in {"probe-timeout", "probe-failed"} or failure_action == "browser-probe":
                self._show_probe_retry_dialog(name, format_name, kind, code, detail, error_info)
                return
            failure = classify_failure(error_info)
            dialog = message_dialogs.create_message_box(self, "")
            dialog.setIcon(QMessageBox.Warning)
            dialog.setWindowTitle("播放失败")
            dialog.setText(f"{failure['title']}：{name}")
            dialog.setInformativeText(
                f"协议：{format_name}\n"
                f"类型：{kind or 'unknown'}\n"
                f"代码：{code or 'unknown'}\n\n"
                f"阶段：{failure['stage_label']}\n"
                f"原因：{failure['summary']}\n"
                f"建议：{failure['suggestion']}\n\n"
                f"错误详情：{detail or '未知错误'}\n\n"
                f"是否改用浏览器播放？"
            )
            dialog.setDetailedText(format_failure_details(error_info, {"format": format_name}))
            default_button = dialog.addButton("使用默认浏览器播放", QMessageBox.AcceptRole)
            choose_button = dialog.addButton("选择浏览器播放", QMessageBox.ActionRole)
            dialog.addButton("放弃播放", QMessageBox.RejectRole)
            dialog.exec()
            clicked = dialog.clickedButton()
            if clicked == default_button:
                self.open_browser_player()
            elif clicked == choose_button:
                self.open_browser_player_with_choice()
        finally:
            self._fallback_dialog_open = False

    def _try_browser_probe(self):
        channel = self.current_channel
        if not channel:
            return False
        if not WEBENGINE_AVAILABLE:
            self.statusBar().showMessage(f"页面探测不可用：{WEBENGINE_ERROR}")
            return False

        timeout_ms = get_browser_probe_timeout_ms()
        self._browser_probe_running = True
        self._last_probe_failure_info = None
        self.player_panel.set_loading(True)
        self.player_panel.loading_label.setText("正在使用受控浏览器探测真实播放地址...")
        trace_id = self._current_trace_id or str(channel.get("_TraceId") or new_trace_id())
        self._current_trace_id = trace_id
        channel["_TraceId"] = trace_id
        log_event(
            "browser_probe.start",
            "info",
            trace_id=trace_id,
            channel=channel,
            timeout_ms=timeout_ms,
        )
        try:
            probe = BrowserProbeSession(self)
            probe.progress.connect(self.player_panel.loading_label.setText)
            result = probe.probe_channel(channel, timeout_ms=timeout_ms)
            if result.get("status") != "ok":
                failure_code = "probe-timeout" if result.get("timed_out") else "probe-failed"
                failure_detail = result.get("message") or "browser probe did not resolve a playable media url"
                details = {
                    "message": failure_detail,
                    "snapshot": result.get("snapshot", {}),
                    "console": result.get("console", []),
                    "requests": result.get("requests", []),
                    "candidates": result.get("candidates", []),
                }
                self._last_probe_failure_info = {
                    "code": failure_code,
                    "detail": failure_detail,
                    "result": dict(result),
                }
                log_event(
                    "browser_probe.failed",
                    "error",
                    trace_id=trace_id,
                    channel=channel,
                    code=failure_code,
                    detail=failure_detail,
                    details=details,
                )
                self.statusBar().showMessage("页面探测未获取到真实播放地址")
                self.player_panel.set_loading(False)
                return False

            patched_channel = dict(channel)
            patched_channel["_TraceId"] = trace_id
            patched_channel["Manifest"] = clean_media_url(result.get("media_url") or channel.get("Manifest") or "")
            media_type = str(result.get("media_type") or "").strip().lower()
            if media_type == "dash":
                patched_channel["ManifestType"] = "mpd"
            elif media_type:
                patched_channel["ManifestType"] = media_type
            page_url = (
                result.get("page_url")
                or (result.get("snapshot") or {}).get("url")
                or channel.get("Manifest")
                or ""
            )
            media_url = patched_channel.get("Manifest") or ""
            page_origin = _url_origin(page_url)
            if page_url:
                patched_channel["_OriginalManifest"] = str(channel.get("Manifest") or "").strip()
                patched_channel["_ResolvedSourceUrl"] = page_url
            referer = _browser_like_referer(page_url, media_url)
            if referer and not patched_channel.get("Referer"):
                patched_channel["Referer"] = referer
            if not patched_channel.get("UserAgent"):
                patched_channel["UserAgent"] = DEFAULT_BROWSER_USER_AGENT
            headers = dict(patched_channel.get("Headers") or {})
            if page_origin and _url_origin(media_url) and page_origin != _url_origin(media_url):
                headers.setdefault("Origin", page_origin)
                headers.setdefault("Accept", "*/*")
            if headers:
                patched_channel["Headers"] = headers
            patched_channel["_BrowserProbeResult"] = dict(result)

            log_event(
                "browser_probe.success",
                "info",
                trace_id=trace_id,
                channel=patched_channel,
                media_url=patched_channel.get("Manifest", ""),
                media_type=media_type,
                page_url=page_url,
                result=result,
            )
            self._last_probe_failure_info = None
            self.statusBar().showMessage("页面探测成功，已切回 libmpv 播放")
            self.play_channel(patched_channel)
            return True
        except Exception as exc:
            log_event(
                "browser_probe.exception",
                "error",
                trace_id=trace_id,
                channel=channel,
                error=str(exc),
            )
            self.statusBar().showMessage(f"页面探测失败：{exc}")
            self.player_panel.set_loading(False)
            return False
        finally:
            self._browser_probe_running = False

    def _detect_stream_format_for_ui(self, channel, url):
        manifest_type = str(channel.get("ManifestType") or "").strip().lower()
        if manifest_type:
            if manifest_type == "local":
                return "LOCAL"
            if "dash" in manifest_type or "mpd" in manifest_type:
                return "MPD/DASH"
            if "hls" in manifest_type or "m3u8" in manifest_type:
                return "HLS/M3U8"
            if manifest_type == "mp4":
                return "MP4"
            if manifest_type == "flv":
                return "FLV"
            if manifest_type == "rtsp":
                return "RTSP"
            if manifest_type == "rtmp":
                return "RTMP"
            return manifest_type.upper()

        lower_url = (url or "").lower()
        if ".mpd" in lower_url or "manifest?" in lower_url or "dash" in lower_url:
            return "MPD/DASH"
        if ".m3u8" in lower_url or "hls" in lower_url:
            return "HLS/M3U8"
        if ".mp4" in lower_url or ".m4v" in lower_url or ".mov" in lower_url:
            return "MP4"
        if ".flv" in lower_url:
            return "FLV"
        if lower_url.startswith("rtsp://"):
            return "RTSP"
        if lower_url.startswith("rtmp://"):
            return "RTMP"
        return "UNKNOWN"

    def configure_proxy_dialog(self):
        from utils.proxy_settings import set_user_proxy

        system_proxy = get_system_proxy()
        user_proxy = get_user_proxy()
        effective_proxy, source = get_effective_proxy(self.current_channel or {})

        text, ok = input_dialogs.get_text(
            self,
            "代理设置",
            "用户代理地址（系统代理存在时将优先生效）：",
            text=user_proxy,
        )
        if not ok:
            return

        set_user_proxy(text.strip(), enabled=True)
        effective_proxy, source = get_effective_proxy(self.current_channel or {})
        display_proxy = effective_proxy or "直连"
        display_source = {
            "system": "系统代理",
            "user": "用户代理",
            "channel": "频道代理",
            "direct": "直连",
        }.get(source, source)
        system_text = system_proxy or "无"
        message_dialogs.information(
            self,
            "代理设置",
            f"系统代理：{system_text}\n当前生效：{display_proxy}\n来源：{display_source}",
        )

    def add_channel(self):
        default_category = ""
        if self.playlist_mgr.streams:
            default_category = self.playlist_mgr.streams[0].get("Category", "")

        dialog = ChannelEditorDialog(None, default_category, self)
        if dialog.exec():
            new_channel = dialog.get_channel_data()
            self.playlist_mgr.streams.append(new_channel)
            self.is_dirty = True

            # 清除缓存
            self._frontend_channels_cache = None
            self._browser_cache = None

            self._annotate_channel_favorites()
            self.player_panel.set_channels(self.playlist_mgr.streams)
            self.channel_list_overlay.set_channels(self.playlist_mgr.streams)
            self._refresh_favorites_views()
            self.statusBar().showMessage(f"已添加频道：{new_channel.get('Name', '未命名')}")

    def edit_channel(self):
        channel = self.current_channel
        if not channel:
            message_dialogs.information(self, "编辑", "请先播放或选择一个频道")
            return

        dialog = ChannelEditorDialog(channel, channel.get("Category", ""), self)
        if dialog.exec():
            updated = dialog.get_channel_data()
            channel.update(updated)
            self.is_dirty = True

            # 清除缓存
            self._frontend_channels_cache = None
            self._browser_cache = None

            self.detail_overlay.set_channel(channel)
            self._annotate_channel_favorites()
            self.player_panel.set_channels(self.playlist_mgr.streams)
            self.channel_list_overlay.set_channels(self.playlist_mgr.streams)
            self._refresh_favorites_views()
            self.statusBar().showMessage(f"已更新频道：{channel.get('Name', '未命名')}")

    def delete_channel(self):
        channel = self.current_channel
        if not channel:
            message_dialogs.information(self, "删除", "请先播放或选择一个频道")
            return

        reply = message_dialogs.question(
            self,
            "确认删除",
            f"确定要删除频道 {channel.get('Name', '未命名')} 吗？",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.playlist_mgr.streams.remove(channel)
            self.is_dirty = True
            self.current_channel = None

            # 清除缓存
            self._frontend_channels_cache = None
            self._browser_cache = None

            self.detail_overlay.set_channel(None)
            self._annotate_channel_favorites()
            self.player_panel.set_channels(self.playlist_mgr.streams)
            self.channel_list_overlay.set_channels(self.playlist_mgr.streams)
            self._refresh_favorites_views()
            self.statusBar().showMessage(f"已删除频道：{channel.get('Name', '未命名')}")

    def delete_channel_file(self, file_path):
        """删除资源文件"""
        if not file_path or not os.path.exists(file_path):
            message_dialogs.warning(self, "删除文件", "文件不存在或路径无效")
            return

        # 确认对话框
        file_name = os.path.basename(file_path)
        reply = message_dialogs.question(
            self,
            "确认删除文件",
            f"确定要删除资源文件 \"{file_name}\" 吗？\n\n此操作无法撤销！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No  # 默认选择"否"
        )

        if reply != QMessageBox.Yes:
            return

        # 检查是否是当前加载的文件
        is_current_file = (file_path == self.current_config_path)

        # 如果是当前文件，在删除前找到下一个要加载的文件
        next_file_to_load = None
        if is_current_file and self.cfg_files_cache:
            # 对列表排序（与navigation_panel保持一致）
            sorted_files = sorted(
                [p for p in self.cfg_files_cache if is_channel_resource(p)],
                key=lambda p: os.path.basename(p).lower(),
            )

            try:
                current_index = sorted_files.index(file_path)
                # 尝试获取下一个文件（如果存在）
                if current_index + 1 < len(sorted_files):
                    next_file_to_load = sorted_files[current_index + 1]
                elif current_index > 0:
                    # 如果是最后一个，尝试加载前一个
                    next_file_to_load = sorted_files[current_index - 1]
                # 如果只有一个文件，next_file_to_load 保持为 None
            except ValueError:
                pass

        try:
            # 删除文件
            os.remove(file_path)
            self.statusBar().showMessage(f"已删除文件：{file_name}")

            # 如果删除的是当前文件
            if is_current_file:
                if next_file_to_load and os.path.exists(next_file_to_load):
                    # 先加载下一个文件（这会设置 current_config_path）
                    self.load_config(next_file_to_load)
                    # 然后刷新文件列表（这会根据 current_config_path 高亮）
                    self.refresh_directory(self.playlist_mgr.channels_dir)
                else:
                    # 没有其他文件可加载，清空状态
                    self.playlist_mgr.streams = []
                    self.current_config_path = ""
                    self.current_channel = None
                    self.is_dirty = False
                    self.player_panel.set_channels([])
                    self.channel_list_overlay.set_channels([])
                    self.detail_overlay.set_channel(None)
                    self._refresh_favorites_views()
                    self.player_panel.stop_playback()
                    # 刷新文件列表
                    self.refresh_directory(self.playlist_mgr.channels_dir)
            else:
                # 删除的不是当前文件，只需刷新列表
                self.refresh_directory(self.playlist_mgr.channels_dir)

        except Exception as e:
            message_dialogs.critical(self, "删除失败", f"无法删除文件：{e}")

    def load_local_epg(self):
        self.statusBar().showMessage("正在加载本地节目单...")
        self.epg_manager.load_local_epg(
            on_finish=lambda file_count, channel_count: self.epg_loaded_signal.emit(file_count, channel_count),
            on_error=lambda error: self.epg_load_error_signal.emit(error),
        )

    def _on_epg_loaded(self, file_count, channel_count):
        self.statusBar().showMessage(f"已加载节目单：{file_count} 个文件，{channel_count} 个频道")

    def _on_epg_load_error(self, error):
        self.statusBar().showMessage("节目单加载失败，EPG 信息已临时禁用，播放不受影响", 5000)
        log_event(
            "epg.load_failed",
            "warning",
            error=str(error or ""),
            index_path=getattr(self.epg_manager, "index_db_path", ""),
        )
        if self._epg_load_warning_shown:
            return
        self._epg_load_warning_shown = True
        message_dialogs.warning(
            self,
            "节目单加载失败",
            str(error or "本地节目单索引加载失败，EPG 信息已临时禁用，播放不受影响。"),
        )

    def download_epg_dialog(self):
        url, ok = input_dialogs.get_text(
            self,
            "下载节目单",
            "请输入节目单 URL：",
            text="https://example.com/epg.xml.gz"
        )

        if ok and url.strip():
            self.statusBar().showMessage(f"正在下载节目单...")
            self.epg_manager.download_epg(
                url.strip(),
                auto=False,
                on_success=lambda path, skipped: self.epg_download_success_signal.emit(path, skipped),
                on_error=lambda err: self.epg_download_error_signal.emit(err)
            )

    def _on_epg_download_success(self, path, skipped):
        if skipped:
            self.statusBar().showMessage(f"节目单已存在，跳过下载")
        else:
            self.statusBar().showMessage(f"节目单下载完成：{os.path.basename(path)}")
            self.load_local_epg()

    def _on_epg_download_error(self, error):
        message_dialogs.critical(self, "下载失败", f"节目单下载失败：{error}")
        self.statusBar().showMessage("节目单下载失败")

    def set_port_dialog(self):
        port, ok = input_dialogs.get_int(
            self,
            "设置端口",
            "浏览器播放端口：",
            self.server_port,
            1024,
            65535
        )

        if ok:
            old_port = self.server_port
            self.server_port = port
            set_browser_port(port)
            if hasattr(self, "btn_port"):
                self.btn_port.setText(f"浏览器端口 {self.server_port}")

            if self.httpd:
                self.stop_http_server()
                self.statusBar().showMessage(f"端口已更改：{old_port} → {port}，下次启动生效")
            else:
                self.statusBar().showMessage(f"端口已设置为 {port}")

    def _regenerate_live_html(self):
        """重新生成 live.html（仅在有频道且模板存在时）"""
        if not self.playlist_mgr.streams:
            return

        if not os.path.exists(TEMPLATE_FILE):
            return

        try:
            # 生成频道 JSON
            channels_json_str = json.dumps(self.get_frontend_channels(), ensure_ascii=False, indent=4)

            # 读取模板并替换占位符
            with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
                html_template = f.read()

            final_html = html_template.replace("{{CHANNELS_JSON}}", channels_json_str)

            # 写入最终的 HTML 文件
            with open(BROWSER_HTML_FILE, "w", encoding="utf-8") as f:
                f.write(final_html)
        except Exception as e:
            # 静默失败，不打扰用户
            print(f"重新生成 live.html 失败: {e}")

    def get_browser_html_path(self):
        """Return the generated browser player HTML path."""
        return BROWSER_HTML_FILE

    def _frontend_keys_dict(self, channel):
        keys_dict = {}
        keys_value = (channel or {}).get("Keys") or []
        if isinstance(keys_value, dict):
            for kid, key in keys_value.items():
                kid_text = str(kid).strip()
                key_text = str(key).strip()
                if kid_text and key_text:
                    keys_dict[kid_text] = key_text
            return keys_dict

        if not isinstance(keys_value, list):
            keys_value = []
        for item in keys_value:
            if isinstance(item, str) and ":" in item:
                try:
                    kid, key = item.split(":", 1)
                    kid_text = kid.strip()
                    key_text = key.strip()
                    if kid_text and key_text:
                        keys_dict[kid_text] = key_text
                except Exception:
                    continue
        return keys_dict

    def _channel_to_frontend_payload(self, channel, source_index=None, original_index=None):
        channel = channel or {}
        keys_dict = self._frontend_keys_dict(channel)
        drm_type = "clearkey" if keys_dict else (channel.get("DrmType") or "none")
        payload = {
            "name": channel.get("Name", "未命名"),
            "category": channel.get("Category") or "未分类",
            "mpd": clean_media_url(channel.get("Manifest", "")),
            "logo": channel.get("LogoUrl", ""),
            "tvgId": channel.get("TvgId", ""),
            "tvgName": channel.get("TvgName", ""),
            "drmType": drm_type,
            "licenseUrl": channel.get("LicenseUrl", ""),
            "keys": keys_dict,
            "useProxy": bool(channel.get("UseLocalProxy", False)),
            "proxy": channel.get("Proxy", ""),
            "manifestProxy": channel.get("ManifestProxy", ""),
            "mediaProxy": channel.get("MediaProxy", ""),
            "userAgent": channel.get("UserAgent", ""),
            "referer": channel.get("Referer", ""),
            "headers": channel.get("Headers", {}) or {},
            "manifestType": channel.get("ManifestType", ""),
            "videoTracks": channel.get("VideoTracks", []) or [],
            "audioTracks": channel.get("AudioTracks", []) or [],
            "subtitleTracks": channel.get("SubtitleTracks", []) or [],
            "defaultVideo": channel.get("DefaultVideo", ""),
            "defaultAudio": channel.get("DefaultAudio", ""),
            "defaultSubtitles": channel.get("DefaultSubtitles", ""),
        }
        if source_index is not None:
            payload["sourceIndex"] = int(source_index)
        if original_index is not None:
            payload["originalIndex"] = int(original_index)
        return payload

    def _apply_frontend_resolved_channel(self, channel, resolved):
        applied = dict(channel or {})
        resolved_url = clean_media_url((resolved or {}).get("media_url") or "")
        resolved_type = str((resolved or {}).get("media_type") or "").strip().lower()
        resolved_from = str((resolved or {}).get("resolved_from") or "").strip().lower()

        if resolved_url:
            applied["Manifest"] = resolved_url
        if resolved_type == "dash":
            applied["ManifestType"] = "mpd"
        elif resolved_type:
            applied["ManifestType"] = resolved_type

        if resolved_from in {"html", "script", "api", "redirect"}:
            source_page = clean_media_url(
                channel.get("Manifest") if resolved_from == "redirect" else (resolved or {}).get("final_url")
            )
            if not source_page:
                source_page = clean_media_url(channel.get("Manifest") or "")
            media_url = clean_media_url(applied.get("Manifest") or "")
            applied["_OriginalManifest"] = clean_media_url(channel.get("Manifest") or "")
            applied["_ResolvedSourceUrl"] = source_page
            referer = _browser_like_referer(source_page, media_url)
            resolved_is_direct_media = resolved_from == "redirect" and _is_explicit_http_media_url(media_url)
            if resolved_is_direct_media:
                applied.pop("Referer", None)
                headers = dict(applied.get("Headers") or {})
                for key in list(headers.keys()):
                    if str(key).strip().lower() in {"origin", "referer"}:
                        headers.pop(key, None)
                if headers:
                    applied["Headers"] = headers
                else:
                    applied.pop("Headers", None)
            elif referer and not applied.get("Referer"):
                applied["Referer"] = referer
            if not applied.get("UserAgent"):
                applied["UserAgent"] = DEFAULT_BROWSER_USER_AGENT

            page_origin = _url_origin(source_page)
            media_origin = _url_origin(media_url)
            headers = dict(applied.get("Headers") or {})
            if not resolved_is_direct_media and page_origin and media_origin and page_origin != media_origin:
                headers.setdefault("Origin", page_origin)
                headers.setdefault("Accept", "*/*")
                applied["UseLocalProxy"] = True
            if headers:
                applied["Headers"] = headers

        applied["_ResolvedInfo"] = dict(resolved or {})
        return applied

    def get_frontend_channels(self):
        """为浏览器播放提供频道列表。"""
        frontend_list = []
        for source_index, channel in enumerate(self.playlist_mgr.streams):
            if not channel.get("Manifest", ""):
                continue
            payload = self._channel_to_frontend_payload(
                channel,
                source_index=source_index,
                original_index=len(frontend_list),
            )
            frontend_list.append(payload)
        self._frontend_channels_cache = frontend_list
        return frontend_list

    def resolve_frontend_channel(self, index, force=False):
        """按需解析一个原始频道，并返回浏览器播放器可直接合并的字段。"""
        streams = self.playlist_mgr.streams
        if index < 0 or index >= len(streams):
            return {
                "ok": False,
                "status": "error",
                "message": "channel index out of range",
            }

        channel = streams[index]
        base_payload = self._channel_to_frontend_payload(channel, source_index=index)
        manifest = clean_media_url(channel.get("Manifest") or "")
        if not manifest:
            return {
                "ok": False,
                "status": "error",
                "message": "missing media url",
                "channel": base_payload,
            }

        lower_manifest = manifest.lower()
        if is_local_media_channel(channel) or not lower_manifest.startswith(("http://", "https://")):
            return {
                "ok": True,
                "status": "ok",
                "message": "passthrough",
                "needJsProbe": False,
                "channel": base_payload,
                "resolved": {
                    "status": "ok",
                    "media_url": manifest,
                    "media_type": channel.get("ManifestType") or "unknown",
                    "resolved_from": "passthrough",
                },
            }

        resolved = resolve_channel(channel, force=force)
        status = str(resolved.get("status") or "error")
        ok = status == "ok" and bool(resolved.get("media_url"))
        applied = self._apply_frontend_resolved_channel(channel, resolved) if ok else channel
        payload = self._channel_to_frontend_payload(applied, source_index=index)

        return {
            "ok": ok,
            "status": status,
            "message": resolved.get("message") or "",
            "needJsProbe": bool(resolved.get("need_js_probe")),
            "httpStatus": resolved.get("http_status"),
            "finalUrl": resolved.get("final_url") or "",
            "channel": payload,
            "resolved": resolved,
        }

    def open_browser_player(self):
        """使用默认浏览器打开"""
        self._open_browser_player_internal(None)

    def open_browser_player_with_choice(self):
        """让用户选择浏览器打开"""
        browsers = self._get_installed_browsers()

        if not browsers:
            message_dialogs.information(self, "选择浏览器", "未检测到已安装的浏览器，将使用系统默认浏览器。")
            self._open_browser_player_internal(None)
            return

        # 创建选择对话框
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QPushButton, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle("选择浏览器")
        dialog.setMinimumWidth(400)
        dialog.setMinimumHeight(300)

        layout = QVBoxLayout(dialog)

        label = QLabel("请选择要使用的浏览器：")
        layout.addWidget(label)

        browser_list = QListWidget()
        for name, path in browsers:
            browser_list.addItem(f"{name}")

        browser_list.setCurrentRow(0)
        layout.addWidget(browser_list)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if dialog.exec() == QDialog.Accepted:
            selected_index = browser_list.currentRow()
            if 0 <= selected_index < len(browsers):
                browser_name, browser_path = browsers[selected_index]
                self._open_browser_player_internal(browser_path)

    def _get_installed_browsers(self):
        """获取系统已安装的浏览器"""
        import winreg
        browsers = []

        # 常见浏览器注册表路径
        browser_keys = [
            r"SOFTWARE\Clients\StartMenuInternet",
            r"SOFTWARE\WOW6432Node\Clients\StartMenuInternet",
        ]

        for key_path in browser_keys:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_READ)
                i = 0
                while True:
                    try:
                        browser_name = winreg.EnumKey(key, i)
                        try:
                            # 获取浏览器可执行文件路径
                            browser_key = winreg.OpenKey(key, f"{browser_name}\\shell\\open\\command")
                            exe_path, _ = winreg.QueryValueEx(browser_key, "")
                            # 清理路径（移除引号和参数）
                            exe_path = exe_path.strip('"').split('"')[0]
                            if os.path.exists(exe_path):
                                browsers.append((browser_name, exe_path))
                            winreg.CloseKey(browser_key)
                        except:
                            pass
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except:
                pass

        # 去重
        seen = set()
        unique_browsers = []
        for name, path in browsers:
            if path not in seen:
                seen.add(path)
                unique_browsers.append((name, path))

        return unique_browsers

    def _open_browser_player_internal(self, browser_path=None):
        """内部函数：打开浏览器播放器

        Args:
            browser_path: 浏览器可执行文件路径，None表示使用默认浏览器
        """
        if not self.playlist_mgr.streams:
            message_dialogs.information(self, "浏览器播放", "没有可播放的频道")
            return

        if not os.path.exists(TEMPLATE_FILE):
            message_dialogs.warning(self, "浏览器播放", f"找不到模板文件：{TEMPLATE_FILE}")
            return

        self.start_http_server()

        # 生成频道配置
        channels_json = json.dumps(self.get_frontend_channels(), ensure_ascii=False, indent=4)

        # 读取模板并替换占位符
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            html_template = f.read()

        final_html = html_template.replace("{{CHANNELS_JSON}}", channels_json)

        # 写入 live.html
        with open(BROWSER_HTML_FILE, "w", encoding="utf-8") as f:
            f.write(final_html)

        # 打开浏览器
        url = f"http://localhost:{self.server_port}/{HTML_FILE}"

        try:
            if browser_path:
                # 使用指定浏览器打开
                import subprocess
                subprocess.Popen([browser_path, url])
                self.statusBar().showMessage(f"已使用选定浏览器打开播放器：{url}")
            else:
                # 使用默认浏览器
                webbrowser.open(url)
                self.statusBar().showMessage(f"已在默认浏览器打开播放器：{url}")
        except Exception as e:
            message_dialogs.critical(self, "打开失败", f"无法打开浏览器：{e}")

    def start_http_server(self):
        if self.httpd:
            return

        try:
            self.httpd = ThreadedTCPServer(("", self.server_port), ProxyHTTPRequestHandler)
            self.httpd.app_ref = self

            self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.server_thread.start()

            self.statusBar().showMessage(f"HTTP 服务器已启动：端口 {self.server_port}")
        except Exception as e:
            message_dialogs.critical(self, "服务器启动失败", f"无法启动 HTTP 服务器：{e}")
            self.httpd = None

    def stop_http_server(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
            self.server_thread = None
            self.statusBar().showMessage("HTTP 服务器已停止")

    def closeEvent(self, event):
        if self.is_dirty:
            reply = message_dialogs.question(
                self,
                "未保存的更改",
                "有未保存的更改，是否保存？",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )

            if reply == QMessageBox.Yes:
                self.save_current_config()
                event.accept()
            elif reply == QMessageBox.No:
                event.accept()
            else:
                event.ignore()
                return

        self.player_panel.clear()
        self.stop_http_server()
        event.accept()
