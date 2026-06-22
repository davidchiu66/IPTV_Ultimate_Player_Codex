from PySide6.QtCore import QRegularExpression, QSortFilterProxyModel


class ChannelFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._query = ""

    def set_query(self, query):
        self._query = (query or "").strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        if not self._query:
            return True

        model = self.sourceModel()
        item = model.get_item(source_row) if model else None
        if not item:
            return False

        searchable = " ".join(
            [
                str(item.get("Name") or ""),
                str(item.get("Category") or ""),
                str(item.get("Manifest") or ""),
                str(item.get("TvgId") or ""),
                str(item.get("TvgName") or ""),
            ]
        ).lower()
        return self._query in searchable
