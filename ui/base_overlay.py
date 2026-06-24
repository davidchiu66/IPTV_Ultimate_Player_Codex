from PySide6.QtCore import QTimer, QPropertyAnimation, QRect, QEasingCurve, Qt, QEvent
from PySide6.QtWidgets import QFrame
from PySide6.QtGui import QCursor


class BaseOverlay(QFrame):
    EDGE_MARGIN = 10
    COMPACT_EDGE_MARGIN = 6
    MIN_OVERLAY_WIDTH = 300
    MAX_WIDTH_RATIO = 0.58
    COMPACT_HEIGHT_THRESHOLD = 720
    """覆盖层基类"""

    def __init__(self, parent=None, side='left', width=350):
        super().__init__(parent)
        self.side = side
        self.base_overlay_width = width
        self.overlay_width = width
        self.setWindowFlags(Qt.Widget)
        self.setAttribute(Qt.WA_StyledBackground)

        # 半透明背景 + 圆角
        self.setStyleSheet("""
            QFrame {
                background: rgba(34, 37, 47, 0.95);
                border-radius: 12px;
            }
        """)

        # 自动滑出定时器：鼠标在覆盖层上则停止；离开后 3 秒滑出
        self.hide_delay = 3000  # 3 秒
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._maybe_hide)

        # 事件过滤器（用于在交互时暂停滑出）
        self.installEventFilter(self)

        # 动画对象
        self.animation = None

        self.hide()

    def _is_compact_viewport(self):
        """Return whether the parent viewport needs compact overlay spacing."""
        parent = self.parent()
        return bool(parent and parent.height() <= self.COMPACT_HEIGHT_THRESHOLD)

    def _edge_margin(self):
        """Return current slide-in edge margin."""
        return self.COMPACT_EDGE_MARGIN if self._is_compact_viewport() else self.EDGE_MARGIN

    def _adaptive_overlay_width(self):
        """Return an overlay width that fits the current logical viewport."""
        parent = self.parent()
        if not parent:
            return self.base_overlay_width
        margin = self._edge_margin()
        available_width = max(self.MIN_OVERLAY_WIDTH, parent.width() - margin * 2)
        ratio_width = max(self.MIN_OVERLAY_WIDTH, int(parent.width() * self.MAX_WIDTH_RATIO))
        return min(self.base_overlay_width, available_width, ratio_width)

    def _apply_adaptive_layout(self):
        """Allow subclasses to compact internal layout before showing."""
        return

    def eventFilter(self, obj, event):
        """覆盖层上有交互（移动/点击/按键/滚轮）时暂停滑出定时器。"""
        if event.type() in [QEvent.MouseMove, QEvent.MouseButtonPress,
                           QEvent.KeyPress, QEvent.Wheel]:
            self.hide_timer.stop()
        return super().eventFilter(obj, event)

    def reset_hide_timer(self):
        """（重新）启动滑出定时器：hide_delay 后滑出。"""
        self.hide_timer.stop()
        self.hide_timer.start(self.hide_delay)

    def leaveEvent(self, event):
        """鼠标离开覆盖层，启动滑出定时器（3 秒后滑出）。"""
        super().leaveEvent(event)
        if self.isVisible():
            self.reset_hide_timer()

    def enterEvent(self, event):
        """鼠标进入覆盖层，停止滑出定时器（保持显示）。"""
        super().enterEvent(event)
        self.hide_timer.stop()

    def _maybe_hide(self):
        """定时器到点：若鼠标仍在覆盖层范围内(含子控件)则续命，否则滑出。"""
        if not self.isVisible():
            return
        local = self.mapFromGlobal(QCursor.pos())
        if self.rect().contains(local):
            self.reset_hide_timer()
        else:
            self.hide_with_animation()

    def show_with_animation(self):
        """滑入动画显示"""
        if not self.parent():
            return

        parent_height = self.parent().height()
        parent_width = self.parent().width()
        self.overlay_width = self._adaptive_overlay_width()
        margin = self._edge_margin()
        overlay_height = max(1, parent_height - margin * 2)
        self._apply_adaptive_layout()

        if self.side == 'left':
            start_x = -self.overlay_width
            end_x = margin
        elif self.side == 'right':
            start_x = parent_width
            end_x = parent_width - self.overlay_width - margin
        else:  # top
            start_x = 0
            end_x = 0

        self.setGeometry(start_x, margin, self.overlay_width, overlay_height)
        self.show()
        self.raise_()
        main_window = self._find_main_window()
        if main_window and hasattr(main_window, "_sync_player_controls_suppression"):
            main_window._sync_player_controls_suppression()

        # 滑入动画
        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.setStartValue(QRect(start_x, margin, self.overlay_width, overlay_height))
        self.animation.setEndValue(QRect(end_x, margin, self.overlay_width, overlay_height))
        self.animation.start()

        self.reset_hide_timer()

    def hide_with_animation(self):
        """滑出动画隐藏"""
        if not self.isVisible() or not self.parent():
            return

        parent_height = self.parent().height()
        parent_width = self.parent().width()
        current_x = self.x()
        margin = self._edge_margin()
        overlay_height = max(1, parent_height - margin * 2)

        if self.side == 'left':
            end_x = -self.overlay_width
        elif self.side == 'right':
            end_x = parent_width
        else:
            end_x = current_x

        # 滑出动画
        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.InCubic)
        self.animation.setStartValue(QRect(current_x, margin, self.overlay_width, overlay_height))
        self.animation.setEndValue(QRect(end_x, margin, self.overlay_width, overlay_height))
        self.animation.finished.connect(self.hide)
        self.animation.finished.connect(self._on_hide_finished)
        self.animation.start()

    def _on_hide_finished(self):
        """隐藏动画完成后的回调"""
        # 检查是否还有其他覆盖层可见
        # 如果所有覆盖层都已隐藏，重新启用触发区域
        if self.parent() and self.parent().parent():
            main_window = self._find_main_window()
            if main_window:
                self._check_and_enable_triggers(main_window)
                if hasattr(main_window, "_sync_player_controls_suppression"):
                    main_window._sync_player_controls_suppression()

    def _find_main_window(self):
        """查找 MainWindow 实例"""
        window = self.window()
        if window and hasattr(window, 'player_panel'):
            return window
        parent = self.parent()
        while parent:
            # 尝试向上查找，直到找到有 player_panel 属性的对象
            if hasattr(parent, 'parent') and callable(parent.parent):
                parent = parent.parent()
                if hasattr(parent, 'player_panel'):
                    return parent
            else:
                break
        return None

    def _check_and_enable_triggers(self, main_window):
        """检查并启用触发区域（如果所有覆盖层都已隐藏）"""
        # 检查是否所有覆盖层都不可见
        all_hidden = True
        overlays = [
            main_window.toolbar_overlay,
            main_window.nav_overlay,
            main_window.channel_list_overlay,
            main_window.detail_overlay,
        ]
        playlist_overlay = getattr(main_window, "playlist_overlay", None)
        if playlist_overlay is not None:
            overlays.append(playlist_overlay)
        settings_overlay = getattr(main_window, "settings_overlay", None)
        if settings_overlay is not None:
            overlays.append(settings_overlay)
        for overlay in overlays:
            if overlay.isVisible():
                all_hidden = False
                break

        # 如果所有覆盖层都隐藏了，重新启用触发区域
        if all_hidden:
            player_panel = getattr(main_window, "player_panel", None)
            if player_panel and hasattr(player_panel, "_enable_triggers_interaction"):
                player_panel._enable_triggers_interaction()

    def toggle(self):
        """切换显示/隐藏"""
        if self.isVisible():
            self.hide_with_animation()
        else:
            self.show_with_animation()
