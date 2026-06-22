from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QVBoxLayout, QLabel, QPushButton,
                               QScrollArea, QWidget, QFrame)
from ui.base_overlay import BaseOverlay


class DetailOverlay(BaseOverlay):
    """频道详情覆盖层"""
    edit_requested = Signal()
    add_requested = Signal()
    delete_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, side='right', width=380)
        self.setObjectName("detailOverlay")
        # 浅色调（与频道列表统一）
        self.setStyleSheet("""
            #detailOverlay { background: #f4f4f6; border-radius: 12px; }
            QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
            QScrollBar::handle:vertical { background: #c4c4cc; border-radius: 4px; min-height: 24px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # 标题（放大、更美观）
        title = QLabel("频道详情")
        title.setStyleSheet("color: #1a1a1a; font-size: 22px; font-weight: 700;")
        layout.addWidget(title)

        # 滚动区域（关闭横向滚动条，内容靠自动换行约束在视口宽度内）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QWidget { background: transparent; }
        """)

        # 内容容器
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)

        # 占位文本
        self.placeholder = QLabel("未选择频道")
        self.placeholder.setStyleSheet("color: #8a8a8a; font-size: 13px;")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(self.placeholder)
        self.content_layout.addStretch()

        scroll.setWidget(self.content_widget)
        layout.addWidget(scroll, 1)

        # 按钮区域
        btn_container = QFrame()
        btn_layout = QVBoxLayout(btn_container)
        btn_layout.setContentsMargins(0, 10, 0, 0)
        btn_layout.setSpacing(8)

        self.btn_edit = QPushButton("编辑频道")
        self.btn_add = QPushButton("添加频道")
        self.btn_delete = QPushButton("删除频道")

        for btn in [self.btn_edit, self.btn_add, self.btn_delete]:
            btn.setStyleSheet("""
                QPushButton {
                    background: #3d6fb0;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 9px;
                    font-size: 13px;
                }
                QPushButton:hover { background: #4a7fc4; }
            """)
            btn_layout.addWidget(btn)

        layout.addWidget(btn_container)

        # 连接信号
        self.btn_edit.clicked.connect(self.edit_requested.emit)
        self.btn_add.clicked.connect(self.add_requested.emit)
        self.btn_delete.clicked.connect(self.delete_requested.emit)

        self.current_channel = None

    def set_channel(self, channel):
        """设置频道详情"""
        self.current_channel = channel

        # 清除旧内容（但保留 placeholder，避免删除后无法使用）
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                widget = item.widget()
                # 不删除 placeholder，只是从布局中移除
                if widget is not self.placeholder:
                    widget.deleteLater()

        if not channel:
            # 显示占位文本
            self.placeholder.setText("未选择频道")
            self.placeholder.show()
            self.content_layout.addWidget(self.placeholder)
            self.content_layout.addStretch()
            self.btn_edit.setEnabled(False)
            self.btn_delete.setEnabled(False)
            return

        # 隐藏占位符（有频道信息时）
        self.placeholder.hide()

        self.btn_edit.setEnabled(True)
        self.btn_delete.setEnabled(True)

        # 显示频道信息（流地址移到最后、置于 DRM 类型下面；所有字段自动换行）
        self._add_field("频道名称", channel.get("Name", "-"), word_wrap=True)
        self.content_layout.addSpacing(5)
        self._add_field("分类", channel.get("Category", "-"), word_wrap=True)
        self._add_field("Logo", channel.get("LogoUrl", "-"), word_wrap=True)
        self._add_field("TVG ID", channel.get("TvgId", "-"), word_wrap=True)
        self._add_field("TVG Name", channel.get("TvgName", "-"), word_wrap=True)
        self._add_field("DRM类型", channel.get("DrmType", "none"), word_wrap=True)
        self._add_field("流地址", channel.get("Manifest", "-"), word_wrap=True)

        self.content_layout.addStretch()

    def _add_field(self, label_text, value_text, word_wrap=False):
        """添加字段显示"""
        label = QLabel(label_text)
        label.setStyleSheet("color: #8a8a8a; font-size: 12px;")
        self.content_layout.addWidget(label)

        value = QLabel(str(value_text))
        value.setStyleSheet("color: #2a2a2a; font-size: 14px;")
        if word_wrap:
            value.setWordWrap(True)
        self.content_layout.addWidget(value)
