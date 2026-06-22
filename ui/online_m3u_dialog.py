#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在线 m3u URL 输入对话框"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel
)
from PySide6.QtCore import Qt

from ui.dialog_style import apply_light_dialog_style


class OnlineM3uDialog(QDialog):
    """在线 m3u URL 输入对话框

    提供三个操作选项：
    - 播放：下载到临时文件并播放
    - 另存：保存到本地文件并播放
    - 取消：关闭对话框
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("打开在线 m3u")
        self.setMinimumWidth(500)
        apply_light_dialog_style(self)

        self.url = ""
        self.action = None  # 'play', 'save', 或 None

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 提示文字
        label = QLabel("请输入 m3u URL：")
        label.setStyleSheet("font-size: 14px;")
        layout.addWidget(label)

        # URL 输入框
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("http://example.com/playlist.m3u")
        self.url_input.setText("http://")
        self.url_input.setMinimumHeight(30)
        layout.addWidget(self.url_input)

        # 按钮行
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.play_button = QPushButton("播放")
        self.play_button.setMinimumWidth(80)
        self.play_button.setMinimumHeight(32)
        self.play_button.clicked.connect(self._on_play)
        self.play_button.setDefault(True)  # 默认按钮（回车触发）
        button_layout.addWidget(self.play_button)

        self.save_button = QPushButton("另存")
        self.save_button.setMinimumWidth(80)
        self.save_button.setMinimumHeight(32)
        self.save_button.clicked.connect(self._on_save)
        button_layout.addWidget(self.save_button)

        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("secondaryButton")
        self.cancel_button.setMinimumWidth(80)
        self.cancel_button.setMinimumHeight(32)
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

        # 焦点设置到输入框
        self.url_input.setFocus()
        self.url_input.selectAll()

    def _on_play(self):
        """播放按钮：直接播放"""
        self.url = self.url_input.text().strip()
        if self.url and len(self.url) > 7:  # 至少是 "http://"
            self.action = 'play'
            self.accept()
        else:
            self.url_input.setFocus()

    def _on_save(self):
        """另存按钮：保存到本地并播放"""
        self.url = self.url_input.text().strip()
        if self.url and len(self.url) > 7:
            self.action = 'save'
            self.accept()
        else:
            self.url_input.setFocus()

    def get_result(self):
        """返回 (action, url)

        Returns:
            tuple: (action, url) 其中 action 为 'play'、'save' 或 None
        """
        return self.action, self.url
