"""Window chrome helpers for a consistent dark glass look."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QSizeGrip, QWidget

from utils.app_paths import resource_path
from utils.compatibility_settings import should_install_custom_chrome


_DWMWA_USE_IMMERSIVE_DARK_MODE_LEGACY = 19
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36

_CAPTION_COLOR = "#202938"
_TEXT_COLOR = "#F2F6FF"
_BORDER_COLOR = "#78B4FF"
_TITLE_ICON_PATH = "docs/assets/icons/iptv-icon-02-signal-orbit-24.png"
_TITLE_BAR_HEIGHT = 32
_TITLE_BUTTON_WIDTH = 42
_WM_NCHITTEST = 0x0084
_HTLEFT = 10
_HTRIGHT = 11
_HTTOP = 12
_HTTOPLEFT = 13
_HTTOPRIGHT = 14
_HTBOTTOM = 15
_HTBOTTOMLEFT = 16
_HTBOTTOMRIGHT = 17


def _hex_to_colorref(value: str) -> int:
    """Convert #RRGGBB into a Windows COLORREF integer."""
    clean = value.strip().lstrip("#")
    if len(clean) != 6:
        return 0
    red = int(clean[0:2], 16)
    green = int(clean[2:4], 16)
    blue = int(clean[4:6], 16)
    return (blue << 16) | (green << 8) | red


def _set_dwm_attribute(hwnd: int, attribute: int, value: int) -> bool:
    """Set a DWM attribute and ignore unsupported Windows builds."""
    try:
        data = wintypes.DWORD(value)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            wintypes.DWORD(attribute),
            ctypes.byref(data),
            ctypes.sizeof(data),
        )
        return result == 0
    except Exception:
        return False


def apply_glass_window_chrome(widget: QWidget | None) -> bool:
    """Apply a dark blue native title bar to a top-level widget on Windows."""
    if sys.platform != "win32" or widget is None:
        return False
    if not widget.isWindow():
        return False

    try:
        hwnd = int(widget.winId())
    except Exception:
        return False
    if not hwnd:
        return False

    applied = False
    applied |= _set_dwm_attribute(hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, 1)
    applied |= _set_dwm_attribute(hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE_LEGACY, 1)
    applied |= _set_dwm_attribute(hwnd, _DWMWA_CAPTION_COLOR, _hex_to_colorref(_CAPTION_COLOR))
    applied |= _set_dwm_attribute(hwnd, _DWMWA_TEXT_COLOR, _hex_to_colorref(_TEXT_COLOR))
    applied |= _set_dwm_attribute(hwnd, _DWMWA_BORDER_COLOR, _hex_to_colorref(_BORDER_COLOR))
    if applied:
        widget.setProperty("_glass_window_chrome_applied", True)
    return applied


