import os

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)
from utils.media_types import resource_label
from ui.theme import overlay_qss


class NavigationPanel(QFrame):
    directory_requested = Signal()
    refresh_requested = Signal()
    delete_file_requested = Signal(str)  # 新增：删除文件信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navigationPanel")
        self.setStyleSheet(overlay_qss("navigationPanel"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("资源库")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self.btn_directory = QPushButton("打开资源目录")
        self.btn_refresh = QPushButton("刷新当前目录")
        layout.addWidget(self.btn_directory)
        layout.addWidget(self.btn_refresh)

        dir_label = QLabel("当前目录")
        dir_label.setObjectName("sectionLabel")
        layout.addWidget(dir_label)

        self.directory_value = QLabel("-")
        self.directory_value.setObjectName("infoValue")
        self.directory_value.setWordWrap(True)
        layout.addWidget(self.directory_value)

        self.file_count_value = QLabel("资源数：0")
        self.file_count_value.setObjectName("metaValue")
        layout.addWidget(self.file_count_value)

        active_label = QLabel("当前播放列表")
        active_label.setObjectName("sectionLabel")
        layout.addWidget(active_label)

        self.active_file_value = QLabel("-")
        self.active_file_value.setObjectName("infoValue")
        self.active_file_value.setWordWrap(True)
        layout.addWidget(self.active_file_value)

        recent_label = QLabel("资源文件")
        recent_label.setObjectName("sectionLabel")
        layout.addWidget(recent_label)

        self.file_list = QListWidget()
        layout.addWidget(self.file_list, 1)

        # 新增：删除文件按钮
        self.btn_delete_file = QPushButton("删除选中文件")
        self.btn_delete_file.setObjectName("dangerButton")
        layout.addWidget(self.btn_delete_file)

        self.btn_directory.clicked.connect(self.directory_requested.emit)
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)
        self.btn_delete_file.clicked.connect(self._on_delete_clicked)

    def _on_delete_clicked(self):
        """删除按钮点击处理"""
        current_item = self.file_list.currentItem()
        if current_item:
            file_path = current_item.data(256)
            self.delete_file_requested.emit(file_path)

    def update_context(self, dir_path="", file_count=0, current_path=""):
        self.directory_value.setText(dir_path or "-")
        self.file_count_value.setText(f"资源数：{file_count}")
        self.active_file_value.setText(os.path.basename(current_path) if current_path else "-")

    def set_files(self, file_paths, current_path=""):
        self.file_list.clear()
        # 排序：先按文件名排序
        sorted_paths = sorted(file_paths, key=lambda p: os.path.basename(p).lower())

        for path in sorted_paths:
            item = QListWidgetItem(resource_label(path))
            item.setData(256, path)
            self.file_list.addItem(item)
            if path == current_path:
                self.file_list.setCurrentItem(item)
