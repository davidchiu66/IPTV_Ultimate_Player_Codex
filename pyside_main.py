import os
import sys
import json
import threading
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, qInstallMessageHandler
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from utils.app_paths import ensure_user_data_dirs
from utils.compatibility_settings import configure_compatibility_environment
from utils.logging_utils import CappedLogHandle, app_log_path


# Widevine DLL 搜索缓存
_WIDEVINE_CACHE = None
_WIDEVINE_CACHE_LOCK = threading.Lock()
_SESSION_LOG = None
_ORIGINAL_EXCEPTHOOK = sys.excepthook


class TeeStream:
    """Mirror stdout/stderr to the console and the per-start log file."""

    def __init__(self, stream, log_handle, lock):
        self._stream = stream
        self._log_handle = log_handle
        self._lock = lock
        self.encoding = getattr(stream, "encoding", "utf-8")
        self.errors = getattr(stream, "errors", "replace")

    def write(self, text):
        if not isinstance(text, str):
            text = str(text)
        with self._lock:
            try:
                self._stream.write(text)
                self._stream.flush()
            except Exception:
                pass
            try:
                self._log_handle.write(text)
                self._log_handle.flush()
            except Exception:
                pass
        return len(text)

    def flush(self):
        with self._lock:
            try:
                self._stream.flush()
            except Exception:
                pass
            try:
                self._log_handle.flush()
            except Exception:
                pass

    def isatty(self):
        return bool(getattr(self._stream, "isatty", lambda: False)())


def setup_session_logging():
    """Attach stdout/stderr to the single capped application log file."""
    global _SESSION_LOG
    if _SESSION_LOG is not None:
        return _SESSION_LOG["path"]

    log_path = app_log_path()
    log_handle = CappedLogHandle(log_path)
    lock = threading.RLock()

    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = TeeStream(original_stdout, log_handle, lock)
    sys.stderr = TeeStream(original_stderr, log_handle, lock)

    def excepthook(exc_type, exc_value, exc_traceback):
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)

    def qt_message_handler(mode, context, message):
        try:
            line = f"qt: {message}\n"
            sys.stderr.write(line)
        except Exception:
            pass

    sys.excepthook = excepthook
    qInstallMessageHandler(qt_message_handler)
    os.environ["IPTV_SESSION_LOG_PATH"] = str(log_path)
    _SESSION_LOG = {
        "path": str(log_path),
        "handle": log_handle,
        "stdout": original_stdout,
        "stderr": original_stderr,
    }
    print(f"\n=== session started {datetime.now().isoformat(timespec='seconds')} ===")
    print(f"session log: {log_path}")
    return str(log_path)


def ensure_directories():
    # Runtime data must live under the per-user writable directory. The
    # installation directory can be read-only under Program Files.
    ensure_user_data_dirs()


def _widevine_search_roots():
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    return [
        os.path.join(os.getcwd(), "plugins", "WidevineCdm"),
        os.path.join(os.getcwd(), "plugins", "widevine"),
        os.path.join(os.getcwd(), "widevine"),
        os.path.join(os.getcwd(), "WidevineCdm"),
        os.path.join(os.getcwd(), "widevine_cdm"),
        os.environ.get("PROGRAMFILES", r"C:\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        os.path.join(local_appdata, "Google", "Chrome", "Application"),
        os.path.join(local_appdata, "Microsoft", "Edge", "Application"),
    ]


def _find_widevine_dll():
    """查找 Widevine DLL，使用缓存避免重复扫描文件系统"""
    global _WIDEVINE_CACHE

    with _WIDEVINE_CACHE_LOCK:
        if _WIDEVINE_CACHE is not None:
            return _WIDEVINE_CACHE

        seen = set()
        for root in _widevine_search_roots():
            if not root or not os.path.isdir(root):
                continue
            try:
                for path in Path(root).rglob("widevinecdm.dll"):
                    resolved = str(path)
                    if resolved not in seen:
                        seen.add(resolved)
                        _WIDEVINE_CACHE = resolved
                        return resolved
            except OSError:
                continue

        _WIDEVINE_CACHE = ""
        return ""


def _read_widevine_version(dll_path):
    search_dirs = [
        Path(dll_path).parent,
        Path(dll_path).parent.parent,
        Path(dll_path).parent.parent.parent,
    ]
    for directory in search_dirs:
        manifest_path = directory / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        for key in ("version", "x-cdm-module-versions", "x-cdm-interface-versions"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return data.get("version") or value.strip()
    return ""


def configure_qtwebengine_runtime():
    widevine_path = _find_widevine_dll()
    if not widevine_path:
        os.environ.pop("IPTV_WIDEVINE_PATH", None)
        return

    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
    extra_flags = []
    if "widevine-path" not in flags:
        extra_flags.append(f'--widevine-path="{widevine_path}"')
    if "widevine-cdm-path" not in flags:
        extra_flags.append(f'--widevine-cdm-path="{widevine_path}"')

    widevine_version = _read_widevine_version(widevine_path)
    if widevine_version and "widevine-cdm-version" not in flags:
        extra_flags.append(f'--widevine-cdm-version="{widevine_version}"')

    if extra_flags:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{flags} {' '.join(extra_flags)}".strip()
    os.environ["IPTV_WIDEVINE_PATH"] = widevine_path
    if widevine_version:
        os.environ["IPTV_WIDEVINE_VERSION"] = widevine_version
    else:
        os.environ.pop("IPTV_WIDEVINE_VERSION", None)


def configure_mpv_runtime():
    mpv_dir = os.path.join(os.getcwd(), "plugins", "mpv")
    if not os.path.isdir(mpv_dir):
        return

    path_value = os.environ.get("PATH", "")
    if mpv_dir.lower() not in path_value.lower():
        os.environ["PATH"] = mpv_dir + os.pathsep + path_value

    add_dll_directory = getattr(os, "add_dll_directory", None)
    if callable(add_dll_directory):
        try:
            add_dll_directory(mpv_dir)
        except OSError:
            pass


def run():
    setup_session_logging()
    compatibility = configure_compatibility_environment(sys.argv)
    print(f"compatibility mode: {json.dumps(compatibility, ensure_ascii=False)}")
    ensure_directories()
    configure_qtwebengine_runtime()
    configure_mpv_runtime()

    from ui.main_window import MainWindow
    from utils.app_paths import resource_path

    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)
    app.setApplicationName("IPTV 播放器")
    app.setApplicationDisplayName("IPTV 播放器")
    app.setWindowIcon(QIcon(resource_path("docs/assets/icons/iptv-icon-02-signal-orbit-24.png")))
    window = MainWindow()
    # 使用 show() + center_on_screen() 代替 showMaximized()
    # showMaximized() 会触发多次 resizeEvent，打断覆盖层的滑入动画
    window.show()
    window.center_on_screen()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
