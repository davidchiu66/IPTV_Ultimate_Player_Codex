from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


class ChannelTableModel(QAbstractTableModel):
    HEADERS = ["名称", "分类", "播放地址", "解密", "代理"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._items)

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self.HEADERS):
            return self.HEADERS[section]
        return str(section + 1)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        item = self._items[index.row()]
        column = index.column()

        if role == Qt.DisplayRole:
            if column == 0:
                return item.get("Name") or "未命名频道"
            if column == 1:
                return item.get("Category") or ""
            if column == 2:
                return item.get("Manifest") or ""
            if column == 3:
                drm_type = item.get("DrmType")
                if drm_type:
                    return drm_type
                keys_list = item.get("Keys") or []
                return "clearkey" if isinstance(keys_list, list) and keys_list else "none"
            if column == 4:
                return "开" if item.get("UseLocalProxy", False) else "关"

        if role == Qt.TextAlignmentRole and column in (3, 4):
            return int(Qt.AlignCenter)

        if role == Qt.ToolTipRole:
            if column == 2:
                return item.get("Manifest") or ""

        return None

    def set_items(self, items):
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def get_item(self, row):
        if 0 <= row < len(self._items):
            return self._items[row]
        return None
