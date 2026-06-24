"""About dialog for IPTV Ultimate Player."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ui.dialog_style import apply_light_dialog_style
from utils.app_paths import resource_path


APP_NAME = "IPTV Ultimate Player"
APP_DISPLAY_NAME = "IPTV 播放器"
APP_VERSION = os.environ.get("APP_VERSION", "0.0.0")
GITHUB_URL = "https://github.com/davidchiu66/IPTV_Ultimate_Player_Codex"
RELEASES_URL = f"{GITHUB_URL}/releases"
APP_ICON_PATH = "docs/assets/icons/iptv-icon-02-signal-orbit-256.png"


class AboutDialog(QDialog):
    """Glass-style application about dialog."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"关于 {APP_DISPLAY_NAME}")
        self.setMinimumWidth(520)
        apply_light_dialog_style(self)
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the about dialog layout."""
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 22)
        root.setSpacing(18)

        header = QHBoxLayout()
        header.setSpacing(18)

        icon_label = QLabel(self)
        pixmap = QPixmap(resource_path(APP_ICON_PATH))
        if not pixmap.isNull():
            icon_label.setPixmap(
                pixmap.scaled(84, 84, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        icon_label.setFixedSize(88, 88)
        icon_label.setAlignment(Qt.AlignCenter)
        header.addWidget(icon_label, 0, Qt.AlignTop)

        title_col = QVBoxLayout()
        title_col.setSpacing(6)

        name_label = QLabel(APP_NAME, self)
        name_label.setObjectName("aboutTitle")
        name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        title_col.addWidget(name_label)

        version_label = QLabel(f"{APP_DISPLAY_NAME} · 版本 {APP_VERSION}", self)
        version_label.setObjectName("aboutVersion")
        version_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        title_col.addWidget(version_label)

        summary = QLabel(
            "一个基于 PySide6 + libmpv 的 Windows IPTV 与本地媒体播放器，"
            "集成直播源管理、本地播放、收藏、播放列表、浏览器播放和现代化玻璃拟态界面。",
            self,
        )
        summary.setObjectName("aboutSummary")
        summary.setWordWrap(True)
        summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        title_col.addWidget(summary)

        header.addLayout(title_col, 1)
        root.addLayout(header)

        line = QFrame(self)
        line.setObjectName("aboutLine")
        line.setFrameShape(QFrame.HLine)
        root.addWidget(line)

        github_label = QLabel(
            f'<a href="{GITHUB_URL}">{GITHUB_URL}</a>',
            self,
        )
        github_label.setObjectName("aboutLink")
        github_label.setOpenExternalLinks(True)
        github_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        root.addWidget(github_label)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addStretch(1)

        check_button = QPushButton("检查版本更新", self)
        check_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(RELEASES_URL)))
        actions.addWidget(check_button)

        update_button = QPushButton("在线更新", self)
        update_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(RELEASES_URL)))
        actions.addWidget(update_button)

        close_button = QPushButton("关闭", self)
        close_button.setObjectName("secondaryButton")
        close_button.clicked.connect(self.accept)
        actions.addWidget(close_button)
        root.addLayout(actions)

        self.setStyleSheet(
            self.styleSheet()
            + """
            QLabel#aboutTitle {
                color: #ffffff;
                font-size: 22px;
                font-weight: 700;
                background: transparent;
            }
            QLabel#aboutVersion {
                color: #9fc9ff;
                font-size: 13px;
                background: transparent;
            }
            QLabel#aboutSummary {
                color: #d7e6ff;
                font-size: 13px;
                line-height: 1.45;
                background: transparent;
            }
            QLabel#aboutLink {
                color: #9fc9ff;
                font-size: 13px;
                background: transparent;
            }
            QLabel#aboutLink a {
                color: #8fd0ff;
                text-decoration: none;
            }
            QFrame#aboutLine {
                color: rgba(120, 180, 255, 80);
                background: rgba(120, 180, 255, 80);
                max-height: 1px;
            }
            """
        )
