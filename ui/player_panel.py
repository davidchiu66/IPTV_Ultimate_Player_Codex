import ctypes
import threading
import time
from ctypes import POINTER, Structure, Union, byref, c_char_p, c_double, c_int, c_longlong, c_size_t, c_ulonglong, c_void_p, cast
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QEvent, QObject, QPoint, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QApplication,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backend.stream_resolver import resolve_channel
from ui.player_controls import PlayerBottomBar, PlayerTopBar
from utils.diagnostics import get_diagnostics_settings, log_event
from utils.media_types import is_local_media_channel
from utils.playback_settings import get_live_playback_mode, get_local_playback_mode
from utils.compatibility_settings import is_safe_mode_enabled
from utils.proxy_settings import get_effective_proxy
from utils.url_cleaning import clean_media_url
from utils.app_paths import resource_path
from utils.logging_utils import mpv_runtime_log_path


DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def _url_origin(url):
    try:
        parsed = urlparse(str(url or "").strip())
    except Exception:
        return ""
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _is_explicit_http_media_url(url):
    """Return whether an HTTP URL points directly at a media file."""
    lower = str(url or "").strip().lower()
    return lower.startswith(("http://", "https://")) and any(
        token in lower
        for token in (
            ".mp4",
            ".m4v",
            ".mov",
            ".flv",
            ".m3u8",
            ".mpd",
            ".mp3",
            ".aac",
            ".flac",
            ".wav",
            ".m4a",
            ".ogg",
            ".wma",
            ".opus",
            ".gif",
            ".jpg",
            ".jpeg",
            ".png",
            ".bmp",
            ".webp",
            ".tif",
            ".tiff",
        )
    )


class ResolveChannelWorker(QObject):
    """Resolve a live channel in a worker thread."""

    progress = Signal(int, str)
    finished = Signal(int, dict)

    def __init__(self, request_id, channel, force=False, parent=None):
        super().__init__(parent)
        self.request_id = int(request_id)
        self.channel = dict(channel or {})
        self.force = bool(force)
        self._cancelled = False

    def cancel(self):
        """Mark this resolve task as cancelled."""
        self._cancelled = True

    def is_cancelled(self):
        """Return whether this task has been cancelled."""
        return bool(self._cancelled)

    def _emit_progress(self, text):
        if not self.is_cancelled():
            self.progress.emit(self.request_id, text)

    def run(self):
        """Run the blocking resolver and emit the result."""
        try:
            result = resolve_channel(
                self.channel,
                force=self.force,
                progress_callback=self._emit_progress,
                cancel_callback=self.is_cancelled,
            )
        except Exception as exc:
            result = {
                "status": "error",
                "message": str(exc) or "直播解析失败",
                "media_url": "",
                "media_type": "unknown",
                "final_url": self.channel.get("Manifest", ""),
                "need_js_probe": False,
                "resolved_from": "",
                "candidates": [],
            }
        self.finished.emit(self.request_id, result)

MPV_RENDERER_OPTION_SETS = [
    {
        "name": "gpu-d3d11",
        "vo": "gpu",
        "gpu-api": "d3d11",
        "gpu-context": "d3d11",
        "hwdec": "auto-safe",
        "keep-open": "yes",
        "idle": "yes",
    },
    {
        "name": "gpu-next-d3d11",
        "vo": "gpu-next",
        "gpu-api": "d3d11",
        "gpu-context": "d3d11",
        "hwdec": "auto-safe",
        "keep-open": "yes",
        "idle": "yes",
    },
    {
        "name": "gpu-basic",
        "vo": "gpu",
        "hwdec": "auto-safe",
        "keep-open": "yes",
        "idle": "yes",
    },
    {
        "name": "direct3d-fallback",
        "vo": "direct3d",
        "keep-open": "yes",
        "idle": "yes",
    },
    {
        "name": "default-fallback",
        "keep-open": "yes",
        "idle": "yes",
    },
]

LOCAL_MPV_RENDERER_OPTION_SETS = [
    {
        "name": "local-gpu-opengl-software",
        "vo": "gpu",
        "gpu-api": "opengl",
        "gpu-context": "win",
        "hwdec": "no",
        "keep-open": "yes",
        "idle": "yes",
    },
    {
        "name": "local-gpu-basic-software",
        "vo": "gpu",
        "hwdec": "no",
        "keep-open": "yes",
        "idle": "yes",
    },
    {
        "name": "local-gpu-d3d11-copy",
        "vo": "gpu",
        "gpu-api": "d3d11",
        "gpu-context": "d3d11",
        "hwdec": "d3d11va-copy",
        "keep-open": "yes",
        "idle": "yes",
    },
    {
        "name": "local-gpu-basic-copy",
        "vo": "gpu",
        "hwdec": "auto-copy",
        "keep-open": "yes",
        "idle": "yes",
    },
    {
        "name": "local-direct3d-nohwdec",
        "vo": "direct3d",
        "hwdec": "no",
        "keep-open": "yes",
        "idle": "yes",
    },
    {
        "name": "local-gpu-d3d11-native",
        "vo": "gpu",
        "gpu-api": "d3d11",
        "gpu-context": "d3d11",
        "gpu-hwdec-interop": "d3d11va",
        "hwdec": "d3d11va",
        "keep-open": "yes",
        "idle": "yes",
    },
]

SAFE_MPV_RENDERER_OPTION_SETS = [
    {
        "name": "safe-direct3d-nohwdec",
        "vo": "direct3d",
        "hwdec": "no",
        "keep-open": "yes",
        "idle": "yes",
    },
    {
        "name": "safe-gpu-nohwdec",
        "vo": "gpu",
        "hwdec": "no",
        "keep-open": "yes",
        "idle": "yes",
    },
    {
        "name": "safe-default-nohwdec",
        "hwdec": "no",
        "keep-open": "yes",
        "idle": "yes",
    },
]

MPV_PLAYBACK_POLICIES = {
    "local_smooth": {
        "name": "local-4k-software-stable",
        "options": {
            "profile": "fast",
            "hwdec": "no",
            "cache": "auto",
            "cache-secs": "30",
            "demuxer-max-bytes": "384MiB",
            "demuxer-max-back-bytes": "128MiB",
            "vd-lavc-dr": "no",
            "scale": "bilinear",
            "cscale": "bilinear",
            "dscale": "bilinear",
            "correct-downscaling": "no",
            "sigmoid-upscaling": "no",
            "deband": "no",
            "interpolation": "no",
            "video-sync": "audio",
            "framedrop": "vo",
            "vd-lavc-threads": "0",
        },
    },
    "local_compat": {
        "name": "local-compat-safe",
        "options": {
            "profile": "fast",
            "hwdec": "no",
            "cache": "auto",
            "cache-secs": "20",
            "demuxer-max-bytes": "256MiB",
            "demuxer-max-back-bytes": "64MiB",
            "vd-lavc-dr": "no",
            "scale": "bilinear",
            "cscale": "bilinear",
            "dscale": "bilinear",
            "correct-downscaling": "no",
            "sigmoid-upscaling": "no",
            "deband": "no",
            "interpolation": "no",
            "video-sync": "audio",
            "framedrop": "vo",
            "vd-lavc-threads": "0",
        },
    },
    "local_copyback": {
        "name": "local-d3d11-copyback",
        "options": {
            "profile": "fast",
            "hwdec": "d3d11va-copy",
            "cache": "auto",
            "cache-secs": "30",
            "demuxer-max-bytes": "384MiB",
            "demuxer-max-back-bytes": "128MiB",
            "vd-lavc-dr": "no",
            "scale": "bilinear",
            "cscale": "bilinear",
            "dscale": "bilinear",
            "correct-downscaling": "no",
            "sigmoid-upscaling": "no",
            "deband": "no",
            "interpolation": "no",
            "video-sync": "audio",
            "framedrop": "vo",
            "vd-lavc-threads": "0",
        },
    },
    "local_fullscreen_safe": {
        "name": "local-fullscreen-software-stable",
        "options": {
            "profile": "fast",
            "hwdec": "no",
            "cache": "auto",
            "cache-secs": "30",
            "demuxer-max-bytes": "384MiB",
            "demuxer-max-back-bytes": "128MiB",
            "vd-lavc-dr": "no",
            "scale": "bilinear",
            "cscale": "bilinear",
            "dscale": "bilinear",
            "correct-downscaling": "no",
            "sigmoid-upscaling": "no",
            "deband": "no",
            "interpolation": "no",
            "video-sync": "audio",
            "framedrop": "vo",
            "vd-lavc-threads": "0",
        },
    },
    "local_quality": {
        "name": "local-high-quality-software",
        "options": {
            "hwdec": "no",
            "cache": "auto",
            "cache-secs": "45",
            "demuxer-max-bytes": "512MiB",
            "demuxer-max-back-bytes": "192MiB",
            "vd-lavc-dr": "no",
            "scale": "spline36",
            "cscale": "spline36",
            "dscale": "mitchell",
            "correct-downscaling": "yes",
            "sigmoid-upscaling": "no",
            "deband": "no",
            "interpolation": "no",
            "video-sync": "audio",
            "framedrop": "vo",
            "vd-lavc-threads": "0",
        },
    },
    "local_extreme": {
        "name": "local-extreme-quality-software",
        "options": {
            "profile": "gpu-hq",
            "hwdec": "no",
            "cache": "auto",
            "cache-secs": "90",
            "demuxer-max-bytes": "1GiB",
            "demuxer-max-back-bytes": "512MiB",
            "vd-lavc-dr": "no",
            "scale": "ewa_lanczossharp",
            "cscale": "ewa_lanczossharp",
            "dscale": "mitchell",
            "correct-downscaling": "yes",
            "sigmoid-upscaling": "yes",
            "deband": "yes",
            "interpolation": "no",
            "video-sync": "audio",
            "framedrop": "vo",
            "vd-lavc-threads": "0",
        },
    },
    "mpd": {
        "name": "dash-live-stable",
        "options": {
            "cache": "yes",
            "cache-pause": "no",
            "cache-secs": "60",
            "demuxer-max-bytes": "512MiB",
            "demuxer-max-back-bytes": "256MiB",
            "vd-lavc-threads": "0",
        },
    },
    "mpd_quality": {
        "name": "dash-live-quality",
        "options": {
            "cache": "yes",
            "cache-pause": "no",
            "cache-secs": "75",
            "demuxer-max-bytes": "640MiB",
            "demuxer-max-back-bytes": "256MiB",
            "scale": "spline36",
            "cscale": "spline36",
            "dscale": "mitchell",
            "correct-downscaling": "yes",
            "sigmoid-upscaling": "no",
            "deband": "yes",
            "interpolation": "no",
            "video-sync": "audio",
            "framedrop": "vo",
            "vd-lavc-threads": "0",
        },
    },
    "hls": {
        "name": "hls-live-balanced",
        "options": {
            "cache": "yes",
            "cache-pause": "no",
            "cache-secs": "45",
            "demuxer-max-bytes": "384MiB",
            "demuxer-max-back-bytes": "128MiB",
            "vd-lavc-threads": "0",
        },
    },
    "hls_quality": {
        "name": "hls-live-quality",
        "options": {
            "cache": "yes",
            "cache-pause": "no",
            "cache-secs": "60",
            "demuxer-max-bytes": "512MiB",
            "demuxer-max-back-bytes": "192MiB",
            "scale": "spline36",
            "cscale": "spline36",
            "dscale": "mitchell",
            "correct-downscaling": "yes",
            "sigmoid-upscaling": "no",
            "deband": "yes",
            "interpolation": "no",
            "video-sync": "audio",
            "framedrop": "vo",
            "vd-lavc-threads": "0",
        },
    },
    "realtime": {
        "name": "realtime-low-latency",
        "options": {
            "cache": "yes",
            "cache-pause": "no",
            "cache-secs": "20",
            "demuxer-max-bytes": "128MiB",
            "demuxer-max-back-bytes": "64MiB",
            "vd-lavc-threads": "0",
        },
    },
    "http_file": {
        "name": "http-file-vod",
        "options": {
            "cache": "yes",
            "cache-pause": "no",
            "cache-secs": "45",
            "demuxer-max-bytes": "512MiB",
            "demuxer-max-back-bytes": "192MiB",
            "vd-lavc-threads": "0",
        },
    },
    "default": {
        "name": "stream-default",
        "options": {
            "cache": "yes",
            "cache-pause": "no",
            "cache-secs": "30",
            "demuxer-max-bytes": "256MiB",
            "demuxer-max-back-bytes": "128MiB",
            "vd-lavc-threads": "0",
        },
    },
}


class HoverZone(QWidget):
    entered = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)
        self.setStyleSheet("background: rgba(255,255,255,1);")
        self._armed = True

    def enterEvent(self, event):
        if self._armed:
            self._armed = False
            self.entered.emit()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._armed = True
        super().leaveEvent(event)


