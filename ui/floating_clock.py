from datetime import datetime
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QLabel, QGraphicsDropShadowEffect
from PySide6.QtGui import QColor


class FloatingClock(QLabel):
    """右上角悬浮时钟"""

    WEEKDAYS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")

    def __init__(self, parent=None, show_weekday=True):
        super().__init__(parent)
        self.setWindowFlags(Qt.Widget)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._show_weekday = bool(show_weekday)

        # 深色玻璃底 + 高亮边框，保证在明暗画面上都清晰。
        self.setStyleSheet("""
            QLabel {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 rgba(58, 68, 86, 222),
                    stop: 1 rgba(20, 27, 38, 226)
                );
                color: #f5f9ff;
                font-size: 16px;
                font-weight: 700;
                padding: 8px 14px;
                border: 1px solid rgba(120, 180, 255, 130);
                border-radius: 14px;
            }
        """)

        # 阴影效果：让时钟像浮在视频上方，兼顾立体感和可读性。
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22)
        shadow.setColor(QColor(0, 0, 0, 185))
        shadow.setOffset(0, 5)
        self.setGraphicsEffect(shadow)

        # 更新定时器（每秒，精确到秒）
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)

        # 立即更新一次
        self.update_time()

    def update_time(self):
        """更新时间显示（精确到秒）"""
        now = datetime.now()
        weekday = f" {self.WEEKDAYS[now.weekday()]}" if self._show_weekday else ""
        text = now.strftime(f"%Y年%m月%d日{weekday} %H:%M:%S")
        self.setText(text)
        self.adjustSize()

    def set_show_weekday(self, enabled):
        """设置是否显示星期。"""
        self._show_weekday = bool(enabled)
        self.update_time()

    def position_at_top_right(self, parent_width):
        """定位到父窗口右上角（与最右、最上对齐）"""
        self.move(max(0, parent_width - self.width() - 10), 10)
