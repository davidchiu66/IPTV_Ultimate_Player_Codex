from PySide6.QtCore import QEvent, QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QWidget

from ui.apple_tv_control_bar import SvgIconButton


class ToolbarOverlay(QFrame):
    """Top hover toolbar."""

    open_url_requested = Signal()
    open_resource_requested = Signal()
    settings_requested = Signal()
    open_browser_requested = Signal()
    choose_browser_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Widget)
        self.setAttribute(Qt.WA_StyledBackground)

        self.setStyleSheet("""
            QFrame {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 rgba(58, 68, 86, 226),
                    stop: 1 rgba(22, 28, 37, 230)
                );
                border-bottom: 1px solid rgba(120, 180, 255, 120);
            }
            QPushButton {
                background: rgba(255, 255, 255, 22);
                color: #e7eef7;
                border: 1px solid rgba(120, 180, 255, 110);
                border-radius: 10px;
                padding: 7px 16px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: rgba(120, 180, 255, 42);
                border: 1px solid rgba(120, 180, 255, 170);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        side_width = 60

        self.left_group = QWidget(self)
        self.left_group.setFixedWidth(side_width)
        self.left_layout = QHBoxLayout(self.left_group)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(10)

        self.resource_button = self._make_icon_button("menu", "打开频道资源")
        self.resource_button.clicked.connect(self.open_resource_requested.emit)
        self.left_layout.addWidget(self.resource_button)
        self.left_layout.addStretch(1)
        layout.addWidget(self.left_group)

        layout.addStretch(1)

        self.center_group = QWidget(self)
        self.center_layout = QHBoxLayout(self.center_group)
        self.center_layout.setContentsMargins(0, 0, 0, 0)
        self.center_layout.setSpacing(10)

        self.browser_button = QPushButton("默认浏览器观看", self.center_group)
        self.browser_button.clicked.connect(self.open_browser_requested.emit)
        self.center_layout.addWidget(self.browser_button)

        self.choose_browser_button = QPushButton("选择浏览器观看", self.center_group)
        self.choose_browser_button.clicked.connect(self.choose_browser_requested.emit)
        self.center_layout.addWidget(self.choose_browser_button)

        layout.addWidget(self.center_group, 0, Qt.AlignCenter)

        layout.addStretch(1)

        self.right_group = QWidget(self)
        self.right_group.setFixedWidth(side_width)
        self.right_layout = QHBoxLayout(self.right_group)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(10)
        self.right_layout.addStretch(1)
        layout.addWidget(self.right_group)

        self.buttons_placeholder = self.left_layout

        self.hide()

        self.leave_timer = QTimer(self)
        self.leave_timer.setSingleShot(True)
        self.leave_timer.timeout.connect(self._on_leave_timeout)
        self.leave_delay = 300

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_with_animation)

        self.installEventFilter(self)
        self.animation = None
        self.settings_button = None

    def _make_icon_button(self, icon_name, tooltip):
        icon = "playlist" if icon_name == "menu" else icon_name
        button = SvgIconButton(icon, 44, self)
        button.setToolTip(tooltip)
        return button

    def eventFilter(self, obj, event):
        if event.type() in [QEvent.MouseMove, QEvent.MouseButtonPress, QEvent.KeyPress]:
            self.reset_hide_timer()
        return super().eventFilter(obj, event)

    def reset_hide_timer(self):
        self.hide_timer.stop()
        self.hide_timer.start(10000)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self.isVisible():
            self.leave_timer.start(self.leave_delay)

    def enterEvent(self, event):
        super().enterEvent(event)
        self.leave_timer.stop()

    def _on_leave_timeout(self):
        if self.isVisible():
            self.hide_with_animation()

    def show_with_animation(self):
        if not self.parent():
            return

        parent_width = self.parent().width()
        height = 60

        self.setGeometry(0, -height, parent_width, height)
        self.show()
        self.raise_()

        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.setStartValue(QRect(0, -height, parent_width, height))
        self.animation.setEndValue(QRect(0, 0, parent_width, height))
        self.animation.start()

        self.reset_hide_timer()

    def hide_with_animation(self):
        if not self.isVisible() or not self.parent():
            return

        parent_width = self.parent().width()
        height = self.height()

        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.InCubic)
        self.animation.setStartValue(QRect(0, 0, parent_width, height))
        self.animation.setEndValue(QRect(0, -height, parent_width, height))
        self.animation.finished.connect(self.hide)
        self.animation.finished.connect(self._on_hide_finished)
        self.animation.start()

    def _on_hide_finished(self):
        if self.parent() and self.parent().parent():
            main_window = self._find_main_window()
            if main_window:
                self._check_and_enable_triggers(main_window)

    def _find_main_window(self):
        parent = self.parent()
        while parent:
            if hasattr(parent, "parent") and callable(parent.parent):
                parent = parent.parent()
                if hasattr(parent, "player_panel"):
                    return parent
            else:
                break
        return None

    def _check_and_enable_triggers(self, main_window):
        overlays = [
            main_window.toolbar_overlay,
            main_window.nav_overlay,
            main_window.channel_list_overlay,
            main_window.detail_overlay,
        ]
        settings_overlay = getattr(main_window, "settings_overlay", None)
        if settings_overlay is not None:
            overlays.append(settings_overlay)
        if all(not overlay.isVisible() for overlay in overlays):
            main_window.player_panel._enable_triggers_interaction()

    def add_button(self, text, callback):
        btn = QPushButton(text)
        btn.clicked.connect(callback)
        self.buttons_placeholder.addWidget(btn)
        return btn

    def add_settings_button(self, callback):
        self.settings_button = self._make_icon_button("settings", "设置")
        self.settings_button.clicked.connect(callback)
        self.right_layout.addWidget(self.settings_button)
        return self.settings_button