class _WindowGlyphButton(QPushButton):
    """Small custom painted title-bar control button."""

    def __init__(self, glyph: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._glyph = glyph
        self.setFixedSize(_TITLE_BUTTON_WIDTH, _TITLE_BAR_HEIGHT)
        self.setCursor(Qt.ArrowCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFlat(True)
        self.setStyleSheet("background: transparent; border: none; padding: 0;")

    def paintEvent(self, event) -> None:  # type: ignore[override]
        """Paint a unified glass title-bar button."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        if self.underMouse() or self.isDown():
            if self._glyph == "close":
                fill = QColor(220, 75, 85, 190 if self.isDown() else 155)
            else:
                fill = QColor(120, 180, 255, 62 if self.isDown() else 44)
            painter.setPen(Qt.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(rect.adjusted(4, 4, -4, -4), 7, 7)

        color = QColor("#F2F6FF")
        if self._glyph == "close" and self.underMouse():
            color = QColor("#FFFFFF")
        pen = QPen(color, 1.7)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)

        cx = rect.center().x()
        cy = rect.center().y()
        if self._glyph == "minimize":
            painter.drawLine(cx - 6, cy + 5, cx + 6, cy + 5)
        elif self._glyph == "maximize":
            painter.drawRect(cx - 6, cy - 6, 12, 12)
        elif self._glyph == "restore":
            painter.drawRect(cx - 4, cy - 7, 10, 10)
            painter.drawRect(cx - 7, cy - 4, 10, 10)
        else:
            painter.drawLine(cx - 5, cy - 5, cx + 5, cy + 5)
            painter.drawLine(cx + 5, cy - 5, cx - 5, cy + 5)

        painter.end()

    def set_restore_mode(self, enabled: bool) -> None:
        """Switch the maximize button between maximize and restore glyphs."""
        if self._glyph in {"maximize", "restore"}:
            self._glyph = "restore" if enabled else "maximize"
            self.update()


class _TitleLogo(QWidget):
    """Shared title-bar app mark."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self._pixmap = QPixmap(resource_path(_TITLE_ICON_PATH))

    def paintEvent(self, event) -> None:  # type: ignore[override]
        """Paint the shared title icon, falling back to a tiny vector mark."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self._pixmap.isNull():
            painter.drawPixmap(self.rect(), self._pixmap)
            painter.end()
            return
        rect = self.rect().adjusted(2, 2, -2, -2)
        painter.setPen(QPen(QColor(120, 180, 255, 190), 1.2))
        painter.setBrush(QColor(14, 21, 31, 230))
        painter.drawRoundedRect(rect, 3, 3)
        painter.setPen(QPen(QColor("#EAF3FF"), 1.3))
        painter.drawLine(6, 5, 10, 5)
        painter.drawLine(5, 8, 11, 8)
        painter.drawLine(6, 11, 10, 11)
        painter.end()


class GlassTitleBar(QFrame):
    """Application-painted glass title bar for frameless top-level widgets."""

    def __init__(self, window: QWidget, show_window_controls: bool = False) -> None:
        super().__init__(window)
        self._window = window
        self._drag_pos: QPoint | None = None
        self._maximize_button: _WindowGlyphButton | None = None
        self.setObjectName("glassTitleBar")
        self.setFixedHeight(_TITLE_BAR_HEIGHT)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setStyleSheet(
            """
            QFrame#glassTitleBar {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(58, 68, 86, 245),
                    stop:0.55 rgba(34, 43, 58, 246),
                    stop:1 rgba(19, 25, 34, 248)
                );
                border-bottom: 1px solid rgba(120, 180, 255, 118);
            }
            QLabel#glassTitleLabel {
                color: #f3f7ff;
                font-size: 13px;
                font-weight: 700;
                background: transparent;
            }
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(8)

        self.logo = _TitleLogo(self)
        layout.addWidget(self.logo, 0, Qt.AlignVCenter)

        self.title_label = QLabel(window.windowTitle(), self)
        self.title_label.setObjectName("glassTitleLabel")
        self.title_label.setTextInteractionFlags(Qt.NoTextInteraction)
        layout.addWidget(self.title_label, 1, Qt.AlignVCenter)

        if show_window_controls:
            minimize_button = _WindowGlyphButton("minimize", self)
            minimize_button.clicked.connect(window.showMinimized)
            layout.addWidget(minimize_button)

            self._maximize_button = _WindowGlyphButton("maximize", self)
            self._maximize_button.clicked.connect(self._toggle_maximized)
            layout.addWidget(self._maximize_button)

        close_button = _WindowGlyphButton("close", self)
        close_button.clicked.connect(window.close)
        layout.addWidget(close_button)

    def _is_window_button_at(self, pos: QPoint) -> bool:
        """Return whether a title-bar position belongs to a window control button."""
        child = self.childAt(pos)
        while child is not None:
            if isinstance(child, _WindowGlyphButton):
                return True
            child = child.parentWidget()
        return False

    def set_title(self, title: str) -> None:
        """Update displayed window title."""
        self.title_label.setText(title)

    def sync_window_state(self) -> None:
        """Refresh maximize/restore glyph from the parent window state."""
        if self._maximize_button is not None:
            self._maximize_button.set_restore_mode(self._window.isMaximized())

    def _toggle_maximized(self) -> None:
        """Toggle the parent top-level window between maximized and normal."""
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()
        self.sync_window_state()

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        """Maximize/restore main windows on title-bar double click."""
        if self._is_window_button_at(event.position().toPoint()):
            super().mouseDoubleClickEvent(event)
            return
        if event.button() == Qt.LeftButton and self._maximize_button is not None:
            self._toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        """Start dragging the frameless parent window."""
        if self._is_window_button_at(event.position().toPoint()):
            super().mousePressEvent(event)
            return
        if event.button() == Qt.LeftButton:
            global_pos = event.globalPosition().toPoint()
            self._drag_pos = global_pos - self._window.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        """Move the frameless parent window while dragging."""
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            if self._window.isMaximized() or self._window.isFullScreen():
                return
            self._window.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        """Finish dragging the frameless parent window."""
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class _CustomChromeEventFilter(QObject):
    """Keep the custom title bar geometry and margins in sync."""

    def __init__(self, window: QWidget, title_bar: GlassTitleBar, grip: QSizeGrip | None) -> None:
        super().__init__(window)
        self._window = window
        self._title_bar = title_bar
        self._grip = grip

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """React to resize, title changes and full-screen state changes."""
        window = getattr(self, "_window", None)
        title_bar = getattr(self, "_title_bar", None)
        if window is None or title_bar is None:
            return False
        if watched is window:
            if event.type() in (QEvent.Resize, QEvent.Show, QEvent.WindowStateChange):
                self.sync()
            elif event.type() == QEvent.WindowTitleChange:
                title_bar.set_title(window.windowTitle())
        return False

    def sync(self) -> None:
        """Apply current title-bar placement and visibility."""
        window = getattr(self, "_window", None)
        title_bar = getattr(self, "_title_bar", None)
        if window is None or title_bar is None:
            return

        fullscreen = window.isFullScreen()
        width = max(0, window.width())
        title_bar.setGeometry(0, 0, width, _TITLE_BAR_HEIGHT)
        title_bar.setVisible(not fullscreen)
        title_bar.sync_window_state()
        if fullscreen:
            window.setContentsMargins(0, 0, 0, 0)
        else:
            window.setContentsMargins(0, _TITLE_BAR_HEIGHT, 0, 0)
            title_bar.raise_()

        grip = getattr(self, "_grip", None)
        if grip is not None:
            grip_size = grip.sizeHint()
            grip.setGeometry(
                window.width() - grip_size.width(),
                window.height() - grip_size.height(),
                grip_size.width(),
                grip_size.height(),
            )
            grip.setVisible(not fullscreen and not window.isMaximized())
            grip.raise_()


