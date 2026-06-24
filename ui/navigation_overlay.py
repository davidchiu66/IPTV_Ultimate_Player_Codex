import os

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QRadioButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.base_overlay import BaseOverlay
from utils.media_types import resource_label, resource_type_key, resource_type_label


FAVORITE_ROLE = Qt.UserRole + 10
STAR_AREA_WIDTH = 32


class FavoriteStarDelegate(QStyledItemDelegate):
    """Draw a right-aligned favorite star without per-row widgets."""

    def paint(self, painter, option, index):
        painter.save()
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(73, 106, 153, 180))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(option.rect, QColor(120, 180, 255, 45))
        painter.restore()

        text_option = QStyleOptionViewItem(option)
        text_option.rect = option.rect.adjusted(0, 0, -STAR_AREA_WIDTH, 0)
        text_option.textElideMode = Qt.ElideRight
        super().paint(painter, text_option, index)

        favorite = bool(index.data(FAVORITE_ROLE))
        star = "★" if favorite else "☆"
        painter.save()
        painter.setPen(QColor("#ffd56a" if favorite else "#9aa8be"))
        painter.drawText(
            option.rect.adjusted(0, 0, -10, 0),
            Qt.AlignRight | Qt.AlignVCenter,
            star,
        )
        painter.restore()


