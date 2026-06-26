"""Apple TV style QWidget player control bar.

This module is UI-only. It exposes Qt signals for playback integration and never
talks to libmpv directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QByteArray, QEasingCurve, Property, QRectF, Qt, QPropertyAnimation, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class ControlBarColors:
    """Color constants for the control bar."""

    background_top: str = "#343A43"
    background_bottom: str = "#161C25"
    panel_border: str = "#78B4FF"
    text: str = "#E7EEF7"
    track_empty: str = "#000000"
    progress_fill: str = "#69B2FF"
    volume_fill: str = "#78BAFF"
    handle: str = "#7CC0FF"
    button_hover: str = "#78B4FF"
    button_pressed: str = "#5AA8FF"
    menu_background: str = "#202A39"


@dataclass(frozen=True)
class ControlBarMetrics:
    """Size constants for the control bar."""

    height: int = 120
    radius: int = 20
    margin_x: int = 28
    margin_y: int = 8
    top_spacing: int = 12
    row_spacing: int = 22
    menu_button: int = 44
    full_button: int = 44
    transport_button: int = 38
    volume_button: int = 44
    play_button: int = 56
    transport_group_width: int = 420
    transport_left_inset: int = 62
    top_progress_min_width: int = 520
    progress_track_height: int = 4
    progress_handle_size: int = 12
    volume_width: int = 130
    volume_track_height: int = 4
    volume_handle_size: int = 10
    speed_width: int = 100
    speed_height: int = 42
    font_time: int = 18
    font_speed: int = 16


COLORS = ControlBarColors()
METRICS = ControlBarMetrics()
ANIMATION_MS = 150
SPEED_OPTIONS: tuple[float, ...] = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)


def _keep_widget_alien(widget: QWidget) -> None:
    """Keep overlay controls as non-native child widgets over the mpv host."""
    widget.setAttribute(Qt.WA_NativeWindow, False)
    widget.setAttribute(Qt.WA_DontCreateNativeAncestors, True)
    widget.setAttribute(Qt.WA_PaintOnScreen, False)


SVG_ICONS: dict[str, str] = {
    "playlist": """
        <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
          <circle cx="12" cy="16" r="3.2" fill="white"/>
          <circle cx="12" cy="32" r="3.2" fill="white"/>
          <circle cx="12" cy="48" r="3.2" fill="white"/>
          <path d="M23 16h31M23 32h31M23 48h31" stroke="white" stroke-width="5.6" stroke-linecap="round"/>
        </svg>
    """,
    "settings": """
        <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
          <path d="M32 20a12 12 0 1 0 0 24 12 12 0 0 0 0-24zm0 7a5 5 0 1 1 0 10 5 5 0 0 1 0-10z" fill="white"/>
          <path d="M34.8 7l2.2 7.1c1.4.4 2.8 1 4 1.7l6.7-3.5 5.1 5.1-3.5 6.7c.7 1.3 1.3 2.6 1.7 4l7 2.2v7.3l-7 2.2c-.4 1.4-1 2.8-1.7 4l3.5 6.7-5.1 5.1-6.7-3.5c-1.3.7-2.6 1.3-4 1.7L34.8 61h-7.3l-2.2-7.1c-1.4-.4-2.8-1-4-1.7l-6.7 3.5-5.1-5.1 3.5-6.7c-.7-1.3-1.3-2.6-1.7-4l-7.1-2.2v-7.3l7.1-2.2c.4-1.4 1-2.8 1.7-4l-3.5-6.7 5.1-5.1 6.7 3.5c1.3-.7 2.6-1.3 4-1.7L27.5 7z" fill="none" stroke="white" stroke-width="4.4" stroke-linejoin="round"/>
        </svg>
    """,
    "fullscreen": """
        <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
          <path d="M14 25V14h11M39 14h11v11M14 39v11h11M50 39v11H39" fill="none" stroke="white" stroke-width="5.2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M17 17l15 15M47 17L32 32M17 47l15-15M47 47L32 32" fill="none" stroke="white" stroke-width="4.2" stroke-linecap="round"/>
        </svg>
    """,
    "volume": """
        <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
          <path d="M9 25h14L42 10c2-1.6 5-.2 5 2.4v39.2c0 2.6-3 4-5 2.4L23 39H9z" fill="white"/>
          <path d="M51 23c5.8 5.8 5.8 12.2 0 18" fill="none" stroke="white" stroke-width="4.4" stroke-linecap="round"/>
          <path d="M56 16c10.8 10.8 10.8 21.2 0 32" fill="none" stroke="white" stroke-width="4.4" stroke-linecap="round"/>
        </svg>
    """,
    "mute": """
        <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
          <path d="M10 25h14L45 8v48L24 39H10z" fill="white"/>
          <path d="M51 24l10 16M61 24L51 40" fill="none" stroke="white" stroke-width="5" stroke-linecap="round"/>
        </svg>
    """,
    "previous": """
        <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
          <rect x="14" y="14" width="5" height="36" rx="2.5" fill="white"/>
          <path d="M51 12v40L22 32z" fill="white"/>
        </svg>
    """,
    "next": """
        <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
          <rect x="45" y="14" width="5" height="36" rx="2.5" fill="white"/>
          <path d="M13 12v40l29-20z" fill="white"/>
        </svg>
    """,
    "rewind10": """
        <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
          <path d="M47 9v30L26 24zM27 9v30L6 24z" fill="white"/>
          <text x="32" y="58" text-anchor="middle" font-family="Segoe UI,Arial" font-size="20" fill="#DDE7FF">-10s</text>
        </svg>
    """,
    "forward10": """
        <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
          <path d="M17 9v30l21-15zM37 9v30l21-15z" fill="white"/>
          <text x="32" y="58" text-anchor="middle" font-family="Segoe UI,Arial" font-size="20" fill="#DDE7FF">+10s</text>
        </svg>
    """,
    "play": """
        <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
          <path d="M24 17v30l25-15z" fill="white"/>
        </svg>
    """,
    "pause": """
        <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
          <rect x="21" y="17" width="8" height="30" rx="3" fill="white"/>
          <rect x="35" y="17" width="8" height="30" rx="3" fill="white"/>
        </svg>
    """,
    "stop": """
        <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
          <rect x="20" y="20" width="24" height="24" rx="4" fill="white"/>
        </svg>
    """,
    "arrow_down": """
        <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
          <path d="M16 24l16 16 16-16" fill="none" stroke="white" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
    """,
}


class SvgIcon:
    """Small SVG renderer wrapper."""

    def __init__(self, name: str) -> None:
        """Create an icon renderer by name."""
        self.name = name
        self.renderer = QSvgRenderer(QByteArray(SVG_ICONS[name].encode("utf-8")))

    def paint(self, painter: QPainter, rect: QRectF) -> None:
        """Paint the SVG into the given rect."""
        self.renderer.render(painter, rect)


class SvgIconButton(QWidget):
    """Animated SVG icon button without QPushButton default styling."""

    clicked = Signal()

    def __init__(self, icon: str, diameter: int, parent: QWidget | None = None, circular: bool = False) -> None:
        """Create an SVG button."""
        super().__init__(parent)
        _keep_widget_alien(self)
        self._icon_name = icon
        self._icon = SvgIcon(icon)
        self._hover = 0.0
        self._scale = 1.0
        self._circular = circular
        self.setFixedSize(diameter, diameter)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self._hover_animation = QPropertyAnimation(self, b"hoverAmount", self)
        self._hover_animation.setDuration(ANIMATION_MS)
        self._hover_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._scale_animation = QPropertyAnimation(self, b"pressScale", self)
        self._scale_animation.setDuration(ANIMATION_MS)
        self._scale_animation.setEasingCurve(QEasingCurve.OutCubic)

    def set_icon(self, icon: str) -> None:
        """Change the SVG icon."""
        if icon != self._icon_name:
            self._icon_name = icon
            self._icon = SvgIcon(icon)
            self.update()

    def get_hover_amount(self) -> float:
        """Return hover animation amount."""
        return self._hover

    def set_hover_amount(self, value: float) -> None:
        """Set hover animation amount."""
        self._hover = max(0.0, min(1.0, float(value)))
        self.update()

    hoverAmount = Property(float, get_hover_amount, set_hover_amount)

    def get_press_scale(self) -> float:
        """Return current press scale."""
        return self._scale

    def set_press_scale(self, value: float) -> None:
        """Set current press scale."""
        self._scale = max(0.90, min(1.0, float(value)))
        self.update()

    pressScale = Property(float, get_press_scale, set_press_scale)

    def enterEvent(self, event) -> None:  # type: ignore[override]
        """Animate hover in."""
        self._animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        """Animate hover out."""
        self._animate_hover(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        """Animate pressed state."""
        if event.button() == Qt.LeftButton:
            self._animate_scale(0.95)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        """Emit clicked if released inside."""
        self._animate_scale(1.0)
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def _animate_hover(self, end_value: float) -> None:
        """Run hover animation."""
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self._hover)
        self._hover_animation.setEndValue(end_value)
        self._hover_animation.start()

    def _animate_scale(self, end_value: float) -> None:
        """Run press scale animation."""
        self._scale_animation.stop()
        self._scale_animation.setStartValue(self._scale)
        self._scale_animation.setEndValue(end_value)
        self._scale_animation.start()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        """Paint the icon button."""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        center = rect.center()
        scaled = QRectF(0, 0, rect.width() * self._scale, rect.height() * self._scale)
        scaled.moveCenter(center)

        painter.setPen(Qt.NoPen)
        if self._circular:
            glow = QRadialGradient(center, scaled.width() * 0.58)
            glow.setColorAt(0.0, QColor(150, 212, 255, 188 + int(42 * self._hover)))
            glow.setColorAt(0.38, QColor(124, 192, 255, 105 + int(42 * self._hover)))
            glow.setColorAt(0.72, QColor(90, 160, 235, 34 + int(24 * self._hover)))
            glow.setColorAt(1.0, QColor(120, 184, 255, 0))
            painter.setBrush(glow)
            painter.drawEllipse(scaled.adjusted(0, 0, 0, 0))

            ring_rect = scaled.adjusted(3, 3, -3, -3)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(124, 192, 255, 78 + int(38 * self._hover)), 4.2))
            painter.drawEllipse(ring_rect)

            button_rect = scaled.adjusted(6, 6, -6, -6)
            fill = QRadialGradient(button_rect.center(), button_rect.width() * 0.55)
            fill.setColorAt(0.0, QColor(255, 255, 255, 60 + int(18 * self._hover)))
            fill.setColorAt(0.36, QColor(128, 196, 255, 46 + int(24 * self._hover)))
            fill.setColorAt(0.72, QColor(34, 47, 63, 128))
            fill.setColorAt(1.0, QColor(8, 12, 18, 168))
            painter.setBrush(fill)
            painter.setPen(QPen(QColor(136, 202, 255, 250), 2.5))
            painter.drawEllipse(button_rect)

            inner = QRadialGradient(button_rect.center(), button_rect.width() * 0.42)
            inner.setColorAt(0.0, QColor(200, 235, 255, 98 + int(34 * self._hover)))
            inner.setColorAt(0.58, QColor(124, 192, 255, 34 + int(22 * self._hover)))
            inner.setColorAt(1.0, QColor(124, 192, 255, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(inner)
            painter.drawEllipse(button_rect.adjusted(4, 4, -4, -4))
        elif self._hover > 0:
            path = QPainterPath()
            path.addRoundedRect(scaled.adjusted(2, 2, -2, -2), 12, 12)
            painter.fillPath(path, QColor(117, 183, 255, int(30 * self._hover)))
            painter.setPen(QPen(QColor(120, 180, 255, int(120 * self._hover)), 1))
            painter.drawPath(path)
        else:
            glow_rect = scaled.adjusted(2, 2, -2, -2)
            glow = QRadialGradient(glow_rect.center(), glow_rect.width() * 0.68)
            glow.setColorAt(0.0, QColor(120, 180, 255, 18))
            glow.setColorAt(1.0, QColor(120, 180, 255, 0))
            painter.setBrush(glow)
            painter.drawEllipse(glow_rect)

        if self._circular:
            icon_margin = scaled.width() * 0.28
        elif self._icon_name in {"playlist", "fullscreen", "volume", "mute"}:
            icon_margin = scaled.width() * 0.06
        elif self._icon_name in {"rewind10", "forward10"}:
            icon_margin = scaled.width() * 0.02
        elif self._icon_name in {"volume", "mute"}:
            icon_margin = scaled.width() * 0.22
        else:
            icon_margin = scaled.width() * 0.19
        icon_rect = scaled.adjusted(icon_margin, icon_margin, -icon_margin, -icon_margin)
        self._icon.paint(painter, icon_rect)


class GlowSlider(QWidget):
    """Custom animated slider painted with QPainter."""

    valueChanged = Signal(float)
    sliderPressed = Signal()
    sliderReleased = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        track_height: int = METRICS.progress_track_height,
        handle_size: int = METRICS.progress_handle_size,
        fill_color: str = COLORS.progress_fill,
        min_width: int = 120,
    ) -> None:
        """Create a horizontal custom slider."""
        super().__init__(parent)
        _keep_widget_alien(self)
        self._value = 0.0
        self._hover = 0.0
        self._dragging = False
        self.track_height = track_height
        self.handle_size = handle_size
        self.fill_color = fill_color
        self.setMinimumWidth(min_width)
        self.setFixedHeight(max(handle_size + 10, 28))
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self._hover_animation = QPropertyAnimation(self, b"hoverAmount", self)
        self._hover_animation.setDuration(ANIMATION_MS)
        self._hover_animation.setEasingCurve(QEasingCurve.OutCubic)

    def value(self) -> float:
        """Return slider value in 0..1."""
        return self._value

    def setValue(self, value: float) -> None:
        """Set slider value in 0..1."""
        value = max(0.0, min(1.0, float(value)))
        if abs(value - self._value) > 0.0001:
            self._value = value
            self.valueChanged.emit(value)
            self.update()

    def get_hover_amount(self) -> float:
        """Return hover animation amount."""
        return self._hover

    def set_hover_amount(self, value: float) -> None:
        """Set hover animation amount."""
        self._hover = max(0.0, min(1.0, float(value)))
        self.update()

    hoverAmount = Property(float, get_hover_amount, set_hover_amount)

    def enterEvent(self, event) -> None:  # type: ignore[override]
        """Animate hover in."""
        self._animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        """Animate hover out."""
        if not self._dragging:
            self._animate_hover(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        """Start dragging."""
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self.sliderPressed.emit()
            self._set_from_x(event.position().x())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        """Update value while dragging."""
        if self._dragging:
            self._set_from_x(event.position().x())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        """End dragging."""
        if event.button() == Qt.LeftButton and self._dragging:
            self._set_from_x(event.position().x())
            self._dragging = False
            self.sliderReleased.emit()
            if not self.underMouse():
                self._animate_hover(0.0)
        super().mouseReleaseEvent(event)

    def _animate_hover(self, end_value: float) -> None:
        """Run hover animation."""
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self._hover)
        self._hover_animation.setEndValue(end_value)
        self._hover_animation.start()

    def _track_rect(self) -> QRectF:
        """Return the slider track rectangle."""
        margin = self.handle_size / 2 + 2
        return QRectF(
            margin,
            (self.height() - self.track_height) / 2,
            max(1.0, self.width() - margin * 2),
            self.track_height,
        )

    def _set_from_x(self, x_pos: float) -> None:
        """Set value based on x coordinate."""
        track = self._track_rect()
        self.setValue((float(x_pos) - track.left()) / track.width())

    def paintEvent(self, event) -> None:  # type: ignore[override]
        """Paint the custom slider."""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track = self._track_rect()
        radius = self.track_height / 2
        painter.setPen(Qt.NoPen)
        empty = QColor(COLORS.track_empty)
        empty.setAlpha(120)
        painter.setBrush(empty)
        painter.drawRoundedRect(track, radius, radius)

        filled = QRectF(track)
        filled.setWidth(track.width() * self._value)
        gradient = QLinearGradient(filled.left(), 0, filled.right(), 0)
        gradient.setColorAt(0, QColor(self.fill_color))
        gradient.setColorAt(1, QColor("#98D2FF"))
        painter.setBrush(gradient)
        painter.drawRoundedRect(filled, radius, radius)

        if filled.width() > 1:
            glow_rect = filled.adjusted(0, -5, 0, 5)
            glow = QLinearGradient(glow_rect.left(), 0, glow_rect.right(), 0)
            glow.setColorAt(0, QColor(105, 178, 255, 0))
            glow.setColorAt(0.55, QColor(105, 178, 255, 92))
            glow.setColorAt(1, QColor(105, 178, 255, 38))
            painter.setBrush(glow)
            painter.drawRoundedRect(glow_rect, glow_rect.height() / 2, glow_rect.height() / 2)

        handle_radius = self.handle_size / 2 + 1.5 * self._hover
        handle_x = track.left() + track.width() * self._value
        handle_center_y = track.center().y()
        handle_glow = QRadialGradient(handle_x, handle_center_y, handle_radius + 10)
        handle_glow.setColorAt(0.0, QColor(124, 192, 255, 180))
        handle_glow.setColorAt(0.46, QColor(124, 192, 255, 82))
        handle_glow.setColorAt(1.0, QColor(124, 192, 255, 0))
        painter.setBrush(handle_glow)
        painter.drawEllipse(
            QRectF(
                handle_x - handle_radius - 10,
                handle_center_y - handle_radius - 10,
                (handle_radius + 10) * 2,
                (handle_radius + 10) * 2,
            )
        )
        painter.setBrush(QColor(COLORS.handle))
        painter.drawEllipse(
            QRectF(handle_x - handle_radius, handle_center_y - handle_radius, handle_radius * 2, handle_radius * 2)
        )


class SpeedButton(QWidget):
    """Speed selector button with a QMenu."""

    speedChanged = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create speed selector."""
        super().__init__(parent)
        _keep_widget_alien(self)
        self._speed = 1.0
        self._hover = 0.0
        self.setFixedSize(METRICS.speed_width, METRICS.speed_height)
        self.setCursor(Qt.PointingHandCursor)
        self._arrow = SvgIcon("arrow_down")
        self._hover_animation = QPropertyAnimation(self, b"hoverAmount", self)
        self._hover_animation.setDuration(ANIMATION_MS)
        self._hover_animation.setEasingCurve(QEasingCurve.OutCubic)

    def get_hover_amount(self) -> float:
        """Return hover amount."""
        return self._hover

    def set_hover_amount(self, value: float) -> None:
        """Set hover amount."""
        self._hover = max(0.0, min(1.0, float(value)))
        self.update()

    hoverAmount = Property(float, get_hover_amount, set_hover_amount)

    def setSpeed(self, speed: float) -> None:
        """Set selected speed."""
        self._speed = float(speed)
        self.update()

    def speed(self) -> float:
        """Return selected speed."""
        return self._speed

    def enterEvent(self, event) -> None:  # type: ignore[override]
        """Animate hover in."""
        self._animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        """Animate hover out."""
        self._animate_hover(0.0)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        """Open speed menu."""
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self._show_menu()
        super().mouseReleaseEvent(event)

    def _animate_hover(self, end_value: float) -> None:
        """Run hover animation."""
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self._hover)
        self._hover_animation.setEndValue(end_value)
        self._hover_animation.start()

    def _show_menu(self) -> None:
        """Show the speed menu."""
        menu = QMenu(self)
        menu.setStyleSheet(
            f"""
            QMenu {{
                background: rgba(32, 42, 57, 235);
                color: {COLORS.text};
                border: 1px solid rgba(120, 180, 255, 120);
                border-radius: 10px;
                padding: 6px;
            }}
            QMenu::item {{
                padding: 7px 28px 7px 16px;
                border-radius: 6px;
            }}
            QMenu::item:selected, QMenu::item:checked {{
                background: rgba(111, 183, 255, 90);
            }}
            """
        )
        for speed in SPEED_OPTIONS:
            action = menu.addAction(self._format_speed(speed))
            action.setCheckable(True)
            action.setChecked(abs(speed - self._speed) < 0.001)
            action.triggered.connect(lambda _checked=False, value=speed: self._choose_speed(value))
        menu.popup(self.mapToGlobal(self.rect().bottomLeft()))

    def _choose_speed(self, speed: float) -> None:
        """Choose speed and emit signal."""
        self.setSpeed(speed)
        self.speedChanged.emit(speed)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        """Paint speed button."""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        if self._hover > 0:
            glow = QRadialGradient(rect.center(), rect.width() * 0.62)
            glow.setColorAt(0.0, QColor(120, 180, 255, int(72 * self._hover)))
            glow.setColorAt(1.0, QColor(120, 180, 255, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(glow)
            painter.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), 14, 14)

        path = QPainterPath()
        path.addRoundedRect(rect, 11, 11)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0, QColor(255, 255, 255, 40 + int(12 * self._hover)))
        gradient.setColorAt(0.48, QColor(120, 160, 190, 18 + int(8 * self._hover)))
        gradient.setColorAt(1, QColor(0, 0, 0, 32))
        painter.fillPath(path, gradient)
        painter.setPen(QPen(QColor(120, 180, 255, 120 + int(60 * self._hover)), 1.2))
        painter.drawPath(path)
        painter.setPen(QColor(COLORS.text))
        font = painter.font()
        font.setPointSize(METRICS.font_speed)
        font.setWeight(QFont.Weight.Light)
        painter.setFont(font)
        painter.drawText(rect.adjusted(12, -1, -28, 1), Qt.AlignVCenter | Qt.AlignLeft, f"[{self._format_speed(self._speed)}]")
        self._arrow.paint(painter, QRectF(rect.right() - 25, rect.center().y() - 7, 15, 15))

    @staticmethod
    def _format_speed(speed: float) -> str:
        """Format speed text."""
        if abs(speed - round(speed)) < 0.001:
            return f"{speed:.1f}x"
        return f"{speed:g}x"


