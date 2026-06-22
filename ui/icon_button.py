import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QPushButton


class IconButton(QPushButton):
    """Unified self-painted icon button for toolbar and player controls."""

    def __init__(
        self,
        icon_name,
        tooltip="",
        parent=None,
        size=(40, 38),
        variant="plain",
        icon_scale=1.0,
    ):
        super().__init__(parent)
        self.icon_name = icon_name
        self.variant = variant
        self.icon_scale = float(icon_scale or 1.0)
        self._active = False
        self._muted = False
        self.setText("")
        self.setToolTip(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(*size)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet("background: transparent; border: none; padding: 0;")

    def set_icon(self, icon_name):
        if icon_name != self.icon_name:
            self.icon_name = icon_name
            self.update()

    def set_active(self, active):
        active = bool(active)
        if active != self._active:
            self._active = active
            self.update()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        if self.variant in {"glass", "primary"}:
            path = QPainterPath()
            path.addRoundedRect(rect, 7, 7)
            base = QColor(255, 255, 255, 28 if self.variant == "primary" else 18)
            if self.underMouse():
                base = QColor(255, 255, 255, 42)
            if self.isDown() or self._active:
                base = QColor(24, 136, 255, 58)
            painter.fillPath(path, base)
            painter.setPen(QPen(QColor(210, 245, 250, 42), 1.0))
            painter.drawPath(path)
        elif self.underMouse() or self.isDown() or self._active:
            path = QPainterPath()
            path.addRoundedRect(rect, 6, 6)
            painter.fillPath(path, QColor(255, 255, 255, 28 if not self.isDown() else 42))

        self._draw_icon(painter, rect)

    def _pen(self, width=3.2):
        pen = QPen(QColor(255, 255, 255), width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        return pen

    def _fill(self):
        return QColor(255, 255, 255)

    def _icon_rect(self, rect):
        side = min(rect.width(), rect.height()) * 0.56 * self.icon_scale
        return QRectF(
            rect.center().x() - side / 2,
            rect.center().y() - side / 2,
            side,
            side,
        )

    def _draw_icon(self, painter, rect):
        name = self.icon_name
        r = self._icon_rect(rect)
        if name == "menu":
            self._draw_menu(painter, r)
        elif name == "settings":
            self._draw_settings(painter, r)
        elif name == "play":
            self._draw_play(painter, r)
        elif name == "pause":
            self._draw_pause(painter, r)
        elif name == "stop":
            self._draw_stop(painter, r)
        elif name == "previous":
            self._draw_previous(painter, r)
        elif name == "next":
            self._draw_next(painter, r)
        elif name == "rewind10":
            self._draw_seek10(painter, r, -1)
        elif name == "forward10":
            self._draw_seek10(painter, r, 1)
        elif name == "volume":
            self._draw_volume(painter, r, muted=False)
        elif name == "mute":
            self._draw_volume(painter, r, muted=True)
        elif name == "fullscreen":
            self._draw_fullscreen(painter, r)

    def _draw_menu(self, painter, r):
        painter.setPen(self._pen(3.0))
        x1 = r.left()
        x2 = r.right()
        for y in (r.top() + r.height() * 0.22, r.center().y(), r.bottom() - r.height() * 0.22):
            painter.drawLine(QPointF(x1, y), QPointF(x2, y))

    def _draw_settings(self, painter, r):
        painter.setPen(self._pen(2.6))
        center = r.center()
        outer = min(r.width(), r.height()) * 0.38
        inner = outer * 0.42
        for index in range(8):
            angle = math.radians(index * 45)
            start = QPointF(center.x() + math.cos(angle) * outer * 0.78, center.y() + math.sin(angle) * outer * 0.78)
            end = QPointF(center.x() + math.cos(angle) * outer * 1.08, center.y() + math.sin(angle) * outer * 1.08)
            painter.drawLine(start, end)
        painter.drawEllipse(center, outer * 0.74, outer * 0.74)
        painter.setBrush(QColor(255, 255, 255))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, inner, inner)

    def _draw_play(self, painter, r):
        painter.setBrush(self._fill())
        painter.setPen(Qt.NoPen)
        poly = QPolygonF([
            QPointF(r.left() + r.width() * 0.28, r.top() + r.height() * 0.15),
            QPointF(r.left() + r.width() * 0.28, r.bottom() - r.height() * 0.15),
            QPointF(r.right() - r.width() * 0.14, r.center().y()),
        ])
        painter.drawPolygon(poly)

    def _draw_pause(self, painter, r):
        painter.setBrush(self._fill())
        painter.setPen(Qt.NoPen)
        w = r.width() * 0.22
        gap = r.width() * 0.15
        h = r.height() * 0.74
        y = r.center().y() - h / 2
        painter.drawRoundedRect(QRectF(r.center().x() - gap / 2 - w, y, w, h), 2, 2)
        painter.drawRoundedRect(QRectF(r.center().x() + gap / 2, y, w, h), 2, 2)

    def _draw_stop(self, painter, r):
        painter.setBrush(self._fill())
        painter.setPen(Qt.NoPen)
        side = min(r.width(), r.height()) * 0.58
        painter.drawRoundedRect(QRectF(r.center().x() - side / 2, r.center().y() - side / 2, side, side), 3, 3)

    def _draw_previous(self, painter, r):
        painter.setBrush(self._fill())
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(r.left(), r.top() + r.height() * 0.15, r.width() * 0.12, r.height() * 0.70), 1.5, 1.5)
        poly = QPolygonF([
            QPointF(r.right(), r.top() + r.height() * 0.12),
            QPointF(r.right(), r.bottom() - r.height() * 0.12),
            QPointF(r.left() + r.width() * 0.20, r.center().y()),
        ])
        painter.drawPolygon(poly)

    def _draw_next(self, painter, r):
        painter.setBrush(self._fill())
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(r.right() - r.width() * 0.12, r.top() + r.height() * 0.15, r.width() * 0.12, r.height() * 0.70), 1.5, 1.5)
        poly = QPolygonF([
            QPointF(r.left(), r.top() + r.height() * 0.12),
            QPointF(r.left(), r.bottom() - r.height() * 0.12),
            QPointF(r.right() - r.width() * 0.20, r.center().y()),
        ])
        painter.drawPolygon(poly)

    def _draw_seek10(self, painter, r, direction):
        painter.setBrush(self._fill())
        painter.setPen(Qt.NoPen)
        if direction < 0:
            tri1 = [
                QPointF(r.right() - r.width() * 0.08, r.top() + r.height() * 0.08),
                QPointF(r.right() - r.width() * 0.08, r.top() + r.height() * 0.58),
                QPointF(r.left() + r.width() * 0.44, r.top() + r.height() * 0.33),
            ]
            tri2 = [
                QPointF(r.left() + r.width() * 0.48, r.top() + r.height() * 0.08),
                QPointF(r.left() + r.width() * 0.48, r.top() + r.height() * 0.58),
                QPointF(r.left() + r.width() * 0.04, r.top() + r.height() * 0.33),
            ]
        else:
            tri1 = [
                QPointF(r.left() + r.width() * 0.08, r.top() + r.height() * 0.08),
                QPointF(r.left() + r.width() * 0.08, r.top() + r.height() * 0.58),
                QPointF(r.right() - r.width() * 0.44, r.top() + r.height() * 0.33),
            ]
            tri2 = [
                QPointF(r.right() - r.width() * 0.48, r.top() + r.height() * 0.08),
                QPointF(r.right() - r.width() * 0.48, r.top() + r.height() * 0.58),
                QPointF(r.right() - r.width() * 0.04, r.top() + r.height() * 0.33),
            ]
        painter.drawPolygon(QPolygonF(tri1))
        painter.drawPolygon(QPolygonF(tri2))
        painter.setPen(QPen(QColor(255, 255, 255), 1.8))
        font = painter.font()
        font.setPointSizeF(max(7.0, r.height() * 0.23))
        painter.setFont(font)
        painter.drawText(QRectF(r.left(), r.top() + r.height() * 0.56, r.width(), r.height() * 0.42), Qt.AlignCenter, "+10s" if direction > 0 else "-10s")

    def _draw_volume(self, painter, r, muted=False):
        painter.setBrush(self._fill())
        painter.setPen(Qt.NoPen)
        body = QPolygonF([
            QPointF(r.left(), r.top() + r.height() * 0.38),
            QPointF(r.left() + r.width() * 0.28, r.top() + r.height() * 0.38),
            QPointF(r.left() + r.width() * 0.58, r.top() + r.height() * 0.14),
            QPointF(r.left() + r.width() * 0.58, r.bottom() - r.height() * 0.14),
            QPointF(r.left() + r.width() * 0.28, r.bottom() - r.height() * 0.38),
            QPointF(r.left(), r.bottom() - r.height() * 0.38),
        ])
        painter.drawPolygon(body)
        painter.setPen(self._pen(2.4))
        if muted:
            painter.drawLine(QPointF(r.right() - r.width() * 0.25, r.top() + r.height() * 0.28), QPointF(r.right(), r.bottom() - r.height() * 0.28))
            painter.drawLine(QPointF(r.right(), r.top() + r.height() * 0.28), QPointF(r.right() - r.width() * 0.25, r.bottom() - r.height() * 0.28))
        else:
            painter.drawArc(QRectF(r.left() + r.width() * 0.45, r.top() + r.height() * 0.25, r.width() * 0.40, r.height() * 0.50), -45 * 16, 90 * 16)
            painter.drawArc(QRectF(r.left() + r.width() * 0.35, r.top() + r.height() * 0.10, r.width() * 0.62, r.height() * 0.80), -45 * 16, 90 * 16)

    def _draw_fullscreen(self, painter, r):
        painter.setPen(self._pen(2.9))
        l, t, w, h = r.left(), r.top(), r.width(), r.height()
        s = min(w, h) * 0.30
        painter.drawLine(QPointF(l, t + s), QPointF(l, t))
        painter.drawLine(QPointF(l, t), QPointF(l + s, t))
        painter.drawLine(QPointF(l + w - s, t), QPointF(l + w, t))
        painter.drawLine(QPointF(l + w, t), QPointF(l + w, t + s))
        painter.drawLine(QPointF(l, t + h - s), QPointF(l, t + h))
        painter.drawLine(QPointF(l, t + h), QPointF(l + s, t + h))
        painter.drawLine(QPointF(l + w - s, t + h), QPointF(l + w, t + h))
        painter.drawLine(QPointF(l + w, t + h), QPointF(l + w, t + h - s))
