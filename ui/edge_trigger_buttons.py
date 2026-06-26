from PySide6.QtCore import QEasingCurve, Property, QRectF, Qt, QPropertyAnimation, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget


class EdgeTriggerButton(QWidget):
    """Pure-arrow edge trigger used by click panel interaction mode."""

    triggered = Signal(str)

    def __init__(self, edge: str, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.edge = str(edge or "")
        self._expanded = False
        self._hover = 0.0
        self.setObjectName(f"edgeTrigger_{self.edge}")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_StyledBackground, False)
        if self.edge in {"left", "right"}:
            self.setFixedSize(34, 58)
        else:
            self.setFixedSize(58, 34)

        self._hover_animation = QPropertyAnimation(self, b"hoverAmount", self)
        self._hover_animation.setDuration(140)
        self._hover_animation.setEasingCurve(QEasingCurve.OutCubic)

    def isExpanded(self) -> bool:
        return self._expanded

    def setExpanded(self, expanded: bool) -> None:
        expanded = bool(expanded)
        if self._expanded != expanded:
            self._expanded = expanded
            self.update()

    def get_hover_amount(self) -> float:
        return self._hover

    def set_hover_amount(self, value: float) -> None:
        self._hover = max(0.0, min(1.0, float(value)))
        self.update()

    hoverAmount = Property(float, get_hover_amount, set_hover_amount)

    def enterEvent(self, event):  # type: ignore[override]
        self._animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):  # type: ignore[override]
        self._animate_hover(0.0)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):  # type: ignore[override]
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.triggered.emit(self.edge)
        super().mouseReleaseEvent(event)

    def _animate_hover(self, end_value: float) -> None:
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self._hover)
        self._hover_animation.setEndValue(end_value)
        self._hover_animation.start()

    def _glyph(self) -> str:
        if self.edge == "left":
            return "<" if self._expanded else ">"
        if self.edge == "right":
            return ">" if self._expanded else "<"
        if self.edge == "top":
            return "^" if self._expanded else "v"
        if self.edge == "bottom":
            return "v" if self._expanded else "^"
        return ">"

    def paintEvent(self, event):  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(self.rect())
        font = QFont("Segoe UI", 26)
        font.setWeight(QFont.Weight.Light)
        painter.setFont(font)

        glyph = self._glyph()
        shadow_offset = 1 + int(self._hover)
        painter.setPen(QColor(0, 0, 0, 160))
        painter.drawText(rect.translated(shadow_offset, shadow_offset), Qt.AlignCenter, glyph)
        painter.setPen(QColor(120, 190, 255, 65 + int(65 * self._hover)))
        painter.drawText(rect.adjusted(-1, -1, 1, 1), Qt.AlignCenter, glyph)
        painter.setPen(QColor(255, 255, 255, 238))
        painter.drawText(rect, Qt.AlignCenter, glyph)
