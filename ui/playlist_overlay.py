import os

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from ui.base_overlay import BaseOverlay
from ui import message_dialogs
from utils.media_types import resource_type_label


class PlaylistOverlay(BaseOverlay):
    """Right-side local playback playlist panel."""

    album_changed = Signal(str)
    create_album_requested = Signal()
    delete_album_requested = Signal(str)
    edit_album_requested = Signal(str)
    refresh_album_requested = Signal(str)
    add_items_requested = Signal(str)
    remove_items_requested = Signal(str, list)
    move_items_requested = Signal(str, list, str)
    item_selected = Signal(str, str, str)
    memory_play_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent, side="right", width=380)
        self.setObjectName("playlistOverlay")
        self.hide_delay = 5000
        self._albums: list[dict] = []
        self._active_album_id = "default"
        self._items: list[dict] = []

        self.setStyleSheet("""
            #playlistOverlay {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(58, 68, 86, 238),
                    stop:1 rgba(22, 28, 37, 238)
                );
                border: 1px solid rgba(120, 180, 255, 150);
                border-radius: 18px;
            }
            QLabel#panelTitle {
                color: #f3f7ff;
                font-size: 18px;
                font-weight: 700;
                background: transparent;
            }
            QLabel#hintLabel {
                color: #9fc9ff;
                font-size: 12px;
                background: transparent;
            }
            QComboBox {
                background: rgba(18, 22, 29, 215);
                color: #f2f6ff;
                border: 1px solid rgba(120, 180, 255, 105);
                border-radius: 8px;
                padding: 6px 38px 6px 10px;
                min-height: 24px;
            }
            QComboBox:hover {
                border: 1px solid rgba(120, 180, 255, 170);
                background: rgba(32, 42, 57, 230);
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 32px;
                border-left: 1px solid rgba(120, 180, 255, 90);
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
                background: rgba(120, 180, 255, 34);
            }
            QComboBox::down-arrow {
                image: none;
                width: 0;
                height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #dceaff;
                margin-right: 10px;
            }
            QComboBox::drop-down:hover {
                background: rgba(120, 180, 255, 58);
            }
            QComboBox QAbstractItemView {
                background: #202a39;
                color: #f2f6ff;
                selection-background-color: rgba(120, 180, 255, 70);
                border: 1px solid rgba(120, 180, 255, 120);
                outline: 0;
            }
            QListWidget {
                background: rgba(13, 18, 26, 190);
                color: #edf4ff;
                border: 1px solid rgba(120, 180, 255, 75);
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }
            QListWidget::item {
                padding: 5px 4px;
                min-height: 22px;
            }
            QListWidget::item:selected {
                background: rgba(105, 178, 255, 115);
                color: white;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background: rgba(120, 180, 255, 42);
                border-radius: 4px;
            }
            QPushButton {
                background: rgba(255, 255, 255, 24);
                color: #f6f9ff;
                border: 1px solid rgba(120, 180, 255, 105);
                border-radius: 8px;
                padding: 7px 8px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: rgba(120, 180, 255, 55);
                border: 1px solid rgba(120, 180, 255, 160);
            }
            QPushButton#dangerButton {
                background: rgba(150, 70, 70, 100);
                border: 1px solid rgba(255, 150, 150, 100);
            }
            QPushButton#dangerButton:hover {
                background: rgba(180, 85, 85, 135);
                border: 1px solid rgba(255, 170, 170, 135);
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel("播放列表")
        title.setObjectName("panelTitle")
        root.addWidget(title)

        album_row = QHBoxLayout()
        self.album_combo = QComboBox()
        self.album_combo.setToolTip("点击切换播放专辑")
        self.new_button = QPushButton("+")
        self.new_button.setFixedWidth(36)
        self.album_delete_button = QPushButton("-")
        self.album_delete_button.setFixedWidth(36)
        self.album_delete_button.setObjectName("dangerButton")
        self.album_delete_button.setToolTip("删除当前播放列表")
        album_row.addWidget(self.album_combo, 1)
        album_row.addWidget(self.new_button)
        album_row.addWidget(self.album_delete_button)
        root.addLayout(album_row)

        self.hint_label = QLabel("选择专辑后双击媒体播放")
        self.hint_label.setObjectName("hintLabel")
        root.addWidget(self.hint_label)

        self.item_list = QListWidget()
        self.item_list.setTextElideMode(Qt.ElideRight)
        self.item_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.item_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        root.addWidget(self.item_list, 1)

        move_row = QHBoxLayout()
        self.move_top_button = QPushButton("置顶")
        self.move_up_button = QPushButton("上移")
        self.move_down_button = QPushButton("下移")
        self.move_bottom_button = QPushButton("置底")
        move_row.addWidget(self.move_top_button)
        move_row.addWidget(self.move_up_button)
        move_row.addWidget(self.move_down_button)
        move_row.addWidget(self.move_bottom_button)
        root.addLayout(move_row)

        action_row = QHBoxLayout()
        self.settings_button = QPushButton("设置")
        self.refresh_button = QPushButton("刷新")
        self.add_button = QPushButton("添加")
        self.delete_button = QPushButton("删除")
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.setText("移除")
        action_row.addWidget(self.settings_button)
        action_row.addWidget(self.refresh_button)
        action_row.addWidget(self.add_button)
        action_row.addWidget(self.delete_button)
        root.addLayout(action_row)

        bottom_row = QHBoxLayout()
        self.cancel_button = QPushButton("取消")
        self.memory_button = QPushButton("从记忆点开始播放")
        self.cancel_button.clicked.connect(self.hide_with_animation)
        bottom_row.addWidget(self.cancel_button, 1)
        bottom_row.addWidget(self.memory_button, 1)
        root.addLayout(bottom_row)

        self.album_combo.currentIndexChanged.connect(self._on_album_combo_changed)
        self.new_button.clicked.connect(self.create_album_requested.emit)
        self.album_delete_button.clicked.connect(self._emit_delete_album)
        self.settings_button.clicked.connect(self._emit_edit_album)
        self.refresh_button.clicked.connect(self._emit_refresh_album)
        self.add_button.clicked.connect(self._emit_add_items)
        self.delete_button.clicked.connect(self._emit_remove_items)
        self.move_top_button.clicked.connect(lambda: self._emit_move_items("top"))
        self.move_up_button.clicked.connect(lambda: self._emit_move_items("up"))
        self.move_down_button.clicked.connect(lambda: self._emit_move_items("down"))
        self.move_bottom_button.clicked.connect(lambda: self._emit_move_items("bottom"))
        self.memory_button.clicked.connect(self._emit_memory_play)
        self.item_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.item_list.itemSelectionChanged.connect(self._update_item_action_state)
        self.item_list.viewport().installEventFilter(self)
        self._update_item_action_state()

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.MouseMove, QEvent.MouseButtonPress, QEvent.Wheel, QEvent.KeyPress):
            self.reset_hide_timer()
        return super().eventFilter(obj, event)

    def set_albums(self, albums: list[dict], active_album_id: str = "") -> None:
        """Update album combo and active list."""
        self._albums = list(albums or [])
        if active_album_id:
            self._active_album_id = active_album_id
        elif self._albums and not self._active_album_id:
            self._active_album_id = self._albums[0].get("id") or "default"
        self.album_combo.blockSignals(True)
        self.album_combo.clear()
        active_index = 0
        for index, album in enumerate(self._albums):
            album_id = album.get("id") or ""
            self.album_combo.addItem(album.get("name") or "未命名专辑", album_id)
            if album_id == self._active_album_id:
                active_index = index
        self.album_combo.setCurrentIndex(active_index if self._albums else -1)
        self.album_combo.setToolTip(
            "点击切换播放专辑" if len(self._albums) > 1 else "当前播放专辑"
        )
        self.album_combo.blockSignals(False)
        if self._albums:
            self._active_album_id = self.album_combo.currentData() or self._active_album_id
        self._apply_active_album()

    def active_album_id(self) -> str:
        """Return the active album id."""
        return str(self.album_combo.currentData() or self._active_album_id or "default")

    def _active_album(self) -> dict:
        album_id = self.active_album_id()
        for album in self._albums:
            if album.get("id") == album_id:
                return album
        return self._albums[0] if self._albums else {}

    def _apply_active_album(self) -> None:
        album = self._active_album()
        self._active_album_id = album.get("id") or self._active_album_id
        self._items = list(album.get("items") or [])
        self.item_list.clear()
        self.album_delete_button.setEnabled(bool(self._active_album_id and self._active_album_id != "default"))
        for index, item in enumerate(self._items, start=1):
            type_label = resource_type_label(item.get("type") or item.get("path") or "")
            status = item.get("status_text") or ""
            text = f"{index:02d}. [{type_label}] {item.get('name') or os.path.basename(item.get('path') or '')}"
            if status and status != "有效":
                text += f"  [{status}]"
            list_item = QListWidgetItem(text)
            list_item.setToolTip(item.get("path") or "")
            list_item.setData(Qt.UserRole, item)
            if item.get("status") not in ("", "ok", None):
                list_item.setForeground(QColor("#9a9a9a"))
            self.item_list.addItem(list_item)
        settings = album.get("settings") or {}
        suffix = "自动连播" if settings.get("auto_play_next", True) else "手动播放"
        self.hint_label.setText(f"{len(self._items)} 个媒体 · {suffix}")

        self._update_item_action_state()

    def _on_album_combo_changed(self, _index: int) -> None:
        self._active_album_id = self.active_album_id()
        self._apply_active_album()
        self.album_changed.emit(self._active_album_id)

    def _emit_edit_album(self) -> None:
        album_id = self.active_album_id()
        if album_id:
            self.edit_album_requested.emit(album_id)

    def _emit_refresh_album(self) -> None:
        album_id = self.active_album_id()
        if album_id:
            self.refresh_album_requested.emit(album_id)

    def _emit_delete_album(self) -> None:
        album_id = self.active_album_id()
        if not album_id or album_id == "default":
            message_dialogs.information(self, "播放列表", "默认专辑不能删除。")
            return
        self.delete_album_requested.emit(album_id)

    def selected_item_ids(self) -> list[str]:
        ids: list[str] = []
        for list_item in self.item_list.selectedItems():
            media = list_item.data(Qt.UserRole) or {}
            item_id = str(media.get("id") or "")
            if item_id:
                ids.append(item_id)
        return ids

    def set_selected_item_ids(self, item_ids: list[str]) -> None:
        wanted = {str(item_id or "") for item_id in item_ids if str(item_id or "")}
        self.item_list.clearSelection()
        if not wanted:
            self._update_item_action_state()
            return
        first_selected_row = -1
        for row in range(self.item_list.count()):
            list_item = self.item_list.item(row)
            media = list_item.data(Qt.UserRole) or {}
            if str(media.get("id") or "") in wanted:
                list_item.setSelected(True)
                if first_selected_row < 0:
                    first_selected_row = row
        if first_selected_row >= 0:
            self.item_list.scrollToItem(self.item_list.item(first_selected_row))
        self._update_item_action_state()

    def _update_item_action_state(self) -> None:
        has_selection = bool(self.item_list.selectedItems())
        for button in (
            self.delete_button,
            self.move_top_button,
            self.move_up_button,
            self.move_down_button,
            self.move_bottom_button,
        ):
            button.setEnabled(has_selection)

    def _emit_add_items(self) -> None:
        album_id = self.active_album_id()
        if album_id:
            self.add_items_requested.emit(album_id)

    def _emit_remove_items(self) -> None:
        item_ids = self.selected_item_ids()
        if not item_ids:
            message_dialogs.information(self, "播放列表", "请先选择要移除的条目。")
            return
        self.remove_items_requested.emit(self.active_album_id(), item_ids)

    def _emit_move_items(self, action: str) -> None:
        item_ids = self.selected_item_ids()
        if not item_ids:
            message_dialogs.information(self, "播放列表", "请先选择要移动的条目。")
            return
        self.move_items_requested.emit(self.active_album_id(), item_ids, action)

    def _emit_memory_play(self) -> None:
        album_id = self.active_album_id()
        if album_id:
            self.memory_play_requested.emit(album_id)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        media = item.data(Qt.UserRole)
        if not media:
            return
        self.item_selected.emit(
            self.active_album_id(),
            str(media.get("id") or ""),
            str(media.get("path") or ""),
        )
        self.hide_with_animation()
