from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QPen


class TriggerArea(QWidget):
    """点击触发区域（完全透明，无视觉元素）"""
    clicked = Signal()

    def __init__(self, parent=None, side='left'):
        super().__init__(parent)
        self.side = side
        # 完全透明，无背景
        self.setStyleSheet("background: transparent;")
        self.setMouseTracking(False)
        # 确保接收鼠标事件
        self.setAttribute(Qt.WA_Hover, True)

    def paintEvent(self, event):
        """不绘制任何内容，保持完全透明"""
        pass

    def mousePressEvent(self, event):
        """点击触发"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def update_geometry(self, parent_width, parent_height):
        """更新几何位置"""
        trigger_width = parent_width // 8

        if self.side == 'left':
            self.setGeometry(0, 0, trigger_width, parent_height)
        else:  # right
            self.setGeometry(parent_width - trigger_width, 0,
                           trigger_width, parent_height)