NATIVE_MPV_AVAILABLE = False
NATIVE_MPV_ERROR = ""
_NATIVE_MPV_LIB = None
_MPV_RUNTIME_LOG = mpv_runtime_log_path()

MPV_FORMAT_STRING = 1
MPV_FORMAT_FLAG = 3
MPV_FORMAT_INT64 = 4
MPV_FORMAT_DOUBLE = 5
MPV_FORMAT_NODE = 6
MPV_FORMAT_NODE_ARRAY = 7
MPV_FORMAT_NODE_MAP = 8


class MpvNode(Structure):
    pass


class MpvNodeList(Structure):
    pass


class MpvByteArray(Structure):
    _fields_ = [
        ("data", c_void_p),
        ("size", c_size_t),
    ]


class MpvNodeUnion(Union):
    _fields_ = [
        ("string", c_char_p),
        ("flag", c_int),
        ("int64", c_longlong),
        ("double_", c_double),
        ("list", POINTER(MpvNodeList)),
        ("ba", POINTER(MpvByteArray)),
    ]


MpvNode._fields_ = [
    ("u", MpvNodeUnion),
    ("format", c_int),
]

MpvNodeList._fields_ = [
    ("num", c_int),
    ("keys", POINTER(c_char_p)),
    ("values", POINTER(MpvNode)),
]

try:
    _mpv_plugin_dir = Path(__file__).resolve().parents[1] / "plugins" / "Mpv"
    _mpv_dll = None
    for _candidate in ("libmpv-2.dll", "mpv-2.dll", "mpv-1.dll"):
        candidate_path = _mpv_plugin_dir / _candidate
        if candidate_path.exists():
            _mpv_dll = candidate_path
            break
    if _mpv_dll is None:
        raise FileNotFoundError(f"libmpv DLL not found in {_mpv_plugin_dir}")

    _NATIVE_MPV_LIB = ctypes.CDLL(str(_mpv_dll))
    _NATIVE_MPV_LIB.mpv_create.restype = c_void_p
    _NATIVE_MPV_LIB.mpv_create.argtypes = []
    _NATIVE_MPV_LIB.mpv_initialize.restype = c_int
    _NATIVE_MPV_LIB.mpv_initialize.argtypes = [c_void_p]
    _NATIVE_MPV_LIB.mpv_set_option_string.restype = c_int
    _NATIVE_MPV_LIB.mpv_set_option_string.argtypes = [c_void_p, c_char_p, c_char_p]
    _NATIVE_MPV_LIB.mpv_set_property_string.restype = c_int
    _NATIVE_MPV_LIB.mpv_set_property_string.argtypes = [c_void_p, c_char_p, c_char_p]
    _NATIVE_MPV_LIB.mpv_get_property_string.restype = c_char_p
    _NATIVE_MPV_LIB.mpv_get_property_string.argtypes = [c_void_p, c_char_p]
    _NATIVE_MPV_LIB.mpv_get_property.restype = c_int
    _NATIVE_MPV_LIB.mpv_get_property.argtypes = [c_void_p, c_char_p, c_int, c_void_p]
    _NATIVE_MPV_LIB.mpv_free_node_contents.restype = None
    _NATIVE_MPV_LIB.mpv_free_node_contents.argtypes = [POINTER(MpvNode)]
    _NATIVE_MPV_LIB.mpv_command.restype = c_int
    _NATIVE_MPV_LIB.mpv_command.argtypes = [c_void_p, POINTER(c_char_p)]
    _NATIVE_MPV_LIB.mpv_command_async.restype = c_int
    _NATIVE_MPV_LIB.mpv_command_async.argtypes = [c_void_p, c_ulonglong, POINTER(c_char_p)]
    _NATIVE_MPV_LIB.mpv_terminate_destroy.restype = None
    _NATIVE_MPV_LIB.mpv_terminate_destroy.argtypes = [c_void_p]
    _NATIVE_MPV_LIB.mpv_error_string.restype = c_char_p
    _NATIVE_MPV_LIB.mpv_error_string.argtypes = [c_int]
    NATIVE_MPV_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    NATIVE_MPV_ERROR = str(exc)


class NativeMpvAdapter:
    def __init__(self, widget, logger=None):
        self.widget = widget
        self.logger = logger
        self.handle = None
        self.renderer_profile = ""
        self.renderer_options = {}
        self.renderer_failures = []

    def _log(self, text):
        if callable(self.logger):
            self.logger(text)

    def _error_text(self, rc):
        raw = _NATIVE_MPV_LIB.mpv_error_string(rc) if _NATIVE_MPV_LIB else None
        return raw.decode("utf-8", errors="replace") if raw else str(rc)

    def _set_option(self, handle, name, value):
        if isinstance(value, bool):
            value = "yes" if value else "no"
        rc = _NATIVE_MPV_LIB.mpv_set_option_string(
            handle,
            str(name).encode("utf-8"),
            str(value).encode("utf-8"),
        )
        if rc < 0:
            raise RuntimeError(f"{name}={value}: {self._error_text(rc)}")

    def _set_property(self, name, value):
        if self.handle is None:
            raise RuntimeError("mpv handle not initialized")
        if isinstance(value, bool):
            value = "yes" if value else "no"
        rc = _NATIVE_MPV_LIB.mpv_set_property_string(
            self.handle,
            str(name).encode("utf-8"),
            str(value).encode("utf-8"),
        )
        if rc < 0:
            raise RuntimeError(f"{name}: {self._error_text(rc)}")

    def initialize(self, force_safe=False, prefer_local_stable=False, local_renderer_mode=""):
        if self.handle is not None:
            return
        if not NATIVE_MPV_AVAILABLE:
            raise RuntimeError(NATIVE_MPV_ERROR or "native libmpv unavailable")
        if not self.widget.isVisible():
            self.widget.show()
        wid = int(self.widget.winId())
        if not wid:
            raise RuntimeError("failed to obtain native window id")

        self.renderer_profile = ""
        self.renderer_options = {}
        self.renderer_failures = []
        diagnostics = get_diagnostics_settings()
        mpv_log_enabled = bool(diagnostics.get("enabled")) and diagnostics.get("level") == "debug"
        log_opts = {"log-file": str(_MPV_RUNTIME_LOG), "msg-level": "all=v"} if mpv_log_enabled else {}
        if mpv_log_enabled:
            log_event(
                "mpv.runtime_log_configured",
                "debug",
                log_path=str(_MPV_RUNTIME_LOG),
            )
        option_sets = []
        if is_safe_mode_enabled() or force_safe:
            renderer_sets = SAFE_MPV_RENDERER_OPTION_SETS
        elif prefer_local_stable:
            mode = str(local_renderer_mode or "").lower()
            if mode in {"opengl", "compat", "software"}:
                renderer_sets = [
                    item
                    for item in LOCAL_MPV_RENDERER_OPTION_SETS
                    if str(item.get("name") or "") == "local-gpu-opengl-software"
                ] + [
                    item
                    for item in LOCAL_MPV_RENDERER_OPTION_SETS
                    if str(item.get("name") or "") not in {
                        "local-gpu-d3d11-native",
                        "local-gpu-opengl-software",
                    }
                ]
            elif mode == "copy":
                renderer_sets = [
                    item
                    for item in LOCAL_MPV_RENDERER_OPTION_SETS
                    if str(item.get("name") or "") != "local-gpu-d3d11-native"
                ]
            else:
                renderer_sets = LOCAL_MPV_RENDERER_OPTION_SETS
        else:
            renderer_sets = MPV_RENDERER_OPTION_SETS
        for option_set in renderer_sets:
            opts = dict(option_set)
            opts.update(log_opts)
            option_sets.append(opts)
        last_error = None
        failures = []
        for opts in option_sets:
            handle = None
            profile_name = str(opts.get("name") or "unknown")
            mpv_opts = {key: value for key, value in opts.items() if key != "name"}
            try:
                handle = _NATIVE_MPV_LIB.mpv_create()
                if not handle:
                    raise RuntimeError("mpv_create returned NULL")
                self._set_option(handle, "wid", wid)
                for key, value in mpv_opts.items():
                    self._set_option(handle, key, value)
                rc = _NATIVE_MPV_LIB.mpv_initialize(handle)
                if rc < 0:
                    raise RuntimeError(self._error_text(rc))
                self.handle = handle
                self.renderer_profile = profile_name
                self.renderer_options = dict(mpv_opts)
                self.renderer_failures = failures
                self._log(f"libmpv initialized with {profile_name}")
                return
            except Exception as exc:
                last_error = exc
                failures.append({"profile": profile_name, "error": str(exc)})
                if handle:
                    try:
                        _NATIVE_MPV_LIB.mpv_terminate_destroy(handle)
                    except Exception:
                        pass
        self.renderer_failures = failures
        raise last_error or RuntimeError("native mpv initialization failed")

    def destroy(self):
        if self.handle is not None:
            try:
                _NATIVE_MPV_LIB.mpv_terminate_destroy(self.handle)
            except Exception:
                pass
            self.handle = None

    def detach_handle(self):
        handle = self.handle
        self.handle = None
        return handle

    def _command_handle_async(self, handle, *args):
        if handle is None:
            return
        arr = (c_char_p * (len(args) + 1))()
        for index, arg in enumerate(args):
            arr[index] = str(arg).encode("utf-8")
        arr[len(args)] = None
        try:
            _NATIVE_MPV_LIB.mpv_command_async(handle, 0, arr)
        except Exception:
            pass

    def destroy_handle(self, handle, stop_first=False):
        if handle is None:
            return
        try:
            if stop_first:
                self._command_handle_async(handle, "stop")
            _NATIVE_MPV_LIB.mpv_terminate_destroy(handle)
        except Exception:
            pass

    def destroy_handle_async(self, handle, delay_ms=0, stop_first=False):
        if handle is None:
            return

        def worker():
            if delay_ms:
                time.sleep(max(0, int(delay_ms)) / 1000.0)
            self.destroy_handle(handle, stop_first=stop_first)

        threading.Thread(target=worker, name="mpv-destroy", daemon=True).start()

    def destroy_if_handle(self, expected_handle):
        if self.handle is not None and self.handle == expected_handle:
            self.destroy()

    def command(self, *args):
        if self.handle is None:
            raise RuntimeError("mpv handle not initialized")
        arr = (c_char_p * (len(args) + 1))()
        for index, arg in enumerate(args):
            arr[index] = str(arg).encode("utf-8")
        arr[len(args)] = None
        rc = _NATIVE_MPV_LIB.mpv_command(self.handle, arr)
        if rc < 0:
            raise RuntimeError(f"{args[0]}: {self._error_text(rc)}")

    def command_async(self, *args):
        if self.handle is None:
            raise RuntimeError("mpv handle not initialized")
        arr = (c_char_p * (len(args) + 1))()
        for index, arg in enumerate(args):
            arr[index] = str(arg).encode("utf-8")
        arr[len(args)] = None
        rc = _NATIVE_MPV_LIB.mpv_command_async(self.handle, 0, arr)
        if rc < 0:
            raise RuntimeError(f"{args[0]}: {self._error_text(rc)}")

    def get_property(self, name):
        if self.handle is None:
            return None
        try:
            raw = _NATIVE_MPV_LIB.mpv_get_property_string(self.handle, str(name).encode("utf-8"))
        except Exception:
            return None
        if not raw:
            return None
        text = raw.decode("utf-8", errors="replace").strip()
        lowered = text.lower()
        if lowered in {"yes", "true"}:
            return True
        if lowered in {"no", "false"}:
            return False
        try:
            if "." in text:
                return float(text)
            return int(text)
        except Exception:
            return text

    def _node_to_python(self, node):
        fmt = int(node.format)
        if fmt == MPV_FORMAT_STRING:
            raw = node.u.string
            return raw.decode("utf-8", errors="replace") if raw else ""
        if fmt == MPV_FORMAT_FLAG:
            return bool(node.u.flag)
        if fmt == MPV_FORMAT_INT64:
            return int(node.u.int64)
        if fmt == MPV_FORMAT_DOUBLE:
            return float(node.u.double_)
        if fmt in (MPV_FORMAT_NODE_ARRAY, MPV_FORMAT_NODE_MAP):
            node_list = node.u.list
            if not node_list:
                return {} if fmt == MPV_FORMAT_NODE_MAP else []
            count = max(0, int(node_list.contents.num))
            values = node_list.contents.values
            if fmt == MPV_FORMAT_NODE_ARRAY:
                return [self._node_to_python(values[index]) for index in range(count)]
            keys = node_list.contents.keys
            result = {}
            for index in range(count):
                raw_key = keys[index] if keys else None
                key = raw_key.decode("utf-8", errors="replace") if raw_key else str(index)
                result[key] = self._node_to_python(values[index])
            return result
        return None

    def get_property_native(self, name):
        if self.handle is None or _NATIVE_MPV_LIB is None:
            return None
        node = MpvNode()
        try:
            rc = _NATIVE_MPV_LIB.mpv_get_property(
                self.handle,
                str(name).encode("utf-8"),
                MPV_FORMAT_NODE,
                cast(byref(node), c_void_p),
            )
            if rc < 0:
                return None
            return self._node_to_python(node)
        except Exception:
            return None
        finally:
            try:
                _NATIVE_MPV_LIB.mpv_free_node_contents(byref(node))
            except Exception:
                pass

    def __getitem__(self, key):
        return self.get_property(key)

    def __setitem__(self, key, value):
        self._set_property(key, value)

    def seek(self, value, reference="absolute"):
        mode = "absolute" if reference == "absolute" else str(reference)
        self.command_async("seek", str(value), mode)

    @property
    def track_list(self):
        tracks = self.get_property_native("track-list")
        return tracks if isinstance(tracks, list) else []

    @property
    def video_params(self):
        width = self.get_property("width") or self.get_property("dwidth")
        height = self.get_property("height") or self.get_property("dheight")
        if width and height:
            return {"w": int(width), "h": int(height)}
        return {}


class SpinnerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setMinimumSize(64, 64)

    def _tick(self):
        self._angle = (self._angle + 30) % 360
        self.update()

    def start(self):
        if not self._timer.isActive():
            self._timer.start(80)
        self.show()

    def stop(self):
        self._timer.stop()
        self.hide()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(8, 8, -8, -8)
        pen = QPen(QColor("#8bb8ff"), 5)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, self._angle * 16, 120 * 16)


class MpvVideoWidget(QWidget):
    playback_started = Signal(dict)
    playback_failed = Signal(dict)
    status_changed = Signal(str)
    loading_changed = Signal(bool)
    loading_text_changed = Signal(str)
    fullscreen_toggle_requested = Signal()
    progress_changed = Signal(float, object)
    duration_changed = Signal(object)
    tracks_changed = Signal(list)
    pause_changed = Signal(bool)
    volume_state_changed = Signal(float, bool)
    quality_changed = Signal(object)
    local_media_finished = Signal(dict)

    QUALITY_PRESETS = [
        ("liu", "流畅", "最快起播", "min"),
        ("sd", "标清", "约 1.5 Mbps", 1_500_000),
        ("hd", "高清", "约 4 Mbps", 4_000_000),
        ("max", "原画", "最高画质", "max"),
    ]
    DEFAULT_QUALITY = "liu"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("mpvViewport")
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors, True)
        self.setStyleSheet("background-color: #000000;")

        self.player = None
        self._native_player = NativeMpvAdapter(self)
        self._player_backend = "native-libmpv"
        self.current_channel = None
        self._failure_sent = False
        self._quality = self.DEFAULT_QUALITY
        self._auto_downgraded = False
        self._static_tracks = []
        self._runtime_tracks = []
        self._last_track_signature = None
        self._loading_text = "正在加载内容..."
        self._finish_announced = False
        self._startup_stream_format = "unknown"
        self._startup_in_progress = False
        self._startup_announced = False
        self._startup_audio_deadline = 0.0
        self._play_request_id = 0
        self._resolve_jobs = {}
        self._resolve_contexts = {}
        self._video_stall_last_position = None
        self._video_stall_last_frame = None
        self._video_stall_since = 0.0
        self._video_stall_recovering = False
        self._last_debug_snapshot_at = 0.0
        self._last_debug_snapshot_key = ""

        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(500)
        self.progress_timer.timeout.connect(self._update_progress)

        self._startup_poll_timer = QTimer(self)
        self._startup_poll_timer.setInterval(350)
        self._startup_poll_timer.timeout.connect(self._poll_startup_state)

        self._idle_check_timer = QTimer(self)
        self._idle_check_timer.setSingleShot(True)
        self._idle_check_timer.timeout.connect(self._check_idle_after_start)

        self._startup_timeout_timer = QTimer(self)
        self._startup_timeout_timer.setSingleShot(True)
        self._startup_timeout_timer.timeout.connect(self._auto_quality_fallback)

        self._single_click_timer = QTimer(self)
        self._single_click_timer.setSingleShot(True)
        self._single_click_timer.setInterval(max(260, QApplication.doubleClickInterval() + 40))
        self._single_click_timer.timeout.connect(self._toggle_pause_from_video_click)
        self._suppress_click_pause_until = 0.0

    def _reset_video_stall_watch(self):
        self._video_stall_last_position = None
        self._video_stall_last_frame = None
        self._video_stall_since = 0.0

    def _screen_debug_info(self):
        window = self.window()
        screen = window.windowHandle().screen() if window and window.windowHandle() else self.screen()
        info = {
            "widget_size": {"w": self.width(), "h": self.height()},
            "native_win_id": int(self.winId()) if self.winId() else 0,
            "window_fullscreen": bool(window.isFullScreen()) if window else False,
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

    def _mpv_debug_snapshot(self):
        if self.player is None:
            return {"player": "none"}
        props = {}
        for name in (
            "vo-configured",
            "hwdec-current",
            "current-vo",
            "estimated-frame-number",
            "time-pos",
            "duration",
            "container-fps",
            "display-fps",
            "mistimed-frame-count",
            "vo-delayed-frame-count",
            "decoder-frame-drop-count",
            "frame-drop-count",
            "video-sync",
            "pause",
            "idle-active",
            "eof-reached",
            "cache-buffering-state",
        ):
            try:
                props[name] = self.player.get_property(name)
            except Exception as exc:
                props[name] = f"<error: {exc}>"
        return {
            "properties": props,
            "video_params_simple": self.player.video_params if self.player else {},
            "renderer_profile": getattr(self._native_player, "renderer_profile", ""),
            "renderer_options": getattr(self._native_player, "renderer_options", {}),
            "renderer_failures": getattr(self._native_player, "renderer_failures", []),
            "screen": self._screen_debug_info(),
        }

    def _log_mpv_snapshot(self, event, level="debug", force=False, **extra):
        channel = self.current_channel or {}
        trace_id = str(channel.get("_TraceId") or "")
        try:
            log_event(
                event,
                level,
                trace_id=trace_id,
                channel=channel,
                force=force,
                snapshot=self._mpv_debug_snapshot(),
                **extra,
            )
        except Exception:
            pass

    def _safe_mpv_debug_snapshot(self):
        try:
            return self._mpv_debug_snapshot()
        except Exception as exc:
            return {"snapshot_error": str(exc)}

    def _set_loading_text(self, text):
        text = (text or "正在加载内容...").strip()
        if text == self._loading_text:
            return
        self._loading_text = text
        self.loading_text_changed.emit(text)

    def _emit_loading_state(self, loading):
        if not loading and self._startup_in_progress and not self._startup_announced:
            return
        self.loading_changed.emit(bool(loading))

    def _stop_startup_watchers(self):
        self._startup_poll_timer.stop()
        self._idle_check_timer.stop()
        self._startup_timeout_timer.stop()
        self._startup_in_progress = False
        self._startup_announced = False
        self._startup_audio_deadline = 0.0

    def _emit_failure(self, code, detail):
        if self._failure_sent:
            return
        code_text = str(code)
        current_channel = self.current_channel or {}
        stream_format = self._detect_stream_format(current_channel.get("Manifest", ""), current_channel)
        if is_local_media_channel(current_channel):
            failure_action = "local-failed"
        elif code_text == "idle-active" and stream_format == "unknown":
            failure_action = "browser-probe"
        else:
            failure_action = "browser-fallback"
        self._failure_sent = True
        self._stop_startup_watchers()
        self._emit_loading_state(False)
        self.playback_failed.emit(
            {
                "kind": "mpv",
                "code": code_text,
                "detail": detail,
                "url": clean_media_url(current_channel.get("Manifest", "")),
                "name": current_channel.get("Name", ""),
                "failure_stage": "mpv",
                "failure_action": failure_action,
                "resolved_info": current_channel.get("_ResolvedInfo", {}),
                "source_url": clean_media_url(current_channel.get("_ResolvedSourceUrl") or current_channel.get("_OriginalManifest") or ""),
            }
        )

    def _set_player_property(self, key, value):
        if self.player is None:
            return False
        try:
            self.player[key] = value
            return True
        except Exception:
            return False

    def _numeric_player_property(self, name):
        if self.player is None:
            return None
        try:
            value = self.player.get_property(name)
            if value in (None, "", False):
                return None
            return float(value)
        except Exception:
            return None

    def _apply_player_options(self, options):
        applied = {}
        failed = {}
        for key, value in (options or {}).items():
            if self._set_player_property(key, value):
                applied[key] = value
            else:
                failed[key] = value
        return applied, failed

    def _playback_policy(self, channel, stream_format):
        if stream_format == "local" or is_local_media_channel(channel):
            if (channel or {}).get("_ForceLocalCompat"):
                return MPV_PLAYBACK_POLICIES["local_compat"]
            if (channel or {}).get("_ForceLocalFullscreenSafe"):
                return MPV_PLAYBACK_POLICIES["local_fullscreen_safe"]
            if (channel or {}).get("_ForceLocalCopyBack"):
                return MPV_PLAYBACK_POLICIES["local_compat"]
            local_mode = get_local_playback_mode()
            if local_mode == "extreme":
                return MPV_PLAYBACK_POLICIES["local_extreme"]
            if local_mode == "quality":
                return MPV_PLAYBACK_POLICIES["local_quality"]
            return MPV_PLAYBACK_POLICIES["local_smooth"]
        if stream_format in {"mpd", "hls"}:
            live_mode = get_live_playback_mode()
            if live_mode == "quality":
                return MPV_PLAYBACK_POLICIES.get(f"{stream_format}_quality", MPV_PLAYBACK_POLICIES[stream_format])
            return MPV_PLAYBACK_POLICIES[stream_format]
        if stream_format in {"rtsp", "rtmp"}:
            return MPV_PLAYBACK_POLICIES["realtime"]
        if stream_format in {"mp4", "flv", "audio", "image", "gif", "online"}:
            return MPV_PLAYBACK_POLICIES["http_file"]
        return MPV_PLAYBACK_POLICIES["default"]

    def _apply_playback_policy(self, channel, stream_format):
        policy = self._playback_policy(channel, stream_format)
        options = dict(policy.get("options") or {})
        if is_safe_mode_enabled():
            options["hwdec"] = "no"
        applied, failed = self._apply_player_options(options)
        trace_id = str((channel or {}).get("_TraceId") or "")
        log_event(
            "mpv.playback_policy",
            "debug",
            trace_id=trace_id,
            channel=channel,
            stream_format=stream_format,
            policy=policy.get("name", ""),
            applied=applied,
            failed=failed,
            renderer_profile=getattr(self._native_player, "renderer_profile", ""),
            renderer_options=getattr(self._native_player, "renderer_options", {}),
        )
        return policy, applied, failed

    def _clear_playback_options(self):
        for key, value in (
            ("demuxer-lavf-o", ""),
            ("http-proxy", ""),
            ("http-header-fields", ""),
            ("user-agent", ""),
            ("referrer", ""),
            ("tls-verify", "no"),
            ("hwdec", "no" if is_safe_mode_enabled() else "auto-safe"),
            ("cache", "auto"),
            ("cache-pause", "no"),
            ("cache-secs", "30"),
            ("demuxer-max-bytes", "256MiB"),
            ("demuxer-max-back-bytes", "128MiB"),
            ("vd-lavc-dr", "yes"),
            ("scale", "auto"),
            ("cscale", "auto"),
            ("dscale", "auto"),
            ("correct-downscaling", "yes"),
            ("sigmoid-upscaling", "yes"),
            ("deband", "no"),
            ("interpolation", "no"),
            ("video-sync", "audio"),
            ("framedrop", "vo"),
            ("speed", "1.0"),
        ):
            self._set_player_property(key, value)

    def _quality_bitrate(self):
        for key, _name, _sub, value in self.QUALITY_PRESETS:
            if key == self._quality:
                return value
        return "min"

    def _apply_network_options(self, channel):
        user_agent = channel.get("UserAgent") or ""
        referer = channel.get("Referer") or ""
        headers = channel.get("Headers") or {}
        stream_url = clean_media_url(channel.get("Manifest") or "")
        header_fields = []
        if user_agent:
            header_fields.append(f"User-Agent: {user_agent}")
            self._set_player_property("user-agent", user_agent)
        else:
            self._set_player_property("user-agent", "")
        if referer:
            header_fields.append(f"Referer: {referer}")
            self._set_player_property("referrer", referer)
        else:
            self._set_player_property("referrer", "")
        if isinstance(headers, dict):
            for key, value in headers.items():
                key_text = str(key).strip()
                value_text = str(value).strip()
                if not key_text or not value_text:
                    continue
                if key_text.lower() in {"user-agent", "referer"}:
                    continue
                header_fields.append(f"{key_text}: {value_text}")
        if _is_explicit_http_media_url(stream_url):
            existing = {field.split(":", 1)[0].strip().lower() for field in header_fields if ":" in field}
            browser_media_headers = {
                "Accept": "*/*",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-Mode": "no-cors",
                "Sec-Fetch-Dest": "video",
                "Cache-Control": "no-cache",
            }
            for key, value in browser_media_headers.items():
                if key.lower() not in existing:
                    header_fields.append(f"{key}: {value}")
        self._set_player_property("http-header-fields", ",".join(header_fields) if header_fields else "")

        proxy_value, _proxy_source = get_effective_proxy(channel)
        self._set_player_property("http-proxy", proxy_value or "")
        self._set_player_property("http-seekable", "yes")
        self._set_player_property("tls-verify", "no")
        self._set_player_property("network-timeout", 15)
        self._set_player_property("hls-bitrate", self._quality_bitrate())
        self._set_player_property("rtsp-transport", "tcp")

    def _apply_stream_options(self, channel, stream_format):
        keys = channel.get("Keys") or []
        decryption_keys = []
        if isinstance(keys, list):
            for item in keys:
                if not isinstance(item, str):
                    continue
                text = item.strip()
                if not text:
                    continue
                if ":" in text:
                    _kid, key = text.split(":", 1)
                    key = key.strip()
                    if key:
                        decryption_keys.append(key)
                else:
                    decryption_keys.append(text)
        if stream_format == "mpd" and decryption_keys:
            self._set_player_property("demuxer-lavf-o", "cenc_decryption_key=" + ",".join(decryption_keys))
        else:
            self._set_player_property("demuxer-lavf-o", "")

    def _detect_stream_format(self, url, channel=None):
        manifest_type = str((channel or {}).get("ManifestType") or "").strip().lower()
        if is_local_media_channel(channel) or manifest_type == "local":
            return "local"
        if manifest_type:
            if "dash" in manifest_type or "mpd" in manifest_type:
                return "mpd"
            if "hls" in manifest_type or "m3u8" in manifest_type:
                return "hls"
            if manifest_type in {"mp4", "flv"}:
                return manifest_type
            if manifest_type in {"audio", "image", "gif", "online"}:
                return manifest_type
            if manifest_type in {"rtsp", "rtmp"}:
                return manifest_type
        lower_url = (url or "").lower()
        if ".mpd" in lower_url or "manifest?" in lower_url or "dash" in lower_url:
            return "mpd"
        if ".m3u8" in lower_url or "hls" in lower_url:
            return "hls"
        if ".mp4" in lower_url or ".m4v" in lower_url or ".mov" in lower_url:
            return "mp4"
        if ".flv" in lower_url:
            return "flv"
        if any(token in lower_url for token in (".mp3", ".aac", ".flac", ".wav", ".m4a", ".ogg", ".wma", ".opus")):
            return "audio"
        if ".gif" in lower_url:
            return "gif"
        if any(token in lower_url for token in (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")):
            return "image"
        if lower_url.startswith("rtsp://"):
            return "rtsp"
        if lower_url.startswith("rtmp://"):
            return "rtmp"
        return "unknown"

    def _is_cenc_mpd_channel(self, channel):
        return self._detect_stream_format(channel.get("Manifest", ""), channel) == "mpd" and bool(channel.get("Keys"))

    def _idle_check_delay_ms(self, channel):
        return 12000 if self._is_cenc_mpd_channel(channel) else 3500

    def _startup_timeout_ms(self, channel):
        return 60000 if self._is_cenc_mpd_channel(channel) else 8000

    def _startup_audio_wait_ms(self, channel):
        stream_format = self._detect_stream_format(channel.get("Manifest", ""), channel)
        if self._is_cenc_mpd_channel(channel):
            return 45000
        if stream_format == "mpd":
            return 15000
        return 0

    def _channel_loading_name(self, channel):
        name = str((channel or {}).get("Name") or "").strip()
        return name or "当前频道"

    def _loading_text_with_channel(self, channel, message):
        return f"{message} {self._channel_loading_name(channel)}"

    def _start_loading_for_channel(self, channel, stream_format):
        if stream_format == "mpd" and channel.get("Keys"):
            text = self._loading_text_with_channel(channel, "正在建立") + " · MPD/CENC 音视频轨道..."
        elif stream_format == "mpd":
            text = self._loading_text_with_channel(channel, "正在连接") + " · MPD/DASH 直播流..."
        elif stream_format == "hls":
            text = self._loading_text_with_channel(channel, "正在缓冲") + " · HLS 直播流..."
        elif stream_format == "local":
            text = self._loading_text_with_channel(channel, "正在打开") + " · 本地媒体..."
        else:
            text = self._loading_text_with_channel(channel, "正在加载") + "..."
        self._set_loading_text(text)
        self._emit_loading_state(True)

    def _update_loading_text_now(self, text):
        channel = self.current_channel or {}
        name = self._channel_loading_name(channel)
        clean = str(text or "正在加载内容...").strip()
        if name and name not in clean:
            clean = f"{clean}（{name}）"
        self._set_loading_text(clean)
        self._emit_loading_state(True)

    def _reset_player_state(self, channel, reload=False):
        self._stop_startup_watchers()
        old_player = self.player
        old_handle = getattr(old_player, "handle", None)
        if old_player is not None:
            try:
                old_player.command_async("stop")
            except Exception:
                pass
        if old_handle is not None:
            try:
                self._native_player.detach_handle()
            except Exception:
                old_handle = None
        self.player = None
        if old_handle is not None:
            self._native_player.destroy_handle_async(old_handle, delay_ms=180, stop_first=True)
        self.current_channel = channel
        self._failure_sent = False
        self._finish_announced = False
        self._reset_video_stall_watch()
        self._video_stall_recovering = False
        self._last_debug_snapshot_at = 0.0
        self._last_debug_snapshot_key = ""
        self._static_tracks = []
        self._runtime_tracks = []
        self._last_track_signature = None
        self._emit_tracks_changed(force=True)
        if not reload:
            self._auto_downgraded = False

    def _initialize_player_or_fail(self, channel):
        try:
            self._native_player.initialize(
                force_safe=bool((channel or {}).get("_ForceLocalCompat")),
                prefer_local_stable=is_local_media_channel(channel),
                local_renderer_mode=(
                    "opengl"
                    if (channel or {}).get("_ForceLocalFullscreenSafe")
                    else "compat"
                    if (channel or {}).get("_ForceLocalCopyBack") or (channel or {}).get("_ForceLocalCompat")
                    else ""
                ),
            )
            self.player = self._native_player
            log_event(
                "mpv.initialized",
                "debug",
                trace_id=str((channel or {}).get("_TraceId") or ""),
                channel=channel,
                renderer_profile=getattr(self._native_player, "renderer_profile", ""),
                renderer_options=getattr(self._native_player, "renderer_options", {}),
                renderer_failures=getattr(self._native_player, "renderer_failures", []),
            )
            return True
        except Exception as exc:
            self.player = None
            self.playback_failed.emit(
                {
                    "kind": "mpv",
                    "code": "unavailable",
                    "detail": str(exc) or NATIVE_MPV_ERROR or "libmpv 未初始化成功",
                    "url": channel.get("Manifest", ""),
                    "name": channel.get("Name", ""),
                    "renderer_failures": getattr(self._native_player, "renderer_failures", []),
                }
            )
            return False

    def _start_resolve_worker(self, request_id, channel, raw_stream_name, reload=False):
        """Start live stream resolution in a worker thread."""
        thread = QThread(self)
        worker = ResolveChannelWorker(request_id, channel, force=reload)
        worker.moveToThread(thread)
        self._resolve_jobs[int(request_id)] = (thread, worker)
        self._resolve_contexts[int(request_id)] = {
            "channel": dict(channel or {}),
            "raw_stream_name": raw_stream_name,
        }
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_resolve_progress)
        worker.finished.connect(self._on_resolve_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(lambda request_id=request_id: self._cleanup_resolve_job(request_id))
        thread.start()

    def _cancel_pending_resolvers(self):
        """Cancel stale resolver workers; active network calls finish naturally."""
        for _request_id, (_thread, worker) in list(self._resolve_jobs.items()):
            try:
                worker.cancel()
            except Exception:
                pass

    def _cleanup_resolve_job(self, request_id):
        """Forget a finished resolver job."""
        self._resolve_jobs.pop(int(request_id), None)
        self._resolve_contexts.pop(int(request_id), None)

    def _is_current_play_request(self, request_id):
        return int(request_id) == int(self._play_request_id)

    def _on_resolve_progress(self, request_id, text):
        """Update loading text from the active resolver only."""
        if not self._is_current_play_request(request_id):
            return
        self._update_loading_text_now(text)

    def _on_resolve_finished(self, request_id, resolved):
        """Continue playback after async live stream resolution."""
        if not self._is_current_play_request(request_id):
            return
        context = self._resolve_contexts.get(int(request_id)) or {}
        original_channel = dict(context.get("channel") or self.current_channel or {})
        raw_stream_name = context.get("raw_stream_name") or original_channel.get("Name") or "Unnamed Channel"

        if not isinstance(resolved, dict) or resolved.get("status") != "ok":
            self._emit_resolve_failure(original_channel, resolved if isinstance(resolved, dict) else {})
            return

        channel = self._apply_resolved_channel(original_channel, resolved)
        if not self._initialize_player_or_fail(channel):
            return
        if not self._is_current_play_request(request_id):
            return

        self.current_channel = channel
        self._static_tracks = self._extract_static_tracks(channel)
        self._emit_tracks_changed(force=True)

        stream_name = channel.get("Name") or raw_stream_name
        try:
            self._load_channel_into_player(channel, stream_name)
        except Exception as exc:
            self._stop_startup_watchers()
            self._emit_loading_state(False)
            self.playback_failed.emit(
                {
                    "kind": "mpv",
                    "code": "loadfile",
                    "detail": f"[{self._player_backend}] {exc}",
                    "url": channel.get("Manifest", ""),
                    "name": stream_name,
                    "failure_stage": "mpv",
                    "failure_action": "browser-fallback",
                }
            )

    def _load_channel_into_player(self, channel, stream_name):
        stream_url = clean_media_url(channel.get("Manifest") or "")
        if stream_url and stream_url != channel.get("Manifest"):
            channel["Manifest"] = stream_url
        stream_format = self._detect_stream_format(stream_url, channel)
        self._startup_stream_format = stream_format

        try:
            self.player.command("stop")
        except Exception:
            pass

        self._start_loading_for_channel(channel, stream_format)
        self._clear_playback_options()
        policy, _applied_options, _failed_options = self._apply_playback_policy(channel, stream_format)
        if stream_format != "local":
            self._apply_network_options(channel)
            self._apply_stream_options(channel, stream_format)
        self.player["force-media-title"] = stream_name
        self.player.command_async("loadfile", stream_url, "replace")
        self._schedule_start_position_seek(channel, self._play_request_id)
        action_text = "正在打开" if stream_format == "local" else "正在连接"
        policy_name = policy.get("name", stream_format)
        self.status_changed.emit(f"{action_text}：{stream_name} ({stream_format.upper()}, {policy_name}, {self._player_backend})")
        if not self.progress_timer.isActive():
            self.progress_timer.start()
        self.pause_changed.emit(bool(self.player["pause"]))
        self.volume_state_changed.emit(float(self.player["volume"] or 100), bool(self.player["mute"]))
        self._begin_startup_watchers(channel)

    def _schedule_start_position_seek(self, channel, request_id):
        try:
            position = max(0.0, float((channel or {}).get("_StartPosition") or 0.0))
        except (TypeError, ValueError):
            position = 0.0
        if position <= 0:
            return

        def try_seek(attempt=0):
            if int(request_id) != int(self._play_request_id) or self.player is None:
                return
            duration = self._numeric_player_property("duration")
            target = position
            if duration and duration > 0:
                target = min(position, max(0.0, duration - 0.5))
            self.seek_absolute(target)
            self.status_changed.emit(f"已从 {int(target // 60):02d}:{int(target % 60):02d} 附近恢复播放")
            if duration and duration > 0:
                return
            if attempt < 8:
                QTimer.singleShot(450, lambda: try_seek(attempt + 1))

        QTimer.singleShot(450, try_seek)

    def _apply_resolved_channel(self, channel, resolved):
        applied = dict(channel or {})
        resolved_url = clean_media_url(resolved.get("media_url") or "")
        resolved_type = str(resolved.get("media_type") or "").strip().lower()
        resolved_from = str(resolved.get("resolved_from") or "").strip().lower()
        source_page = clean_media_url(resolved.get("final_url") or channel.get("Manifest") or "")
        if resolved_url:
            applied["Manifest"] = resolved_url
        if resolved_type == "dash":
            applied["ManifestType"] = "mpd"
        elif resolved_type:
            applied["ManifestType"] = resolved_type
        if resolved_from in {"html", "script", "api", "redirect"}:
            source_page = (
                clean_media_url(channel.get("Manifest") or "")
                if resolved_from == "redirect"
                else source_page
            )
            applied["_OriginalManifest"] = clean_media_url(channel.get("Manifest") or "")
            applied["_ResolvedSourceUrl"] = source_page
            resolved_is_direct_media = _is_explicit_http_media_url(applied.get("Manifest") or "")
            if resolved_from == "redirect" and resolved_is_direct_media:
                applied.pop("Referer", None)
                headers = dict(applied.get("Headers") or {})
                for key in list(headers.keys()):
                    if str(key).strip().lower() in {"origin", "referer"}:
                        headers.pop(key, None)
                if headers:
                    applied["Headers"] = headers
                else:
                    applied.pop("Headers", None)
            elif source_page and not applied.get("Referer"):
                applied["Referer"] = source_page
            if not applied.get("UserAgent"):
                applied["UserAgent"] = DEFAULT_BROWSER_USER_AGENT
            page_origin = _url_origin(source_page)
            media_origin = _url_origin(applied.get("Manifest") or "")
            if not (resolved_from == "redirect" and resolved_is_direct_media) and page_origin and media_origin and page_origin != media_origin:
                headers = dict(applied.get("Headers") or {})
                headers.setdefault("Origin", page_origin)
                headers.setdefault("Accept", "*/*")
                applied["Headers"] = headers
        applied["_ResolvedInfo"] = dict(resolved)
        return applied

    def _emit_resolve_failure(self, channel, resolved):
        status = str(resolved.get("status") or "error")
        http_status = resolved.get("http_status")
        detail = str(resolved.get("message") or "").strip()
        final_url = str(resolved.get("final_url") or channel.get("Manifest") or "").strip()
        code = "resolve-failed"
        failure_action = "generic"
        if status == "dead":
            code = "source-dead"
            failure_action = "next-channel"
            detail = detail or "直播链接已不存在或不可用"
        elif status == "page" and resolved.get("need_js_probe"):
            code = "need-js-probe"
            failure_action = "browser-probe"
            detail = detail or "页面型源需要进一步 JS 嗅探"
        elif status == "unresolved":
            code = "unresolved-media"
            failure_action = "browser-fallback"
            detail = detail or "未能识别真实媒体地址"
        elif status == "error":
            code = f"http-{http_status}" if http_status else "resolve-error"
            if http_status in {400, 404, 410, 451, 500, 502, 503, 504}:
                failure_action = "next-channel"
            else:
                failure_action = "browser-fallback"
            detail = detail or "媒体解析失败"

        self._emit_loading_state(False)
        self.playback_failed.emit(
            {
                "kind": "mpv",
                "code": code,
                "detail": detail,
                "url": clean_media_url(final_url),
                "name": (channel or {}).get("Name", ""),
                "http_status": http_status,
                "failure_stage": "resolve",
                "failure_action": failure_action,
                "resolved_info": channel.get("_ResolvedInfo", {}) if isinstance(channel, dict) else {},
                "source_url": clean_media_url(
                    (
                        channel.get("_ResolvedSourceUrl")
                        or channel.get("_OriginalManifest")
                        or ""
                    )
                    if isinstance(channel, dict)
                    else ""
                ),
            }
        )

    def _selected_track_state(self, prop):
        value = self.player.get_property(prop) if self.player is not None else None
        if value is None:
            return "unknown"
        text = str(value).strip().lower()
        if not text:
            return "unknown"
        if text in {"no", "none", "false", "0"}:
            return "absent"
        return "present"

    def _video_started(self):
        if self.player is None:
            return False
        try:
            params = self.player.video_params
            return bool(params) and bool(params.get("w"))
        except Exception:
            return False

    def _audio_started(self):
        if self.player is None:
            return False
        try:
            codec = self.player.get_property("audio-codec-name")
            if codec:
                return True
            if self._selected_track_state("aid") == "absent":
                return False
            params = self.player.get_property("audio-params")
            if isinstance(params, str):
                return bool(params.strip())
            return bool(params)
        except Exception:
            return False

    def _track_required(self, channel, track_type):
        if track_type == "video" and channel.get("VideoTracks"):
            return True
        if track_type == "audio" and channel.get("AudioTracks"):
            return True
        prop = "vid" if track_type == "video" else "aid"
        state = self._selected_track_state(prop)
        if state == "absent":
            return False
        stream_format = self._detect_stream_format(channel.get("Manifest", ""), channel)
        if stream_format == "mpd":
            return True
        return state == "present"

    def _startup_ready(self, channel):
        video_ready = self._video_started()
        audio_ready = self._audio_started()
        stream_format = self._detect_stream_format(channel.get("Manifest", ""), channel)
        if stream_format != "mpd":
            return video_ready or audio_ready
        needs_video = self._track_required(channel, "video")
        needs_audio = self._track_required(channel, "audio")
        if needs_video and not video_ready:
            return False
        if needs_audio and not audio_ready:
            return False
        return video_ready or audio_ready

    def _extract_static_tracks(self, channel):
        default_video = str(channel.get("DefaultVideo") or "").strip()
        default_audio = str(channel.get("DefaultAudio") or "").strip()
        default_subtitles = str(channel.get("DefaultSubtitles") or "").strip()
        tracks = []

        for index, video in enumerate(channel.get("VideoTracks") or []):
            item = dict(video)
            item["type"] = "video"
            item["selected"] = str(item.get("id") or "") == default_video if default_video else index == 0
            tracks.append(item)
        for index, audio in enumerate(channel.get("AudioTracks") or []):
            item = dict(audio)
            item["type"] = "audio"
            item["selected"] = str(item.get("id") or "") == default_audio if default_audio else index == 0
            tracks.append(item)
        for subtitle in channel.get("SubtitleTracks") or []:
            item = dict(subtitle)
            item["type"] = "sub"
            item["selected"] = str(item.get("id") or "") == default_subtitles if default_subtitles else False
            tracks.append(item)

        normalized = []
        for track in tracks:
            normalized.append(
                {
                    "id": track.get("id") or track.get("Id") or "",
                    "type": track.get("type"),
                    "selected": bool(track.get("selected")),
                    "title": track.get("title") or track.get("Title") or "",
                    "lang": track.get("language") or track.get("lang") or track.get("Lang") or "",
                    "codec": track.get("codec") or track.get("Codec") or "",
                    "demux-w": track.get("width"),
                    "demux-h": track.get("height"),
                    "demux-fps": track.get("fps"),
                    "demux-bitrate": track.get("bitrate") or track.get("Bandwidth"),
                    "demux-samplerate": track.get("sampling_rate"),
                    "demux-channel-count": track.get("channels"),
                    "resolution": track.get("resolution") or track.get("Resolution") or "",
                    "source": track.get("source") or "file",
                    "playback_id": track.get("playback_id"),
                }
            )
        return normalized

    def _normalize_runtime_track(self, track):
        if not isinstance(track, dict):
            return None
        track_type = str(track.get("type") or "").strip().lower()
        if track_type in {"subtitle", "subtitles"}:
            track_type = "sub"
        if track_type not in {"video", "audio", "sub"}:
            return None
        track_id = track.get("id")
        normalized = {
            "id": track_id,
            "type": track_type,
            "selected": bool(track.get("selected")),
            "title": track.get("title") or track.get("external-filename") or "",
            "lang": track.get("lang") or track.get("language") or "",
            "codec": track.get("codec") or track.get("decoder-desc") or "",
            "demux-w": track.get("demux-w") or track.get("w"),
            "demux-h": track.get("demux-h") or track.get("h"),
            "demux-fps": track.get("demux-fps") or track.get("fps"),
            "demux-bitrate": track.get("demux-bitrate") or track.get("bitrate"),
            "demux-samplerate": track.get("demux-samplerate") or track.get("samplerate"),
            "demux-channel-count": track.get("demux-channel-count") or track.get("channels"),
            "source": "mpv",
            "playback_id": track_id,
        }
        width = normalized.get("demux-w")
        height = normalized.get("demux-h")
        if width and height:
            normalized["resolution"] = f"{width}x{height}"
        return normalized

    @staticmethod
    def _track_text(value):
        return str(value or "").strip().lower()

    @staticmethod
    def _track_number(value):
        if value in (None, "", False):
            return None
        try:
            return float(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            return None

    def _numbers_close(self, left, right, ratio=0.12, absolute=1.0):
        left_num = self._track_number(left)
        right_num = self._track_number(right)
        if left_num is None or right_num is None:
            return False
        if left_num == right_num:
            return True
        return abs(left_num - right_num) <= max(absolute, max(abs(left_num), abs(right_num)) * ratio)

    def _codec_family(self, value):
        text = self._track_text(value)
        if not text:
            return ""
        if any(token in text for token in ("avc", "h264", "h.264")):
            return "h264"
        if any(token in text for token in ("hev", "hvc", "h265", "h.265", "hevc")):
            return "hevc"
        if any(token in text for token in ("mp4a", "aac")):
            return "aac"
        if any(token in text for token in ("eac3", "ec-3")):
            return "eac3"
        if any(token in text for token in ("ac3", "ac-3")):
            return "ac3"
        if "opus" in text:
            return "opus"
        if "mp3" in text:
            return "mp3"
        if "srt" in text:
            return "srt"
        if "webvtt" in text or "vtt" in text:
            return "webvtt"
        return text.split(".", 1)[0]

    def _codec_matches(self, left, right):
        left_family = self._codec_family(left)
        right_family = self._codec_family(right)
        return bool(left_family and right_family and left_family == right_family)

    def _track_match_score(self, static_track, runtime_track):
        static_id = self._track_text(static_track.get("id"))
        runtime_id = self._track_text(runtime_track.get("id"))
        if static_id and static_id == runtime_id:
            return 1000

        score = 0
        kind = static_track.get("type")
        static_lang = self._track_text(static_track.get("lang"))
        runtime_lang = self._track_text(runtime_track.get("lang"))
        static_codec = static_track.get("codec")
        runtime_codec = runtime_track.get("codec")
        static_title = self._track_text(static_track.get("title"))
        runtime_title = self._track_text(runtime_track.get("title"))

        if kind == "video":
            if static_track.get("demux-w") and runtime_track.get("demux-w"):
                score += 80 if static_track.get("demux-w") == runtime_track.get("demux-w") else 0
            if static_track.get("demux-h") and runtime_track.get("demux-h"):
                if static_track.get("demux-h") == runtime_track.get("demux-h"):
                    score += 100
                elif self._numbers_close(static_track.get("demux-h"), runtime_track.get("demux-h"), ratio=0.02, absolute=2):
                    score += 40
            if self._numbers_close(static_track.get("demux-bitrate"), runtime_track.get("demux-bitrate"), ratio=0.25, absolute=100_000):
                score += 45
            if self._numbers_close(static_track.get("demux-fps"), runtime_track.get("demux-fps"), ratio=0.02, absolute=0.5):
                score += 25
            if self._codec_matches(static_codec, runtime_codec):
                score += 25
            if static_lang and static_lang == runtime_lang:
                score += 10
            return score

        if kind == "audio":
            if static_lang and static_lang == runtime_lang:
                score += 85
            elif not static_lang and not runtime_lang:
                score += 8
            if self._codec_matches(static_codec, runtime_codec):
                score += 35
            if self._numbers_close(static_track.get("demux-bitrate"), runtime_track.get("demux-bitrate"), ratio=0.30, absolute=32_000):
                score += 25
            if self._numbers_close(static_track.get("demux-samplerate"), runtime_track.get("demux-samplerate"), ratio=0.02, absolute=100):
                score += 25
            if static_track.get("demux-channel-count") and static_track.get("demux-channel-count") == runtime_track.get("demux-channel-count"):
                score += 20
            if static_title and runtime_title and (static_title in runtime_title or runtime_title in static_title):
                score += 15
            return score

        if kind == "sub":
            if static_lang and static_lang == runtime_lang:
                score += 80
            if static_title and runtime_title and (static_title in runtime_title or runtime_title in static_title):
                score += 40
            if self._codec_matches(static_codec, runtime_codec):
                score += 20
            return score

        return score

    def _find_runtime_track_match(self, static_track, runtime_tracks, used_indexes, index, static_count):
        best_index = None
        best_track = None
        best_score = 0
        for runtime_index, runtime_track in enumerate(runtime_tracks):
            if runtime_index in used_indexes:
                continue
            score = self._track_match_score(static_track, runtime_track)
            if score > best_score:
                best_score = score
                best_index = runtime_index
                best_track = runtime_track

        threshold = {"video": 80, "audio": 60, "sub": 50}.get(static_track.get("type"), 60)
        if best_track is not None and best_score >= threshold:
            return best_index, best_track

        if static_count == len(runtime_tracks) and index < len(runtime_tracks) and index not in used_indexes:
            return index, runtime_tracks[index]
        return None, None

    def _merge_tracks(self):
        runtime_by_type = {"video": [], "audio": [], "sub": []}
        for track in self._runtime_tracks:
            runtime_by_type.setdefault(track.get("type"), []).append(track)

        merged = []
        for kind in ("video", "audio", "sub"):
            static_tracks = [track for track in self._static_tracks if track.get("type") == kind]
            runtime_tracks = runtime_by_type.get(kind) or []
            if not static_tracks:
                merged.extend(runtime_tracks)
                continue

            used = set()
            for index, static_track in enumerate(static_tracks):
                item = dict(static_track)
                runtime_index, runtime_track = self._find_runtime_track_match(
                    static_track,
                    runtime_tracks,
                    used,
                    index,
                    len(static_tracks),
                )
                if runtime_track:
                    used.add(runtime_index)
                    item["playback_id"] = runtime_track.get("playback_id")
                    item["selected"] = bool(runtime_track.get("selected"))
                    for key in ("codec", "demux-w", "demux-h", "demux-fps", "demux-bitrate", "demux-samplerate", "demux-channel-count", "resolution"):
                        if item.get(key) in (None, "", 0):
                            item[key] = runtime_track.get(key)
                merged.append(item)
        return merged

    def _track_signature(self, tracks):
        signature = []
        for track in tracks:
            signature.append(
                (
                    track.get("type"),
                    str(track.get("id")),
                    str(track.get("playback_id")),
                    bool(track.get("selected")),
                    str(track.get("title") or ""),
                    str(track.get("lang") or ""),
                    str(track.get("codec") or ""),
                    str(track.get("demux-w") or ""),
                    str(track.get("demux-h") or ""),
                    str(track.get("demux-bitrate") or ""),
                )
            )
        return tuple(signature)

    def _emit_tracks_changed(self, force=False):
        tracks = self._merge_tracks()
        signature = self._track_signature(tracks)
        if force or signature != self._last_track_signature:
            self._last_track_signature = signature
            self.tracks_changed.emit(tracks)

    def _refresh_runtime_tracks(self, force=False):
        if self.player is None:
            return
        try:
            raw_tracks = self.player.track_list
        except Exception:
            raw_tracks = []
        runtime_tracks = []
        for raw_track in raw_tracks or []:
            normalized = self._normalize_runtime_track(raw_track)
            if normalized:
                runtime_tracks.append(normalized)
        if force or self._track_signature(runtime_tracks) != self._track_signature(self._runtime_tracks):
            self._runtime_tracks = runtime_tracks
            self._emit_tracks_changed(force=force)

    def _begin_startup_watchers(self, channel):
        self._startup_in_progress = True
        self._startup_announced = False
        wait_ms = self._startup_audio_wait_ms(channel)
        self._startup_audio_deadline = time.monotonic() + (wait_ms / 1000.0 if wait_ms else 0.0)
        self._startup_poll_timer.start()
        self._idle_check_timer.start(self._idle_check_delay_ms(channel))
        self._startup_timeout_timer.start(self._startup_timeout_ms(channel))

    def _announce_startup_ready(self):
        if self.current_channel is None or self._startup_announced:
            return
        self._startup_announced = True
        self._startup_in_progress = False
        self._startup_poll_timer.stop()
        self._idle_check_timer.stop()
        self._startup_timeout_timer.stop()
        stream_name = self.current_channel.get("Name") or "未命名频道"
        self.status_changed.emit(
            f"正在播放：{stream_name} ({self._startup_stream_format.upper()}, {self._player_backend})"
        )
        self._emit_loading_state(False)
        self._refresh_runtime_tracks(force=True)
        log_event(
            "mpv.playback_ready",
            "debug",
            trace_id=str((self.current_channel or {}).get("_TraceId") or ""),
            channel=self.current_channel,
            stream_format=self._startup_stream_format,
            renderer_profile=getattr(self._native_player, "renderer_profile", ""),
            renderer_options=getattr(self._native_player, "renderer_options", {}),
            renderer_failures=getattr(self._native_player, "renderer_failures", []),
            hwdec_current=self.player.get_property("hwdec-current") if self.player else None,
            video_codec=self.player.get_property("video-codec-name") if self.player else None,
            video_params=self.player.video_params if self.player else {},
            decoder_drops=self.player.get_property("decoder-frame-drop-count") if self.player else None,
            vo_drops=self.player.get_property("frame-drop-count") if self.player else None,
            snapshot=self._safe_mpv_debug_snapshot(),
        )
        self.playback_started.emit(self.current_channel)

    def _poll_startup_state(self):
        if self.player is None or self.current_channel is None or self._failure_sent:
            self._stop_startup_watchers()
            return
        video_ready = self._video_started()
        audio_ready = self._audio_started()
        if self._startup_ready(self.current_channel):
            self._announce_startup_ready()
            return
        if self._startup_stream_format == "mpd" and video_ready and not audio_ready:
            if self._startup_audio_deadline and time.monotonic() < self._startup_audio_deadline:
                self._set_loading_text("画面已就绪，正在等待音频同步...")
                self.status_changed.emit("视频轨已就绪，正在等待音频轨道...")
            else:
                self._set_loading_text("音频轨初始化较慢，继续等待中...")
                self.status_changed.emit("音频轨初始化较慢，继续等待中...")
        elif video_ready or audio_ready:
            self._set_loading_text("媒体轨已连接，正在完成起播...")
        else:
            self._start_loading_for_channel(self.current_channel, self._startup_stream_format)

    def _check_idle_after_start(self):
        if self.player is None or self.current_channel is None or self._failure_sent:
            return
        try:
            idle_active = bool(self.player["idle-active"])
            paused = bool(self.player["pause"])
            if idle_active and not paused:
                self._emit_failure("idle-active", "播放器进入空闲状态，媒体可能未成功打开。")
        except Exception:
            pass

    def _auto_quality_fallback(self):
        if self.player is None or self.current_channel is None or self._failure_sent:
            return
        if self._startup_ready(self.current_channel):
            self._announce_startup_ready()
            return
        stream_format = self._detect_stream_format((self.current_channel or {}).get("Manifest", ""), self.current_channel)
        video_ready = self._video_started()
        audio_ready = self._audio_started()
        if stream_format == "mpd" and video_ready and not audio_ready:
            self._emit_failure("audio-timeout", "视频轨已就绪，但音频轨在等待窗口内未完成初始化。")
            return
        if stream_format == "mpd" and (self.current_channel or {}).get("Keys"):
            self._emit_failure("cenc-timeout", "MPD/CENC 流已加载，但未成功建立可播放的解密轨道。")
            return
        try:
            if bool(self.player["pause"]):
                return
        except Exception:
            pass
        if self._quality != self.DEFAULT_QUALITY and not self._auto_downgraded:
            self._auto_downgraded = True
            self._quality = self.DEFAULT_QUALITY
            self.status_changed.emit("网络较慢，已自动切换到“流畅”。")
            self.quality_changed.emit(self._quality)
            self.play_channel(self.current_channel, _reload=True)
            return
        self.status_changed.emit("网络较慢，画面仍在加载中，可尝试改用浏览器播放。")

    def get_tracks(self):
        return self._merge_tracks()

    def set_video_track(self, value):
        if value not in (None, "") and self._set_player_property("vid", value):
            self._refresh_runtime_tracks(force=True)

    def set_audio_track(self, value):
        if value not in (None, "") and self._set_player_property("aid", value):
            self._refresh_runtime_tracks(force=True)

    def set_subtitle_track(self, value):
        if value not in (None, "") and self._set_player_property("sid", value):
            self._refresh_runtime_tracks(force=True)

    def toggle_pause(self):
        if self.player is None:
            return
        if self._restart_finished_local_media():
            return
        try:
            paused = not bool(self.player["pause"])
            self.player["pause"] = paused
            self.pause_changed.emit(paused)
        except Exception:
            pass

    def set_pause(self, paused):
        if self.player is None:
            return
        if not bool(paused) and self._restart_finished_local_media():
            return
        try:
            paused = bool(paused)
            self.player["pause"] = paused
            self.pause_changed.emit(paused)
        except Exception:
            pass

    def _local_media_is_finished(self):
        """Return whether the current local media has reached EOF/idle."""
        if self.player is None or not is_local_media_channel(self.current_channel or {}):
            return False
        try:
            if bool(self.player.get_property("idle-active")):
                return True
            if bool(self.player.get_property("eof-reached")):
                return True
            duration = self.player.get_property("duration")
            position = self.player.get_property("time-pos")
            if duration and position is not None:
                return float(duration) > 0 and float(position) >= max(0.0, float(duration) - 0.35)
        except Exception:
            return False
        return False

    def _restart_finished_local_media(self):
        """Restart local media when the user presses play after completion."""
        if not self._local_media_is_finished():
            return False
        channel = dict(self.current_channel or {})
        if not channel:
            return False
        self.status_changed.emit(f"重新播放：{channel.get('Name') or '本地媒体'}")
        self.play_channel(channel, _reload=True)
        return True

    def set_volume(self, value):
        if self.player is None:
            return
        try:
            self.player["volume"] = float(max(0, min(100, value)))
            self.volume_state_changed.emit(float(self.player["volume"] or 0), bool(self.player["mute"]))
        except Exception:
            pass

    def toggle_mute(self):
        if self.player is None:
            return
        try:
            muted = not bool(self.player["mute"])
            self.player["mute"] = muted
            self.volume_state_changed.emit(float(self.player["volume"] or 0), muted)
        except Exception:
            pass

    def set_playback_speed(self, speed):
        if self.player is None:
            return
        try:
            speed_value = float(speed)
        except (TypeError, ValueError):
            speed_value = 1.0
        speed_value = max(0.25, min(4.0, speed_value))
        try:
            self.player["speed"] = speed_value
            label = f"{int(speed_value)}x" if float(speed_value).is_integer() else f"{speed_value:g}x"
            self.status_changed.emit(f"播放倍率：{label}")
        except Exception:
            pass

    def seek_relative(self, seconds):
        if self.player is None:
            return
        try:
            self.player.command_async("seek", seconds, "relative")
        except Exception:
            pass

    def seek_fraction(self, fraction):
        if self.player is None:
            return
        try:
            duration = self.player.get_property("duration")
            if duration and duration > 0:
                self.player.seek(fraction * duration, reference="absolute")
        except Exception:
            pass

    def seek_absolute(self, seconds):
        if self.player is None:
            return
        try:
            value = max(0.0, float(seconds or 0.0))
            self.player.seek(value, reference="absolute")
        except Exception:
            pass

    def _check_video_render_stall(self, position, duration):
        if self.player is None or self._video_stall_recovering:
            return
        channel = self.current_channel or {}
        if not is_local_media_channel(channel):
            self._reset_video_stall_watch()
            return
        try:
            if bool(self.player["pause"]):
                self._reset_video_stall_watch()
                return
        except Exception:
            return
        if not duration or float(duration or 0) <= 0 or not self._video_started():
            self._reset_video_stall_watch()
            return

        frame = self._numeric_player_property("estimated-frame-number")
        if frame is None:
            return

        try:
            position_value = float(position or 0.0)
        except (TypeError, ValueError):
            return
        now = time.monotonic()
        last_position = self._video_stall_last_position
        last_frame = self._video_stall_last_frame
        self._video_stall_last_position = position_value
        self._video_stall_last_frame = frame
        if last_position is None or last_frame is None:
            return

        position_advanced = position_value - float(last_position or 0.0) >= 0.35
        frame_stuck = frame <= float(last_frame or 0.0) + 0.01
        if position_advanced and frame_stuck:
            if not self._video_stall_since:
                self._video_stall_since = now
                self._log_mpv_snapshot(
                    "mpv.video_render_stall_suspected",
                    "warning",
                    position=position_value,
                    last_position=last_position,
                    frame=frame,
                    last_frame=last_frame,
                )
            elif now - self._video_stall_since >= 6.0:
                self._recover_video_render_stall(position_value)
            return

        if frame > float(last_frame or 0.0) + 0.01:
            self._video_stall_since = 0.0

    def _maybe_log_runtime_snapshot(self, position, duration):
        if self.player is None:
            return
        channel = self.current_channel or {}
        if not is_local_media_channel(channel):
            return
        window = self.window()
        is_fullscreen = bool(window.isFullScreen()) if window else False
        now = time.monotonic()
        interval = 10.0 if is_fullscreen else 30.0
        if now - self._last_debug_snapshot_at < interval:
            return
        frame = self._numeric_player_property("estimated-frame-number")
        key = f"{int(position or 0)}|{int(frame or -1)}|{int(is_fullscreen)}"
        if key == self._last_debug_snapshot_key:
            return
        self._last_debug_snapshot_at = now
        self._last_debug_snapshot_key = key
        self._log_mpv_snapshot(
            "mpv.local_fullscreen_snapshot" if is_fullscreen else "mpv.local_window_snapshot",
            "debug",
            position=float(position or 0.0),
            duration=duration,
            frame=frame,
        )

    def _recover_video_render_stall(self, position):
        if self._video_stall_recovering:
            return
        channel = dict(self.current_channel or {})
        if not channel:
            return
        if channel.get("_ForceLocalCompat"):
            self._video_stall_recovering = True
            self._emit_failure(
                "video-stall",
                "本地视频画面渲染已停止，但音频/进度仍在继续。已尝试兼容渲染恢复仍未成功，建议切换本地渲染模式或开启兼容/安全启动模式后重试。",
            )
            return
        self._video_stall_recovering = True
        start_position = max(0.0, float(position or 0.0) - 1.0)
        channel["_ForceLocalCompat"] = True
        channel["_StartPosition"] = start_position
        trace_id = str(channel.get("_TraceId") or "")
        log_event(
            "mpv.video_render_stall",
            "error",
            trace_id=trace_id,
            channel=channel,
            position=start_position,
            renderer_profile=getattr(self._native_player, "renderer_profile", ""),
            renderer_options=getattr(self._native_player, "renderer_options", {}),
            hwdec_current=self.player.get_property("hwdec-current") if self.player else None,
            video_codec=self.player.get_property("video-codec-name") if self.player else None,
            video_params=self.player.video_params if self.player else {},
            snapshot=self._safe_mpv_debug_snapshot(),
        )
        self.status_changed.emit("检测到本地视频画面渲染停滞，正在切换到软件解码兼容模式并从当前位置恢复...")
        self._emit_loading_state(True)
        QTimer.singleShot(0, lambda channel=channel: self.play_channel(channel, _reload=True))

    def set_quality(self, key):
        valid = {item[0] for item in self.QUALITY_PRESETS}
        if key not in valid or key == self._quality:
            return
        self._quality = key
        self._auto_downgraded = False
        self.quality_changed.emit(self._quality)
        if self.current_channel is not None:
            name = next((n for k, n, _s, _v in self.QUALITY_PRESETS if k == key), key)
            self.status_changed.emit(f"已切换清晰度：{name}")
            self.play_channel(self.current_channel, _reload=True)

    def get_quality(self):
        return self._quality

    def play_channel(self, channel, _reload=False):
        self._play_request_id += 1
        request_id = self._play_request_id
        self._cancel_pending_resolvers()
        self._reset_player_state(channel, reload=_reload)
        raw_stream_url = clean_media_url((channel or {}).get("Manifest") or "")
        raw_stream_name = (channel or {}).get("Name") or "Unnamed Channel"
        raw_stream_format = self._detect_stream_format(raw_stream_url, channel)
        self._start_loading_for_channel(channel, raw_stream_format)

        if raw_stream_format != "local" and not is_local_media_channel(channel):
            self._update_loading_text_now("正在检测直播链接...")
            self._start_resolve_worker(request_id, channel, raw_stream_name, reload=_reload)
            return

        if not self._initialize_player_or_fail(channel):
            return

        local_channel = dict(channel or {})
        self.current_channel = local_channel
        self._static_tracks = self._extract_static_tracks(local_channel)
        self._emit_tracks_changed(force=True)

        stream_name = local_channel.get("Name") or raw_stream_name
        try:
            self._load_channel_into_player(local_channel, stream_name)
        except Exception as exc:
            self._stop_startup_watchers()
            self._emit_loading_state(False)
            self.playback_failed.emit(
                {
                    "kind": "mpv",
                    "code": "loadfile",
                    "detail": f"[{self._player_backend}] {exc}",
                    "url": local_channel.get("Manifest", ""),
                    "name": stream_name,
                    "failure_stage": "mpv",
                    "failure_action": "local-failed",
                }
            )

    def stop(self):
        self._play_request_id += 1
        self._cancel_pending_resolvers()
        self._stop_startup_watchers()
        self._single_click_timer.stop()
        self.progress_timer.stop()
        if self.player is None:
            self.status_changed.emit("已停止播放。")
            self._emit_loading_state(False)
            return
        player = self.player
        try:
            if is_local_media_channel(self.current_channel or {}):
                self._log_mpv_snapshot("mpv.stop_requested", "info")
        except Exception:
            pass
        self.player = None
        try:
            stopped_handle = player.detach_handle()
        except Exception:
            stopped_handle = getattr(player, "handle", None)
        self.status_changed.emit("已停止播放。")
        self._emit_loading_state(False)
        self._native_player.destroy_handle_async(stopped_handle, delay_ms=0, stop_first=True)

    def _toggle_pause_from_video_click(self):
        if time.monotonic() < self._suppress_click_pause_until:
            return
        if self.player is not None:
            self.toggle_pause()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.player is not None:
            if time.monotonic() >= self._suppress_click_pause_until:
                self._single_click_timer.start()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self._single_click_timer.stop()
        if event.button() == Qt.LeftButton:
            self._suppress_click_pause_until = time.monotonic() + 0.45
            self.fullscreen_toggle_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _update_progress(self):
        if self.player is None:
            return
        try:
            duration = self.player.get_property("duration")
            position = self.player.get_property("time-pos")
            self.progress_changed.emit(float(position or 0.0), duration)
            self.duration_changed.emit(duration)
            self._maybe_log_runtime_snapshot(float(position or 0.0), duration)
            self._check_video_render_stall(float(position or 0.0), duration)
            finished = self._local_media_is_finished()
            self.pause_changed.emit(True if finished else bool(self.player["pause"]))
            if finished and not self._finish_announced:
                self._finish_announced = True
                self.local_media_finished.emit(dict(self.current_channel or {}))
            self._refresh_runtime_tracks()
        except Exception:
            pass


class PlayerPanel(QFrame):
    channel_play_requested = Signal(dict)
    stop_requested = Signal()
    open_external_requested = Signal()
    open_external_with_browser_requested = Signal()
    playback_failed = Signal(dict)
    top_edge_entered = Signal()
    left_edge_entered = Signal()
    right_edge_entered = Signal()
    fullscreen_toggle_requested = Signal()
    menu_requested = Signal()
    detail_requested = Signal()
    load_epg_requested = Signal()
    download_epg_requested = Signal()
    prev_channel_requested = Signal()
    next_channel_requested = Signal()
    loading_overlay_raised = Signal()
    local_media_finished = Signal(dict)
    playback_progress_changed = Signal(float, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playerPanel")
        self._current_title = "未开始播放"
        self._channels = []
        self._filtered_channels = []
        self._triggers_enabled = False
        self._controls_visible = False
        self._controls_suppressed = False
        self._playback_active = False
        self._last_cursor_pos = None

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setSpacing(10)
        root_layout.addLayout(header_row)

        self.panel_title = QLabel("播放器")
        self.panel_title.setObjectName("panelTitle")
        header_row.addWidget(self.panel_title)

        self.state_badge = QLabel("待机")
        self.state_badge.setObjectName("stateBadge")
        self.state_badge.setAlignment(Qt.AlignCenter)
        self.state_badge.setMinimumWidth(110)
        header_row.addWidget(self.state_badge)
        header_row.addStretch(1)

        self.stop_button = QPushButton("停止")
        self.browser_button = QPushButton("默认浏览器播放")
        self.choose_browser_button = QPushButton("选择浏览器播放")
        header_row.addWidget(self.stop_button)
        header_row.addWidget(self.browser_button)
        header_row.addWidget(self.choose_browser_button)

        self.info_label = QLabel("在左侧选择频道即可开始播放，内置播放器使用 libmpv。")
        self.info_label.setObjectName("sectionLabel")
        self.info_label.setWordWrap(True)
        root_layout.addWidget(self.info_label)

        self.warning_label = QLabel()
        self.warning_label.setObjectName("warningLabel")
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        root_layout.addWidget(self.warning_label)

        content_row = QHBoxLayout()
        content_row.setSpacing(14)
        root_layout.addLayout(content_row, 1)

        self.channel_side = QFrame()
        self.channel_side.setObjectName("summaryCard")
        side_layout = QVBoxLayout(self.channel_side)
        side_layout.setContentsMargins(14, 14, 14, 14)
        side_layout.setSpacing(10)

        side_title = QLabel("频道")
        side_title.setObjectName("panelTitle")
        side_layout.addWidget(side_title)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索频道名称...")
        side_layout.addWidget(self.search_input)

        self.channel_list = QListWidget()
        side_layout.addWidget(self.channel_list, 1)
        self.channel_side.setMinimumWidth(280)
        self.channel_side.setMaximumWidth(340)
        content_row.addWidget(self.channel_side, 0)

        player_host = QFrame()
        player_host.setObjectName("playerHost")
        player_layout = QVBoxLayout(player_host)
        player_layout.setContentsMargins(0, 0, 0, 0)
        player_layout.setSpacing(12)
        content_row.addWidget(player_host, 1)

        self.title_value = QLabel(self._current_title)
        self.title_value.setObjectName("heroTitle")
        self.title_value.setWordWrap(True)
        player_layout.addWidget(self.title_value)

        self.video_stack = QStackedWidget()
        self.video_stack.setObjectName("videoStack")
        self.placeholder_widget = QWidget()
        self.placeholder_widget.setObjectName("placeholderWidget")
        self.placeholder_widget.setStyleSheet("#placeholderWidget { background-color: #000000; }")
        placeholder_layout = QVBoxLayout(self.placeholder_widget)
        placeholder_layout.setContentsMargins(0, 0, 0, 0)
        placeholder_layout.addStretch(1)
        self.placeholder_logo = QLabel(self.placeholder_widget)
        self.placeholder_logo.setAlignment(Qt.AlignCenter)
        self.placeholder_logo.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        logo_pixmap = QPixmap(resource_path("docs/assets/icons/iptv-icon-02-signal-orbit-256.png"))
        if not logo_pixmap.isNull():
            self.placeholder_logo.setPixmap(logo_pixmap)
        placeholder_layout.addWidget(self.placeholder_logo, 0, Qt.AlignHCenter | Qt.AlignVCenter)
        placeholder_layout.addStretch(1)
        self.placeholder_widget.installEventFilter(self)
        self.video_stack.addWidget(self.placeholder_widget)
        self.mpv_widget = None

        self.video_stack_host = QFrame()
        self.video_stack_host.setObjectName("mpvViewport")
        self.video_stack_host.installEventFilter(self)
        video_host_layout = QVBoxLayout(self.video_stack_host)
        video_host_layout.setContentsMargins(0, 0, 0, 0)
        video_host_layout.setSpacing(0)
        video_host_layout.addWidget(self.video_stack, 1)
        player_layout.addWidget(self.video_stack_host, 1)

        self.top_edge = HoverZone(self.video_stack_host)
        self.top_edge.entered.connect(self.top_edge_entered.emit)
        self.top_edge.hide()

        self.left_edge = HoverZone(self.video_stack_host)
        self.left_edge.entered.connect(self.left_edge_entered.emit)
        self.left_edge.hide()

        self.right_edge = HoverZone(self.video_stack_host)
        self.right_edge.entered.connect(self.right_edge_entered.emit)
        self.right_edge.hide()

        self.loading_overlay = QFrame(self.video_stack_host)
        self.loading_overlay.setObjectName("loadingOverlay")
        self.loading_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        overlay_layout = QVBoxLayout(self.loading_overlay)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.addStretch(1)
        spinner_wrap = QVBoxLayout()
        spinner_wrap.setSpacing(12)
        self.spinner = SpinnerWidget(self.loading_overlay)
        spinner_wrap.addWidget(self.spinner, 0, Qt.AlignHCenter)
        self.loading_label = QLabel("正在加载内容...")
        self.loading_label.setObjectName("heroTitle")
        spinner_wrap.addWidget(self.loading_label, 0, Qt.AlignHCenter)
        overlay_layout.addLayout(spinner_wrap)
        overlay_layout.addStretch(1)
        self.loading_overlay.hide()

        self.top_bar = PlayerTopBar(self.video_stack_host)
        self.bottom_bar = PlayerBottomBar(self.video_stack_host)
        self.top_bar.hide()
        self.bottom_bar.hide()
        self.top_bar.menu_clicked.connect(self.menu_requested.emit)
        self.top_bar.detail_clicked.connect(self.detail_requested.emit)
        self.top_bar.stop_clicked.connect(self.stop_requested.emit)
        self.top_bar.fullscreen_clicked.connect(self.fullscreen_toggle_requested.emit)
        self.top_bar.load_epg_clicked.connect(self.load_epg_requested.emit)
        self.top_bar.download_epg_clicked.connect(self.download_epg_requested.emit)
        self.bottom_bar.prev_channel.connect(self.prev_channel_requested.emit)
        self.bottom_bar.next_channel.connect(self.next_channel_requested.emit)
        self.bottom_bar.menu_requested.connect(self.menu_requested.emit)
        self.bottom_bar.stop_requested.connect(self.stop_requested.emit)
        self.bottom_bar.fullscreen_requested.connect(self.fullscreen_toggle_requested.emit)

        self._controls_cursor_timer = QTimer(self)
        self._controls_cursor_timer.setInterval(250)
        self._controls_cursor_timer.timeout.connect(self._poll_cursor)
        self._controls_hide_timer = QTimer(self)
        self._controls_hide_timer.setSingleShot(True)
        self._controls_hide_timer.timeout.connect(self._hide_controls)

        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(self._do_filter)

        if not NATIVE_MPV_AVAILABLE:
            self.info_label.setText(f"libmpv 当前不可用：{NATIVE_MPV_ERROR or '缺少原生 libmpv DLL'}")

        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.browser_button.clicked.connect(self.open_external_requested.emit)
        self.choose_browser_button.clicked.connect(self.open_external_with_browser_requested.emit)
        self.search_input.textChanged.connect(self._schedule_filter)
        self.channel_list.itemClicked.connect(self._on_channel_clicked)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
            if watched is self.placeholder_widget or watched is self.video_stack_host:
                self.fullscreen_toggle_requested.emit()
                return True
        return super().eventFilter(watched, event)

    def _ensure_mpv_widget(self):
        if self.mpv_widget is not None:
            return
        self.mpv_widget = MpvVideoWidget(self.video_stack)
        self.video_stack.addWidget(self.mpv_widget)
        self.video_stack.setCurrentWidget(self.mpv_widget)

        mw = self.mpv_widget
        mw.playback_started.connect(self._on_playback_started)
        mw.playback_failed.connect(self._on_playback_failed)
        mw.status_changed.connect(self.info_label.setText)
        mw.loading_changed.connect(self.set_loading)
        mw.loading_text_changed.connect(self.loading_label.setText)
        mw.fullscreen_toggle_requested.connect(self.fullscreen_toggle_requested.emit)
        mw.progress_changed.connect(self.bottom_bar.update_progress)
        mw.progress_changed.connect(self.playback_progress_changed.emit)
        mw.duration_changed.connect(self._on_duration_changed)
        mw.tracks_changed.connect(self.top_bar.populate_tracks)
        mw.pause_changed.connect(lambda paused: self.bottom_bar.set_playing(not paused))
        mw.volume_state_changed.connect(lambda _volume, muted: self.bottom_bar.set_muted(muted))
        mw.quality_changed.connect(self.top_bar.set_current_quality)
        mw.local_media_finished.connect(self.local_media_finished.emit)

        self.top_bar.quality_selected.connect(mw.set_quality)
        self.top_bar.video_track_selected.connect(mw.set_video_track)
        self.top_bar.audio_track_selected.connect(mw.set_audio_track)
        self.top_bar.subtitle_track_selected.connect(mw.set_subtitle_track)
        self.top_bar.set_current_quality(mw.get_quality())
        self.bottom_bar.play_pause_toggled.connect(mw.toggle_pause)
        self.bottom_bar.play_requested.connect(lambda: mw.set_pause(False))
        self.bottom_bar.pause_requested.connect(lambda: mw.set_pause(True))
        self.bottom_bar.skip_requested.connect(mw.seek_relative)
        self.bottom_bar.seek_requested.connect(mw.seek_fraction)
        self.bottom_bar.volume_changed.connect(mw.set_volume)
        self.bottom_bar.mute_toggled.connect(mw.toggle_mute)
        self.bottom_bar.speed_changed.connect(mw.set_playback_speed)

        if not self._controls_cursor_timer.isActive():
            self._controls_cursor_timer.start()

    def enable_immersive_mode(self):
        self.channel_side.setVisible(False)
        for widget in (
            self.panel_title,
            self.state_badge,
            self.stop_button,
            self.browser_button,
            self.choose_browser_button,
            self.info_label,
            self.warning_label,
            self.title_value,
        ):
            widget.setVisible(False)
            widget.setFixedHeight(0)
        layout = self.layout()
        if layout is not None:
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
        self._set_triggers_enabled(True)
        self._enable_triggers_interaction()

    def seek_absolute(self, seconds):
        """Seek current media to an absolute position in seconds."""
        if self.mpv_widget is not None:
            self.mpv_widget.seek_absolute(seconds)

    def current_position(self):
        if self.mpv_widget is None or self.mpv_widget.player is None:
            return 0.0
        try:
            return float(self.mpv_widget.player.get_property("time-pos") or 0.0)
        except Exception:
            return 0.0

    def use_local_fullscreen_safe_renderer(self, enabled):
        if self.mpv_widget is None or self.mpv_widget.current_channel is None:
            return False
        channel = dict(self.mpv_widget.current_channel or {})
        if not is_local_media_channel(channel):
            return False
        enabled = bool(enabled)
        if bool(channel.get("_ForceLocalFullscreenSafe")) == enabled:
            return False
        position = self.current_position()
        channel["_ForceLocalFullscreenSafe"] = enabled
        channel["_StartPosition"] = max(0.0, position - 0.8) if position > 0 else 0.0
        self.mpv_widget.status_changed.emit(
            "正在切换本地全屏安全渲染..." if enabled else "正在恢复本地窗口渲染..."
        )
        self.mpv_widget.play_channel(channel, _reload=True)
        return True

    def _set_triggers_enabled(self, enabled):
        self._triggers_enabled = enabled
        if enabled:
            self._reposition_triggers()
            self.top_edge.show()
            self.left_edge.show()
            self.right_edge.show()
            self._raise_triggers()
        else:
            self.top_edge.hide()
            self.left_edge.hide()
            self.right_edge.hide()

    def _raise_triggers(self):
        self.top_edge.raise_()
        self.left_edge.raise_()
        self.right_edge.raise_()

    def _reposition_triggers(self):
        width = self.video_stack_host.width()
        height = self.video_stack_host.height()
        self.top_edge.setGeometry(0, 0, width, 20)
        self.left_edge.setGeometry(0, 0, 20, height)
        self.right_edge.setGeometry(max(0, width - 20), 0, 20, height)

    def _disable_triggers_interaction(self):
        self.top_edge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.left_edge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.right_edge.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def _enable_triggers_interaction(self):
        self.top_edge.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.left_edge.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.right_edge.setAttribute(Qt.WA_TransparentForMouseEvents, False)

    def set_controls_suppressed(self, suppressed: bool):
        """临时抑制播放控制条自动显示，避免覆盖侧边交互面板。"""
        self._controls_suppressed = bool(suppressed)
        if self._controls_suppressed:
            self._controls_hide_timer.stop()
            self._hide_controls()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.loading_overlay.setGeometry(self.video_stack_host.rect())
        if self._triggers_enabled:
            self._reposition_triggers()
            self._raise_triggers()
        if self._controls_visible:
            self._position_controls()

    def mouseMoveEvent(self, event):
        if self._playback_active and not self._controls_suppressed:
            self._show_controls()
        super().mouseMoveEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self._triggers_enabled:
            QTimer.singleShot(0, self._reposition_triggers)
            QTimer.singleShot(100, self._raise_triggers)

    def _position_controls(self):
        host = self.video_stack_host
        width, height = host.width(), host.height()
        top_height = max(1, self.top_bar.sizeHint().height())
        bottom_height = max(
            1,
            self.bottom_bar.minimumHeight(),
            self.bottom_bar.height(),
        )
        self.top_bar.setGeometry(0, 0, width, top_height)
        side_margin = 24 if width >= 900 else 8
        bottom_margin = 16 if height >= 420 else 8
        self.bottom_bar.setGeometry(
            side_margin,
            max(0, height - bottom_height - bottom_margin),
            max(240, width - side_margin * 2),
            bottom_height,
        )

    def _poll_cursor(self):
        if self.mpv_widget is None:
            return
        if not self._playback_active:
            return
        if self._controls_suppressed:
            if self._controls_visible:
                self._hide_controls()
            return
        host = self.video_stack_host
        global_pos = QCursor.pos()
        local_pos = host.mapFromGlobal(global_pos)
        inside = host.rect().contains(local_pos)
        moved = global_pos != self._last_cursor_pos
        self._last_cursor_pos = global_pos

        over_bar = False
        if self._controls_visible:
            over_bar = self.top_bar.geometry().contains(local_pos) or self.bottom_bar.geometry().contains(local_pos)
        if inside and (moved or over_bar):
            self._show_controls()

    def _show_controls(self):
        if self._controls_suppressed:
            if self._controls_visible:
                self._hide_controls()
            return
        self._position_controls()
        self.top_bar.show()
        self.bottom_bar.show()
        self.top_bar.raise_()
        self.bottom_bar.raise_()
        self._controls_visible = True
        self._controls_hide_timer.start(3000)

    def _hide_controls(self):
        self.top_bar.hide()
        self.bottom_bar.hide()
        self._controls_visible = False

    def _on_duration_changed(self, duration):
        has_duration = bool(duration) and duration and duration > 0
        self.bottom_bar.set_duration_mode(bool(has_duration))

    def apply_language(self):
        self.top_bar.apply_language()

    def _on_playback_failed(self, error_info):
        self.playback_failed.emit(error_info)

    def _set_channel_title(self, channel):
        name = (channel or {}).get("Name") or "未命名频道"
        group = (channel or {}).get("GroupTitle") or (channel or {}).get("Category") or ""
        self._current_title = name
        self.title_value.setText(name)
        self.top_bar.set_title(name, group)
        self.select_channel_by_name(name)
        return name

    def _on_playback_started(self, channel):
        self._playback_active = True
        self._set_channel_title(channel)
        self.state_badge.setText("播放中")
        if self.mpv_widget is not None:
            self.video_stack.setCurrentWidget(self.mpv_widget)
        self.set_loading(False)
        self.warning_label.setVisible(False)
        self.bottom_bar.set_playing(True)
        self._show_controls()

    def set_channels(self, channels):
        self._channels = list(channels)
        self._do_filter()

    def get_selected_channel(self):
        row = self.channel_list.currentRow()
        if 0 <= row < len(self._filtered_channels):
            return self._filtered_channels[row]
        return None

    def _schedule_filter(self):
        self._filter_timer.stop()
        self._filter_timer.start(300)

    def _do_filter(self):
        query = self.search_input.text().strip().lower()
        self._filtered_channels = []
        self.channel_list.clear()
        for channel in self._channels:
            name = str(channel.get("Name") or "未命名频道")
            if query and query not in name.lower():
                continue
            self._filtered_channels.append(channel)
            self.channel_list.addItem(QListWidgetItem(name))

    def _on_channel_clicked(self, item):
        row = self.channel_list.row(item)
        if 0 <= row < len(self._filtered_channels):
            self.channel_play_requested.emit(self._filtered_channels[row])

    def select_channel_by_name(self, name):
        for row in range(self.channel_list.count()):
            item = self.channel_list.item(row)
            if item and item.text() == name:
                self.channel_list.setCurrentRow(row)
                break

    def set_loading(self, loading):
        if loading:
            self.spinner.start()
            self.loading_overlay.setGeometry(self.video_stack_host.rect())
            self.loading_overlay.show()
            self.loading_overlay.raise_()
            self._raise_triggers()
            self.loading_overlay_raised.emit()
        else:
            self.spinner.stop()
            self.loading_overlay.hide()
            self.loading_label.setText("正在加载内容...")

    def play_channel(self, channel, _reload=False):
        self._set_channel_title(channel)
        self.state_badge.setText("加载中")
        self.bottom_bar.reset_speed()
        self._ensure_mpv_widget()
        if self.mpv_widget is not None:
            initial_tracks = self.mpv_widget._extract_static_tracks(channel)
            self.top_bar.populate_tracks(initial_tracks)
            self.mpv_widget.play_channel(channel, _reload=_reload)

    def stop_playback(self):
        self._playback_active = False
        if self.mpv_widget is not None:
            self.mpv_widget.stop()
        self.video_stack.setCurrentWidget(self.placeholder_widget)
        self.top_bar.hide()
        self.bottom_bar.hide()
        self.bottom_bar.reset_speed()
        self._controls_visible = False
        self._controls_hide_timer.stop()
        self.state_badge.setText("待机")
        self.set_loading(False)
        self.warning_label.setVisible(False)

    def set_running_state(self, running, _url=""):
        if not running and self.state_badge.text() != "播放中":
            self.state_badge.setText("待机")

    def set_message(self, message):
        self.info_label.setText(message)

    def clear(self):
        self.stop_playback()