class AppleTVControlBar(QFrame):
    """Commercial style Apple TV inspired control bar."""

    play_pause_toggled = Signal()
    play_requested = Signal()
    pause_requested = Signal()
    menu_requested = Signal()
    stop_requested = Signal()
    prev_channel = Signal()
    next_channel = Signal()
    skip_requested = Signal(int)
    seek_requested = Signal(float)
    volume_changed = Signal(int)
    mute_toggled = Signal()
    speed_changed = Signal(float)
    fullscreen_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the control bar."""
        super().__init__(parent)
        _keep_widget_alien(self)
        self.setObjectName("appleTVControlBar")
        self.setFixedHeight(METRICS.height)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setAutoFillBackground(False)
        self.setStyleSheet(
            """
            QFrame#appleTVControlBar {
                border: 1px solid rgba(120, 180, 255, 150);
                background: rgba(18, 22, 29, 220);
            }
            """
        )
        self._has_duration = False
        self._duration = 0.0
        self._muted = False
        self._build_ui()
        self._keep_children_alien()
        self.set_playing(False)

    def _build_ui(self) -> None:
        """Create child widgets and layout."""
        root = QVBoxLayout(self)
        root.setContentsMargins(METRICS.margin_x, METRICS.margin_y, METRICS.margin_x, METRICS.margin_y)
        root.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(METRICS.top_spacing)
        self.menu_button = SvgIconButton("playlist", METRICS.menu_button, self)
        self.menu_button.clicked.connect(self.menu_requested.emit)
        self.current_time_label = QLabel("00:00", self)
        self.current_time_label.setMinimumWidth(54)
        self.current_time_label.setAlignment(Qt.AlignCenter)
        self.current_time_label.setStyleSheet(
            f"color: {COLORS.text}; font-size: {METRICS.font_time}px; font-weight: 400;"
        )
        self.progress_slider = GlowSlider(
            self,
            track_height=METRICS.progress_track_height,
            handle_size=METRICS.progress_handle_size,
            fill_color=COLORS.progress_fill,
            min_width=METRICS.top_progress_min_width,
        )
        self.progress_slider.sliderReleased.connect(self._emit_seek)
        self.total_time_label = QLabel("00:00", self)
        self.total_time_label.setMinimumWidth(54)
        self.total_time_label.setAlignment(Qt.AlignCenter)
        self.total_time_label.setStyleSheet(
            f"color: {COLORS.text}; font-size: {METRICS.font_time}px; font-weight: 400;"
        )
        self.fullscreen_button = SvgIconButton("fullscreen", METRICS.full_button, self)
        self.fullscreen_button.clicked.connect(self.fullscreen_requested.emit)

        right_top_group = QWidget(self)
        right_top_layout = QHBoxLayout(right_top_group)
        right_top_layout.setContentsMargins(0, 0, 0, 0)
        right_top_layout.setSpacing(10)
        right_top_layout.addWidget(self.total_time_label, 0, Qt.AlignVCenter)
        right_top_layout.addWidget(self.fullscreen_button, 0, Qt.AlignVCenter)

        top.addWidget(self.menu_button, 0, Qt.AlignVCenter)
        top.addWidget(self.current_time_label, 0, Qt.AlignVCenter)
        top.addWidget(self.progress_slider, 1, Qt.AlignVCenter)
        top.addWidget(right_top_group, 0, Qt.AlignVCenter)
        root.addLayout(top)

        bottom = QHBoxLayout()
        bottom.setSpacing(0)
        left_zone = QWidget(self)
        center_zone = QWidget(self)
        right_zone = QWidget(self)
        left_zone.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        center_zone.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        right_zone.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        left_layout = QHBoxLayout(left_zone)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        center_layout = QHBoxLayout(center_zone)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        right_layout = QHBoxLayout(right_zone)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        volume_group = QWidget(left_zone)
        volume_layout = QHBoxLayout(volume_group)
        volume_layout.setContentsMargins(0, 0, 0, 0)
        volume_layout.setSpacing(10)
        self.volume_button = SvgIconButton("volume", METRICS.volume_button, self)
        self.volume_button.clicked.connect(self._toggle_mute)
        self.volume_slider = GlowSlider(
            self,
            track_height=METRICS.volume_track_height,
            handle_size=METRICS.volume_handle_size,
            fill_color=COLORS.volume_fill,
            min_width=METRICS.volume_width,
        )
        self.volume_slider.setFixedWidth(METRICS.volume_width)
        self.volume_slider.setValue(1.0)
        self.volume_slider.valueChanged.connect(lambda value: self.volume_changed.emit(int(round(value * 100))))
        volume_layout.addWidget(self.volume_button, 0, Qt.AlignVCenter)
        volume_layout.addWidget(self.volume_slider, 0, Qt.AlignVCenter)
        left_layout.addWidget(volume_group, 0, Qt.AlignLeft | Qt.AlignVCenter)
        left_layout.addStretch(1)

        transport_group = QWidget(center_zone)
        transport_group.setFixedWidth(METRICS.transport_group_width)
        center = QHBoxLayout(transport_group)
        center.setContentsMargins(METRICS.transport_left_inset, 0, 0, 0)
        center.setSpacing(METRICS.row_spacing)
        self.prev_button = SvgIconButton("previous", METRICS.transport_button, self)
        self.rewind_button = SvgIconButton("rewind10", METRICS.transport_button, self)
        self.play_button = SvgIconButton("play", METRICS.play_button, self, circular=True)
        self.stop_button = SvgIconButton("stop", METRICS.transport_button, self)
        self.forward_button = SvgIconButton("forward10", METRICS.transport_button, self)
        self.next_button = SvgIconButton("next", METRICS.transport_button, self)
        self.prev_button.clicked.connect(self.prev_channel.emit)
        self.rewind_button.clicked.connect(lambda: self.skip_requested.emit(-10))
        self.play_button.clicked.connect(self.play_pause_toggled.emit)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.forward_button.clicked.connect(lambda: self.skip_requested.emit(10))
        self.next_button.clicked.connect(self.next_channel.emit)
        for button in (
            self.prev_button,
            self.rewind_button,
            self.play_button,
            self.stop_button,
            self.forward_button,
            self.next_button,
        ):
            center.addWidget(button)
        center_layout.addStretch(1)
        center_layout.addWidget(transport_group, 0, Qt.AlignCenter)
        center_layout.addStretch(1)

        self.speed_button = SpeedButton(self)
        self.speed_button.speedChanged.connect(self.speed_changed.emit)
        right_layout.addStretch(1)
        right_layout.addWidget(self.speed_button, 0, Qt.AlignRight | Qt.AlignVCenter)

        bottom.addWidget(left_zone, 20)
        bottom.addWidget(center_zone, 60)
        bottom.addWidget(right_zone, 20)
        root.addLayout(bottom)

    def _keep_children_alien(self) -> None:
        """Avoid creating QWidgetWindow handles for non-top-level overlay children."""
        for child in self.findChildren(QWidget):
            if not child.isWindow():
                _keep_widget_alien(child)

    def set_duration_mode(self, has_duration: bool) -> None:
        """Set whether the current media has a duration."""
        self._has_duration = bool(has_duration)
        if not self._has_duration:
            self.progress_slider.setValue(0.0)

    def update_progress(self, position: float, duration: float | None) -> None:
        """Update progress labels and slider."""
        self._duration = float(duration or 0.0)
        position_value = float(position or 0.0)
        self.current_time_label.setText(self._format_time(position_value))
        self.total_time_label.setText(self._format_time(self._duration))
        if self._duration > 0 and not self.progress_slider._dragging:
            self.progress_slider.setValue(position_value / self._duration)

    def set_playing(self, playing: bool) -> None:
        """Update play button icon according to playing state."""
        self.play_button.set_icon("pause" if playing else "play")

    def set_volume(self, value: float) -> None:
        """Update volume slider value."""
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(max(0.0, min(1.0, float(value or 0.0) / 100.0)))
        self.volume_slider.blockSignals(False)

    def set_muted(self, muted: bool) -> None:
        """Update volume icon according to muted state."""
        self._muted = bool(muted)
        self.volume_button.set_icon("mute" if self._muted else "volume")

    def reset_speed(self) -> None:
        """Reset playback speed UI to 1.0x."""
        self.set_speed(1.0)

    def set_speed(self, speed: float) -> None:
        """Set playback speed UI."""
        self.speed_button.setSpeed(float(speed or 1.0))

    def _toggle_mute(self) -> None:
        """Emit mute toggle request."""
        self.mute_toggled.emit()

    def _emit_seek(self) -> None:
        """Emit seek fraction when progress drag ends."""
        self.seek_requested.emit(self.progress_slider.value())

    def paintEvent(self, event) -> None:  # type: ignore[override]
        """Paint rounded translucent gradient background."""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        for inset, width, alpha in ((1.5, 7, 26), (3.5, 4, 38), (5.5, 2, 54)):
            glow_rect = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
            glow_path = QPainterPath()
            glow_path.addRoundedRect(glow_rect, METRICS.radius, METRICS.radius)
            painter.setPen(QPen(QColor(80, 150, 255, alpha), width))
            painter.drawPath(glow_path)

        path = QPainterPath()
        path.addRoundedRect(rect, METRICS.radius, METRICS.radius)

        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        top = QColor(COLORS.background_top)
        bottom = QColor(COLORS.background_bottom)
        top.setAlphaF(0.90)
        bottom.setAlphaF(0.90)
        mid = QColor("#242A33")
        mid.setAlphaF(0.91)
        gradient.setColorAt(0, top)
        gradient.setColorAt(0.52, mid)
        gradient.setColorAt(1, bottom)
        painter.fillPath(path, gradient)

        painter.save()
        painter.setClipPath(path)
        center_glow = QRadialGradient(rect.center().x(), rect.bottom() - 22, rect.width() * 0.28)
        center_glow.setColorAt(0.0, QColor(90, 150, 210, 22))
        center_glow.setColorAt(0.52, QColor(90, 150, 210, 8))
        center_glow.setColorAt(1.0, QColor(90, 150, 210, 0))
        painter.fillPath(path, center_glow)

        haze = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        haze.setColorAt(0.0, QColor(255, 255, 255, 18))
        haze.setColorAt(0.24, QColor(255, 255, 255, 6))
        haze.setColorAt(0.62, QColor(0, 0, 0, 8))
        haze.setColorAt(1.0, QColor(0, 0, 0, 24))
        painter.fillPath(path, haze)

        for y in range(int(rect.top()) + 3, int(rect.bottom()), 4):
            alpha = 5 if y % 12 else 3
            painter.setPen(QPen(QColor(255, 255, 255, alpha), 1))
            painter.drawLine(int(rect.left()) + 2, y, int(rect.right()) - 2, y)
        for y in range(int(rect.top()) + 1, int(rect.bottom()), 11):
            painter.setPen(QPen(QColor(0, 0, 0, 14), 1))
            painter.drawLine(int(rect.left()) + 2, y, int(rect.right()) - 2, y)
        highlight = QLinearGradient(rect.topLeft(), rect.topRight())
        highlight.setColorAt(0.0, QColor(255, 255, 255, 20))
        highlight.setColorAt(0.5, QColor(255, 255, 255, 5))
        highlight.setColorAt(1.0, QColor(255, 255, 255, 18))
        painter.fillPath(path, highlight)
        painter.restore()

        painter.setPen(QPen(QColor(120, 180, 255, 145), 1))
        painter.drawPath(path)

    @staticmethod
    def _format_time(seconds: float | None) -> str:
        """Format seconds to mm:ss or hh:mm:ss."""
        if seconds is None or seconds < 0:
            return "00:00"
        total = int(seconds)
        hours = total // 3600
        minutes = (total % 3600) // 60
        secs = total % 60
        if hours:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"


class DemoWindow(QWidget):
    """Standalone demo window for this control bar."""

    def __init__(self) -> None:
        """Create demo window."""
        super().__init__()
        self.setWindowTitle("Apple TV Control Bar Demo")
        self.resize(1280, 240)
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        self.control = AppleTVControlBar(self)
        layout.addWidget(self.control)
        self.control.update_progress(37, 64)


def run_demo() -> None:
    """Run a standalone demo for manual visual inspection."""
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = DemoWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_demo()