class NavigationOverlay(BaseOverlay):
    """Resource library overlay with directory and favorite tabs."""

    file_selected = Signal(str)
    open_directory_requested = Signal()
    open_url_requested = Signal()
    refresh_requested = Signal()
    delete_file_requested = Signal(str)

    resource_favorite_selected = Signal(str, str)
    resource_favorite_removed = Signal(str)
    resource_favorite_toggle_requested = Signal(str)
    channel_favorite_selected = Signal(dict, str)
    channel_favorite_removed = Signal(str)
    favorites_refresh_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, side="left", width=380)
        self.setObjectName("navOverlay")
        self._all_file_paths: list[str] = []
        self._resource_filter = "all"
        self._resource_favorite_filter = "all"
        self._resource_favorite_keyword = ""
        self._channel_favorite_keyword = ""
        self._resource_favorite_paths: set[str] = set()
        self._resource_favorites: list[dict] = []
        self._channel_favorites: list[dict] = []

        self.setStyleSheet("""
            #navOverlay {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(58, 68, 86, 235),
                    stop:1 rgba(22, 28, 37, 235)
                );
                border: 1px solid rgba(120, 180, 255, 125);
                border-radius: 18px;
            }
            QLabel#panelTitle {
                color: #f3f7ff;
                font-size: 20px;
                font-weight: 700;
                background: transparent;
            }
            QLabel {
                color: #d7e6ff;
                background: transparent;
            }
            QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
            QScrollBar::handle:vertical { background: rgba(120, 180, 255, 120); border-radius: 4px; min-height: 24px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QRadioButton {
                color: #d7e6ff;
                font-size: 12px;
                spacing: 5px;
                background: transparent;
            }
            QRadioButton::indicator { width: 13px; height: 13px; }
            QLineEdit {
                background: rgba(18, 22, 29, 210);
                color: #f2f6ff;
                border: 1px solid rgba(120, 180, 255, 90);
                border-radius: 8px;
                padding: 6px 8px;
                font-size: 12px;
                selection-background-color: rgba(105, 178, 255, 150);
            }
            QTabWidget::pane {
                border: 1px solid rgba(120, 180, 255, 75);
                border-radius: 10px;
                background: rgba(12, 18, 25, 120);
            }
            QTabBar::tab {
                background: rgba(255, 255, 255, 18);
                color: #c7d7ef;
                padding: 7px 9px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background: rgba(120, 180, 255, 65);
                color: #ffffff;
                font-weight: 600;
            }
        """)

        layout = QVBoxLayout(self)
        self._root_layout = layout
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("资源库")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(lambda _index: self.favorites_refresh_requested.emit())
        layout.addWidget(self.tabs, 1)

        self._build_directory_tab()
        self._build_resource_favorites_tab()
        self._build_channel_favorites_tab()

        self.cancel_button = QPushButton("取消")
        self.cancel_button.setStyleSheet(self._button_style())
        self.cancel_button.clicked.connect(self.hide_with_animation)
        layout.addWidget(self.cancel_button)

        self.btn_open.clicked.connect(self.open_directory_requested.emit)
        self.btn_open_url.clicked.connect(self.open_url_requested.emit)
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        self.file_list.itemDoubleClicked.connect(self._on_file_clicked)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._show_file_context_menu)
        self.file_list.viewport().installEventFilter(self)

    def eventFilter(self, watched, event):
        if not hasattr(self, "file_list"):
            return super().eventFilter(watched, event)
        if watched is self.file_list.viewport() and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                item = self.file_list.itemAt(event.position().toPoint())
                if item:
                    rect = self.file_list.visualItemRect(item)
                    if event.position().toPoint().x() >= rect.right() - STAR_AREA_WIDTH:
                        path = item.data(Qt.UserRole)
                        if path:
                            self.resource_favorite_toggle_requested.emit(path)
                            return True
        return super().eventFilter(watched, event)

    def _button_style(self) -> str:
        padding = 5 if self._is_compact_viewport() else 8
        font_size = 12 if self._is_compact_viewport() else 13
        return f"""
            QPushButton {{
                background: rgba(255, 255, 255, 24);
                color: #f4f8ff;
                border: 1px solid rgba(120, 180, 255, 105);
                border-radius: 8px;
                padding: {padding}px;
                font-size: {font_size}px;
            }}
            QPushButton:hover {{
                background: rgba(120, 180, 255, 55);
                border: 1px solid rgba(120, 180, 255, 160);
            }}
            QPushButton:disabled {{
                background: rgba(255, 255, 255, 10);
                color: rgba(220, 230, 245, 95);
                border: 1px solid rgba(120, 180, 255, 45);
            }}
        """

    def _list_style(self) -> str:
        padding = 4 if self._is_compact_viewport() else 6
        return f"""
            QListWidget {{
                background: rgba(13, 18, 26, 190);
                color: #edf4ff;
                border: 1px solid rgba(120, 180, 255, 70);
                border-radius: 8px;
                outline: 0;
            }}
            QListWidget::item {{
                padding: {padding}px 8px;
                border-bottom: 1px solid rgba(255, 255, 255, 18);
            }}
            QListWidget::item:selected {{
                background: rgba(105, 178, 255, 115);
                color: #ffffff;
                border-radius: 5px;
            }}
            QListWidget::item:hover {{
                background: rgba(120, 180, 255, 40);
                border-radius: 5px;
            }}
        """

    def _configure_list_widget(self, widget: QListWidget) -> None:
        """Keep resource names inside the panel and avoid horizontal scrolling."""
        widget.setWordWrap(False)
        widget.setTextElideMode(Qt.ElideRight)
        widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        widget.setUniformItemSizes(True)

    def _apply_adaptive_layout(self) -> None:
        """Compact the resource overlay on high-DPI small logical screens."""
        compact = self._is_compact_viewport()
        root_margin = 12 if compact else 18
        root_spacing = 8 if compact else 12
        page_margin = 8 if compact else 12
        page_spacing = 6 if compact else 10
        list_min_height = 110 if compact else 150

        self._root_layout.setContentsMargins(root_margin, root_margin, root_margin, root_margin)
        self._root_layout.setSpacing(root_spacing)
        for layout in (
            getattr(self, "_directory_layout", None),
            getattr(self, "_resource_favorites_layout", None),
            getattr(self, "_channel_favorites_layout", None),
        ):
            if layout is not None:
                layout.setContentsMargins(page_margin, page_margin, page_margin, page_margin)
                layout.setSpacing(page_spacing)

        button_style = self._button_style()
        for button in (
            getattr(self, "btn_open", None),
            getattr(self, "btn_open_url", None),
            getattr(self, "btn_refresh", None),
            getattr(self, "btn_delete", None),
            getattr(self, "btn_use_resource_favorite", None),
            getattr(self, "btn_remove_resource_favorite", None),
            getattr(self, "btn_refresh_resource_favorites", None),
            getattr(self, "btn_play_channel_favorite", None),
            getattr(self, "btn_remove_channel_favorite", None),
            getattr(self, "btn_refresh_channel_favorites", None),
            getattr(self, "cancel_button", None),
        ):
            if button is not None:
                button.setStyleSheet(button_style)

        list_style = self._list_style()
        for widget in (
            getattr(self, "file_list", None),
            getattr(self, "resource_favorite_list", None),
            getattr(self, "channel_favorite_list", None),
        ):
            if widget is not None:
                widget.setStyleSheet(list_style)
                widget.setMinimumHeight(list_min_height)

    def _build_directory_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self._directory_layout = layout
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.btn_open = QPushButton("打开资源目录")
        self.btn_open_url = QPushButton("打开在线资源")
        self.btn_refresh = QPushButton("刷新当前目录")
        self.btn_delete = QPushButton("删除选中文件")
        for btn in [self.btn_open, self.btn_open_url, self.btn_refresh, self.btn_delete]:
            btn.setStyleSheet(self._button_style())

        layout.addWidget(self.btn_open)
        layout.addWidget(self.btn_open_url)
        layout.addWidget(self.btn_refresh)

        info_label = QLabel("当前目录")
        info_label.setObjectName("sectionLabel")
        layout.addWidget(info_label)

        self.dir_label = QLabel("-")
        self.dir_label.setObjectName("infoValue")
        self.dir_label.setWordWrap(True)
        layout.addWidget(self.dir_label)

        self.file_count_label = QLabel("资源数：0")
        self.file_count_label.setObjectName("metaValue")
        layout.addWidget(self.file_count_label)

        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(8)
        filter_row2 = QHBoxLayout()
        filter_row2.setContentsMargins(0, 0, 0, 0)
        filter_row2.setSpacing(8)
        self.filter_group = QButtonGroup(self)
        self.filter_all = QRadioButton("全部")
        self.filter_channels = QRadioButton("频道")
        self.filter_videos = QRadioButton("视频")
        self.filter_audios = QRadioButton("音频")
        self.filter_gifs = QRadioButton("GIF")
        self.filter_images = QRadioButton("图片")
        self.filter_all.setChecked(True)
        for index, (key, radio) in enumerate((
            ("all", self.filter_all),
            ("channel_resource", self.filter_channels),
            ("video", self.filter_videos),
            ("audio", self.filter_audios),
            ("gif", self.filter_gifs),
            ("image", self.filter_images),
        )):
            self.filter_group.addButton(radio)
            radio.toggled.connect(lambda checked, filter_key=key: self._on_filter_changed(filter_key, checked))
            (filter_row if index < 4 else filter_row2).addWidget(radio)
        filter_row.addStretch(1)
        filter_row2.addStretch(1)
        layout.addLayout(filter_row)
        layout.addLayout(filter_row2)

        file_label = QLabel("资源文件")
        file_label.setObjectName("sectionLabel")
        layout.addWidget(file_label)

        self.file_list = QListWidget()
        self.file_list.setStyleSheet(self._list_style())
        self.file_list.setItemDelegate(FavoriteStarDelegate(self.file_list))
        self._configure_list_widget(self.file_list)
        layout.addWidget(self.file_list, 1)
        layout.addWidget(self.btn_delete)
        self.tabs.addTab(page, "资源目录")

    def _build_resource_favorites_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self._resource_favorites_layout = layout
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        label = QLabel("收藏的频道、视频、音频、GIF 和图片")
        label.setObjectName("hintLabel")
        layout.addWidget(label)

        self.resource_favorite_search = QLineEdit()
        self.resource_favorite_search.setPlaceholderText("搜索资源名称或路径...")
        self.resource_favorite_search.textChanged.connect(self._on_resource_favorite_search_changed)
        layout.addWidget(self.resource_favorite_search)

        favorite_filter_row = QHBoxLayout()
        favorite_filter_row.setContentsMargins(0, 0, 0, 0)
        favorite_filter_row.setSpacing(8)
        favorite_filter_row2 = QHBoxLayout()
        favorite_filter_row2.setContentsMargins(0, 0, 0, 0)
        favorite_filter_row2.setSpacing(8)
        self.resource_favorite_filter_group = QButtonGroup(self)
        self.resource_favorite_filter_all = QRadioButton("全部")
        self.resource_favorite_filter_channels = QRadioButton("频道")
        self.resource_favorite_filter_videos = QRadioButton("视频")
        self.resource_favorite_filter_audios = QRadioButton("音频")
        self.resource_favorite_filter_gifs = QRadioButton("GIF")
        self.resource_favorite_filter_images = QRadioButton("图片")
        self.resource_favorite_filter_all.setChecked(True)
        for index, (key, radio) in enumerate((
            ("all", self.resource_favorite_filter_all),
            ("channel_resource", self.resource_favorite_filter_channels),
            ("video", self.resource_favorite_filter_videos),
            ("audio", self.resource_favorite_filter_audios),
            ("gif", self.resource_favorite_filter_gifs),
            ("image", self.resource_favorite_filter_images),
        )):
            self.resource_favorite_filter_group.addButton(radio)
            radio.toggled.connect(
                lambda checked, filter_key=key: self._on_resource_favorite_filter_changed(filter_key, checked)
            )
            (favorite_filter_row if index < 4 else favorite_filter_row2).addWidget(radio)
        favorite_filter_row.addStretch(1)
        favorite_filter_row2.addStretch(1)
        layout.addLayout(favorite_filter_row)
        layout.addLayout(favorite_filter_row2)

        self.resource_favorite_list = QListWidget()
        self.resource_favorite_list.setStyleSheet(self._list_style())
        self._configure_list_widget(self.resource_favorite_list)
        self.resource_favorite_list.itemDoubleClicked.connect(self._on_resource_favorite_clicked)
        layout.addWidget(self.resource_favorite_list, 1)

        row = QHBoxLayout()
        self.btn_use_resource_favorite = QPushButton("使用/播放")
        self.btn_remove_resource_favorite = QPushButton("取消收藏")
        self.btn_refresh_resource_favorites = QPushButton("刷新状态")
        for btn in [self.btn_use_resource_favorite, self.btn_remove_resource_favorite, self.btn_refresh_resource_favorites]:
            btn.setStyleSheet(self._button_style())
            row.addWidget(btn)
        layout.addLayout(row)

        self.btn_use_resource_favorite.clicked.connect(self._use_selected_resource_favorite)
        self.btn_remove_resource_favorite.clicked.connect(self._remove_selected_resource_favorite)
        self.btn_refresh_resource_favorites.clicked.connect(self.favorites_refresh_requested.emit)
        self.tabs.addTab(page, "资源收藏")

    def _build_channel_favorites_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self._channel_favorites_layout = layout
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        label = QLabel("收藏的单个频道")
        label.setObjectName("hintLabel")
        layout.addWidget(label)

        self.channel_favorite_search = QLineEdit()
        self.channel_favorite_search.setPlaceholderText("搜索频道名称、分类、来源或类型...")
        self.channel_favorite_search.textChanged.connect(self._on_channel_favorite_search_changed)
        layout.addWidget(self.channel_favorite_search)

        self.channel_favorite_list = QListWidget()
        self.channel_favorite_list.setStyleSheet(self._list_style())
        self._configure_list_widget(self.channel_favorite_list)
        self.channel_favorite_list.itemDoubleClicked.connect(self._on_channel_favorite_clicked)
        layout.addWidget(self.channel_favorite_list, 1)

        row = QHBoxLayout()
        self.btn_play_channel_favorite = QPushButton("播放")
        self.btn_remove_channel_favorite = QPushButton("取消收藏")
        self.btn_refresh_channel_favorites = QPushButton("刷新状态")
        for btn in [self.btn_play_channel_favorite, self.btn_remove_channel_favorite, self.btn_refresh_channel_favorites]:
            btn.setStyleSheet(self._button_style())
            row.addWidget(btn)
        layout.addLayout(row)

        self.btn_play_channel_favorite.clicked.connect(self._use_selected_channel_favorite)
        self.btn_remove_channel_favorite.clicked.connect(self._remove_selected_channel_favorite)
        self.btn_refresh_channel_favorites.clicked.connect(self.favorites_refresh_requested.emit)
        self.tabs.addTab(page, "频道收藏")

    def _on_file_clicked(self, item: QListWidgetItem) -> None:
        file_path = item.data(Qt.UserRole)
        if file_path:
            self.file_selected.emit(file_path)

    def _on_delete_clicked(self) -> None:
        current_item = self.file_list.currentItem()
        if current_item:
            file_path = current_item.data(Qt.UserRole)
            self.delete_file_requested.emit(file_path)

    def _show_file_context_menu(self, pos) -> None:
        item = self.file_list.itemAt(pos)
        if not item:
            return
        path = item.data(Qt.UserRole)
        if not path:
            return
        menu = QMenu(self)
        action_text = "取消收藏" if self._is_resource_favorite(path) else "添加到收藏"
        favorite_action = menu.addAction(action_text)
        open_action = menu.addAction("使用/播放")
        action = menu.exec(self.file_list.mapToGlobal(pos))
        if action == favorite_action:
            self.resource_favorite_toggle_requested.emit(path)
        elif action == open_action:
            self.file_selected.emit(path)

    def update_info(self, dir_path: str = "", file_count: int = 0) -> None:
        self.dir_label.setText(dir_path or "-")
        shown = self.file_list.count() if hasattr(self, "file_list") else file_count
        if file_count and shown != file_count:
            self.file_count_label.setText(f"资源数：{shown} / {file_count}")
        else:
            self.file_count_label.setText(f"资源数：{file_count}")

    def set_scanning(self, dir_path: str = "") -> None:
        self._all_file_paths = []
        self.dir_label.setText(dir_path or "-")
        self.file_count_label.setText("正在扫描资源...")
        self.file_list.clear()

    def set_files(self, file_paths) -> None:
        self._all_file_paths = list(file_paths or [])
        self._apply_file_filter()

    def set_resource_favorite_paths(self, paths) -> None:
        self._resource_favorite_paths = {os.path.normcase(os.path.normpath(os.path.abspath(path))) for path in paths or []}
        self._apply_file_filter()

    def set_resource_favorites(self, items) -> None:
        self._resource_favorites = list(items or [])
        self._apply_resource_favorite_filter()

    def _apply_resource_favorite_filter(self) -> None:
        self.resource_favorite_list.clear()
        keyword = self._resource_favorite_keyword.strip().lower()
        for favorite in self._filtered_resource_favorites():
            status = favorite.get("status_text") or ""
            name = favorite.get("name") or os.path.basename(favorite.get("path") or "")
            type_label = resource_type_label(self._resource_favorite_type(favorite))
            text = f"[{type_label}] {name}  [{status}]"
            item = QListWidgetItem(text)
            item.setToolTip(favorite.get("path") or "")
            item.setData(Qt.UserRole, favorite)
            if favorite.get("status") != "ok":
                item.setForeground(QColor("#8fa2bc"))
            self.resource_favorite_list.addItem(item)

    def set_channel_favorites(self, items) -> None:
        self._channel_favorites = list(items or [])
        self._apply_channel_favorite_filter()

    def _apply_channel_favorite_filter(self) -> None:
        self.channel_favorite_list.clear()
        for favorite in self._filtered_channel_favorites():
            status = favorite.get("status_text") or ""
            name = favorite.get("name") or "未命名频道"
            category = favorite.get("category") or "未分组"
            stream_type = self._channel_stream_type_label(favorite)
            text = f"[{stream_type}] {name}  ·  {category}  [{status}]"
            item = QListWidgetItem(text)
            item.setToolTip(favorite.get("source_path") or "频道快照")
            item.setData(Qt.UserRole, favorite)
            if favorite.get("status") in ("source_missing", "source_error", "changed"):
                item.setForeground(QColor("#8fa2bc"))
            self.channel_favorite_list.addItem(item)

    def _on_filter_changed(self, filter_key: str, checked: bool) -> None:
        if not checked:
            return
        self._resource_filter = filter_key
        self._apply_file_filter()

    def _filtered_paths(self) -> list[str]:
        if self._resource_filter != "all":
            return [path for path in self._all_file_paths if resource_type_key(path) == self._resource_filter]
        return list(self._all_file_paths)

    def _on_resource_favorite_filter_changed(self, filter_key: str, checked: bool) -> None:
        if not checked:
            return
        self._resource_favorite_filter = filter_key
        self._apply_resource_favorite_filter()

    def _on_resource_favorite_search_changed(self, text: str) -> None:
        self._resource_favorite_keyword = text or ""
        self._apply_resource_favorite_filter()

    def _on_channel_favorite_search_changed(self, text: str) -> None:
        self._channel_favorite_keyword = text or ""
        self._apply_channel_favorite_filter()

    def _resource_favorite_type(self, favorite: dict) -> str:
        path = favorite.get("path") or ""
        detected = resource_type_key(path)
        if detected != "unknown":
            return detected
        return str(favorite.get("type") or "unknown")

    def _filtered_resource_favorites(self) -> list[dict]:
        keyword = self._resource_favorite_keyword.strip().lower()
        result = []
        for favorite in self._resource_favorites:
            type_key = self._resource_favorite_type(favorite)
            if self._resource_favorite_filter != "all" and type_key != self._resource_favorite_filter:
                continue
            haystack = " ".join(
                str(value or "")
                for value in (
                    favorite.get("name"),
                    favorite.get("path"),
                    favorite.get("status_text"),
                    resource_type_label(type_key),
                )
            ).lower()
            if keyword and keyword not in haystack:
                continue
            result.append(favorite)
        return result

    def _channel_stream_type_label(self, favorite: dict) -> str:
        channel = favorite.get("channel") if isinstance(favorite, dict) else {}
        if not isinstance(channel, dict):
            channel = {}
        manifest_type = str(channel.get("ManifestType") or "").strip().lower()
        manifest = str(channel.get("Manifest") or "").strip().lower()
        resolved_info = channel.get("resolved_info")
        resolved_type = ""
        if isinstance(resolved_info, dict):
            resolved_type = str(resolved_info.get("media_type") or "").strip().lower()
        probe_markers = ("page", "web", "html", "browser", "probe")
        if manifest_type in {"hls", "m3u8"} or resolved_type in {"hls", "m3u8"} or ".m3u8" in manifest:
            return "HLS"
        if manifest_type in {"dash", "mpd"} or resolved_type in {"dash", "mpd"} or ".mpd" in manifest:
            return "DASH"
        if manifest_type == "flv" or resolved_type == "flv" or ".flv" in manifest:
            return "FLV"
        if manifest_type == "mp4" or ".mp4" in manifest:
            return "MP4"
        if manifest_type == "ts" or ".ts" in manifest:
            return "TS"
        if channel.get("NeedJsProbe") or any(marker in manifest_type for marker in probe_markers):
            return "页面"
        return "直播"

    def _filtered_channel_favorites(self) -> list[dict]:
        keyword = self._channel_favorite_keyword.strip().lower()
        if not keyword:
            return list(self._channel_favorites)
        result = []
        for favorite in self._channel_favorites:
            channel = favorite.get("channel") if isinstance(favorite.get("channel"), dict) else {}
            stream_type = self._channel_stream_type_label(favorite)
            haystack = " ".join(
                str(value or "")
                for value in (
                    favorite.get("name"),
                    favorite.get("category"),
                    favorite.get("source_name"),
                    favorite.get("status_text"),
                    stream_type,
                    channel.get("ManifestType"),
                    channel.get("Manifest"),
                )
            ).lower()
            if keyword in haystack:
                result.append(favorite)
        return result

    def _is_resource_favorite(self, path: str) -> bool:
        key = os.path.normcase(os.path.normpath(os.path.abspath(path)))
        return key in self._resource_favorite_paths

    def _apply_file_filter(self) -> None:
        self.file_list.clear()
        sorted_paths = sorted(self._filtered_paths(), key=lambda p: os.path.basename(p).lower())

        self.file_list.setUpdatesEnabled(False)
        try:
            for path in sorted_paths:
                item = QListWidgetItem(resource_label(path))
                item.setData(Qt.UserRole, path)
                item.setData(FAVORITE_ROLE, self._is_resource_favorite(path))
                item.setToolTip(path)
                self.file_list.addItem(item)
        finally:
            self.file_list.setUpdatesEnabled(True)
        total = len(self._all_file_paths)
        shown = len(sorted_paths)
        if total and shown != total:
            self.file_count_label.setText(f"资源数：{shown} / {total}")
        else:
            self.file_count_label.setText(f"资源数：{total}")

    def _selected_resource_favorite(self) -> dict | None:
        item = self.resource_favorite_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _selected_channel_favorite(self) -> dict | None:
        item = self.channel_favorite_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _on_resource_favorite_clicked(self, item: QListWidgetItem) -> None:
        favorite = item.data(Qt.UserRole)
        if favorite:
            self.resource_favorite_selected.emit(favorite.get("path") or "", favorite.get("id") or "")

    def _use_selected_resource_favorite(self) -> None:
        favorite = self._selected_resource_favorite()
        if favorite:
            self.resource_favorite_selected.emit(favorite.get("path") or "", favorite.get("id") or "")

    def _remove_selected_resource_favorite(self) -> None:
        favorite = self._selected_resource_favorite()
        if favorite:
            self.resource_favorite_removed.emit(favorite.get("id") or "")

    def _on_channel_favorite_clicked(self, item: QListWidgetItem) -> None:
        favorite = item.data(Qt.UserRole)
        if favorite:
            self.channel_favorite_selected.emit(dict(favorite.get("channel") or {}), favorite.get("id") or "")

    def _use_selected_channel_favorite(self) -> None:
        favorite = self._selected_channel_favorite()
        if favorite:
            self.channel_favorite_selected.emit(dict(favorite.get("channel") or {}), favorite.get("id") or "")

    def _remove_selected_channel_favorite(self) -> None:
        favorite = self._selected_channel_favorite()
        if favorite:
            self.channel_favorite_removed.emit(favorite.get("id") or "")
