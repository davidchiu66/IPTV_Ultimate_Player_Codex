from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTableView,
    QVBoxLayout,
)


class ChannelTablePanel(QFrame):
    query_changed = Signal(str)
    channel_selected = Signal(int)
    channel_activated = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("channelTablePanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("频道列表")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索名称、分类、节目单 ID、播放地址...")
        top_row.addWidget(self.search_input, 1)
        layout.addLayout(top_row)

        self.table = QTableView()
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        layout.addWidget(self.table, 1)

        self.search_input.textChanged.connect(self.query_changed.emit)
        self.table.doubleClicked.connect(self._emit_activated_row)

    def bind_selection_model(self):
        selection_model = self.table.selectionModel()
        if selection_model:
            try:
                selection_model.selectionChanged.disconnect(self._emit_selected_row)
            except (RuntimeError, TypeError):
                pass
            selection_model.selectionChanged.connect(self._emit_selected_row)

    def _emit_selected_row(self, *_args):
        index = self.table.currentIndex()
        if index.isValid():
            self.channel_selected.emit(index.row())

    def _emit_activated_row(self, index):
        if index.isValid():
            self.channel_activated.emit(index.row())