def install_custom_window_chrome(
    widget: QWidget | None,
    *,
    show_window_controls: bool = False,
    resizable: bool = True,
) -> GlassTitleBar | None:
    """Install a custom glass title bar on a top-level widget."""
    if widget is None:
        return None
    if not should_install_custom_chrome():
        return None
    existing = getattr(widget, "_glass_custom_title_bar", None)
    if existing is not None:
        widget._glass_custom_chrome_resizable = bool(resizable)
        existing.set_title(widget.windowTitle())
        return existing

    widget.setWindowFlag(Qt.FramelessWindowHint, True)
    title_bar = GlassTitleBar(widget, show_window_controls=show_window_controls)
    grip = QSizeGrip(widget) if resizable else None
    if grip is not None:
        grip.setStyleSheet("background: transparent;")

    event_filter = _CustomChromeEventFilter(widget, title_bar, grip)
    widget.installEventFilter(event_filter)
    widget._glass_custom_title_bar = title_bar
    widget._glass_custom_chrome_filter = event_filter
    widget._glass_custom_chrome_resizable = bool(resizable)
    widget._glass_size_grip = grip
    event_filter.sync()
    return title_bar


def handle_frameless_native_event(
    widget: QWidget,
    event_type,
    message,
    *,
    border_width: int = 8,
) -> tuple[bool, int]:
    """Provide invisible resize borders for frameless Windows top-level widgets."""
    if getattr(widget, "_glass_custom_title_bar", None) is None:
        return False, 0
    if not getattr(widget, "_glass_custom_chrome_resizable", True):
        return False, 0
    if sys.platform != "win32" or widget.isFullScreen() or widget.isMaximized():
        return False, 0
    try:
        msg = wintypes.MSG.from_address(int(message))
    except Exception:
        return False, 0
    if msg.message != _WM_NCHITTEST:
        return False, 0

    x = ctypes.c_short(msg.lParam & 0xFFFF).value
    y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
    rect = wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(msg.hWnd, ctypes.byref(rect)):
        return False, 0

    left = x <= rect.left + border_width
    right = x >= rect.right - border_width
    top = y <= rect.top + border_width
    bottom = y >= rect.bottom - border_width

    if top and left:
        return True, _HTTOPLEFT
    if top and right:
        return True, _HTTOPRIGHT
    if bottom and left:
        return True, _HTBOTTOMLEFT
    if bottom and right:
        return True, _HTBOTTOMRIGHT
    if left:
        return True, _HTLEFT
    if right:
        return True, _HTRIGHT
    if top:
        return True, _HTTOP
    if bottom:
        return True, _HTBOTTOM
    return False, 0


class _WindowChromeEventFilter(QObject):
    """Apply native glass title-bar coloring whenever top-level widgets appear."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Handle top-level widget show and native handle change events."""
        if event.type() in (QEvent.Show, QEvent.WinIdChange) and isinstance(watched, QWidget):
            if watched.isWindow():
                apply_glass_window_chrome(watched)
        return False


def install_glass_window_chrome(app: QApplication) -> None:
    """Install a small app-wide filter for future dialogs and windows."""
    if sys.platform != "win32":
        return
    if getattr(app, "_glass_window_chrome_filter", None) is not None:
        return
    event_filter = _WindowChromeEventFilter(app)
    app.installEventFilter(event_filter)
    app._glass_window_chrome_filter = event_filter
