import re

from PySide6.QtCore import Signal, Qt, QSize, QRect, QObject, QTimer, QUrl, QEvent
from PySide6.QtGui import QPixmap, QIcon, QPainter, QColor, QBrush
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QWidget, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QStyle, QStyledItemDelegate, QMenu,
    QStyleOptionViewItem,
)
from ui.base_overlay import BaseOverlay
from ui.theme import overlay_qss


FAVORITE_ROLE = Qt.UserRole + 10
STAR_AREA_WIDTH = 34


class FavoriteStarDelegate(QStyledItemDelegate):
    """Draw channel row content with a right-aligned favorite star."""

    def paint(self, painter, option, index):
        painter.save()
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(105, 178, 255, 115))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(option.rect, QColor(120, 180, 255, 42))
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


class GroupRowDelegate(QStyledItemDelegate):
    """分组行：名称(省略号) + 右对齐数量，保证数量始终完整显示。"""

    def paint(self, painter, option, index):
        painter.save()
        rect = option.rect
        if option.state & QStyle.State_Selected:
            painter.fillRect(rect, QColor(105, 178, 255, 115))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(rect, QColor(120, 180, 255, 42))
        # 底部分隔线
        painter.setPen(QColor(255, 255, 255, 22))
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        fm = option.fontMetrics
        pad = 12
        count = str(index.data(Qt.UserRole + 1) or "")
        cw = fm.horizontalAdvance(count)
        crect = QRect(rect.right() - pad - cw, rect.top(), cw, rect.height())
        painter.setPen(QColor("#9fc9ff"))
        painter.drawText(crect, Qt.AlignVCenter | Qt.AlignRight, count)

        name = str(index.data(Qt.DisplayRole) or "")
        nleft = rect.left() + pad
        navail = max(0, crect.left() - 8 - nleft)
        elided = fm.elidedText(name, Qt.ElideRight, navail)
        painter.setPen(QColor("#edf4ff"))
        painter.drawText(QRect(nleft, rect.top(), navail, rect.height()),
                         Qt.AlignVCenter | Qt.AlignLeft, elided)
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(0, 40)


class LogoLoader(QObject):
    """异步加载频道台标（懒加载 + 内存缓存 + 失败回退默认）。"""
    ready = Signal(str, QIcon)

    def __init__(self, size=36, parent=None):
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._size = size
        self._inflight = {}   # reply -> url
        self._requested = set()

    def request(self, url):
        if not url or url in self._requested:
            return
        if not (url.startswith("http://") or url.startswith("https://")):
            return
        self._requested.add(url)
        req = QNetworkRequest(QUrl(url))
        try:
            req.setAttribute(QNetworkRequest.RedirectPolicyAttribute,
                             QNetworkRequest.NoLessSafeRedirectPolicy)
        except Exception:
            pass
        reply = self._nam.get(req)
        self._inflight[reply] = url
        reply.finished.connect(lambda r=reply: self._on_finished(r))

    def _on_finished(self, reply):
        url = self._inflight.pop(reply, None)
        try:
            err = reply.error()
        except Exception:
            err = None
        data = reply.readAll() if err == QNetworkReply.NoError else None
        reply.deleteLater()
        if not url or data is None:
            return  # 失败：保留默认台标
        pm = QPixmap()
        if pm.loadFromData(data) and not pm.isNull():
            pm = pm.scaled(self._size, self._size, Qt.KeepAspectRatio,
                           Qt.SmoothTransformation)
            self.ready.emit(url, QIcon(pm))


_CHANNEL_LIST_QSS = overlay_qss("channelListOverlay") + """
#groupPane {
    background: rgba(12, 18, 25, 120);
    border-top-left-radius: 18px;
    border-bottom-left-radius: 18px;
}
#channelPane {
    background: rgba(10, 15, 22, 80);
    border-top-right-radius: 18px;
    border-bottom-right-radius: 18px;
}
QLabel#paneTitle {
    color: #f3f7ff;
    font-size: 19px;
    font-weight: 700;
    background: transparent;
}
QLabel#paneSubtitle {
    color: #9fc9ff;
    font-size: 12px;
    background: transparent;
}
QLineEdit#chSearch {
    background: rgba(18, 22, 29, 215);
    color: #f2f6ff;
    border: 1px solid rgba(120, 180, 255, 105);
    border-radius: 8px;
    padding: 7px 9px;
    font-size: 13px;
}
QListWidget {
    background: rgba(13, 18, 26, 150);
    border: 1px solid rgba(120, 180, 255, 65);
    border-radius: 8px;
    outline: 0;
}
QListWidget#channelList::item {
    color: #edf4ff;
    border-bottom: 1px solid rgba(255, 255, 255, 16);
    padding: 8px 6px;
}
QListWidget#channelList::item:selected {
    background: rgba(105, 178, 255, 115);
    color: #ffffff;
}
QListWidget#channelList::item:hover {
    background: rgba(120, 180, 255, 42);
}
"""

ALL_CHANNELS = "__all__"


class ChannelListOverlay(BaseOverlay):
    """频道列表覆盖层：左侧分组 + 右侧频道（玻璃风）。"""
    channel_selected = Signal(dict)
    channel_favorite_toggle_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent, side='left', width=560)
        self.setObjectName("channelListOverlay")
        self.setStyleSheet(_CHANNEL_LIST_QSS)

        self._channels = []
        self._filtered_channels = []
        self._groups = []           # [(category, count)]
        self._selected_group = ALL_CHANNELS
        self._source_name = "频道"
        self._placeholder_icon = self._make_placeholder_icon()
        self._favorite_fingerprints = set()

        # 台标懒加载
        self._logo_cache = {}       # url -> QIcon
        self._logo_loader = LogoLoader(36, self)
        self._logo_loader.ready.connect(self._on_logo_ready)
        self._logo_scroll_timer = QTimer(self)
        self._logo_scroll_timer.setSingleShot(True)
        self._logo_scroll_timer.setInterval(120)
        self._logo_scroll_timer.timeout.connect(self._ensure_visible_logos)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ===== 左：分组面板 =====
        group_pane = QWidget()
        group_pane.setObjectName("groupPane")
        group_pane.setFixedWidth(210)
        gl = QVBoxLayout(group_pane)
        gl.setContentsMargins(16, 16, 10, 16)
        gl.setSpacing(2)

        self.group_title = QLabel("频道")
        self.group_title.setObjectName("paneTitle")
        self.group_subtitle = QLabel("0 个分组")
        self.group_subtitle.setObjectName("paneSubtitle")
        gl.addWidget(self.group_title)
        gl.addWidget(self.group_subtitle)
        gl.addSpacing(8)

        self.group_list = QListWidget()
        self.group_list.setObjectName("groupList")
        self.group_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.group_list.setItemDelegate(GroupRowDelegate(self.group_list))
        self.group_list.currentRowChanged.connect(self._on_group_changed)
        gl.addWidget(self.group_list, 1)
        root.addWidget(group_pane)

        # ===== 右：频道面板 =====
        channel_pane = QWidget()
        channel_pane.setObjectName("channelPane")
        cl = QVBoxLayout(channel_pane)
        cl.setContentsMargins(16, 16, 14, 16)
        cl.setSpacing(8)

        self.channel_title = QLabel("全部频道")
        self.channel_title.setObjectName("paneTitle")
        self.channel_subtitle = QLabel("0 个频道")
        self.channel_subtitle.setObjectName("paneSubtitle")
        cl.addWidget(self.channel_title)
        cl.addWidget(self.channel_subtitle)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("chSearch")
        self.search_input.setPlaceholderText("搜索频道名称...")
        self.search_input.textChanged.connect(lambda _t: self._apply_filter())
        cl.addWidget(self.search_input)

        self.channel_list = QListWidget()
        self.channel_list.setObjectName("channelList")
        self.channel_list.setIconSize(QSize(36, 36))
        self.channel_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.channel_list.setWordWrap(False)
        self.channel_list.setTextElideMode(Qt.ElideRight)
        self.channel_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.channel_list.setUniformItemSizes(True)
        self.channel_list.setItemDelegate(FavoriteStarDelegate(self.channel_list))
        self.channel_list.itemClicked.connect(self._on_channel_clicked)
        self.channel_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.channel_list.customContextMenuRequested.connect(self._show_channel_context_menu)
        self.channel_list.viewport().installEventFilter(self)
        self.channel_list.verticalScrollBar().valueChanged.connect(
            lambda _v: self._logo_scroll_timer.start()
        )
        cl.addWidget(self.channel_list, 1)
        root.addWidget(channel_pane, 1)

    def eventFilter(self, watched, event):
        if not hasattr(self, "channel_list"):
            return super().eventFilter(watched, event)
        if watched is self.channel_list.viewport() and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                item = self.channel_list.itemAt(event.position().toPoint())
                if item:
                    rect = self.channel_list.visualItemRect(item)
                    if event.position().toPoint().x() >= rect.right() - STAR_AREA_WIDTH:
                        channel = item.data(Qt.UserRole + 2)
                        if channel:
                            self.channel_favorite_toggle_requested.emit(channel)
                            return True
        return super().eventFilter(watched, event)

    # ---------- 占位 logo 图标 ----------
    def _make_placeholder_icon(self):
        pm = QPixmap(36, 36)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#cfcfd6")))
        p.drawRoundedRect(0, 0, 36, 36, 6, 6)
        p.end()
        return QIcon(pm)

    # ---------- 数据入口 ----------
    def set_channels(self, channels, source_name=None):
        self._channels = list(channels)
        if source_name:
            self._source_name = self._short_name(source_name)
        self._rebuild_groups()

    def set_source_name(self, name):
        if name:
            self._source_name = self._short_name(name)
            self.group_title.setText(self._source_name)

    def set_channel_favorite_fingerprints(self, fingerprints):
        self._favorite_fingerprints = set(fingerprints or [])
        self._apply_filter()

    @staticmethod
    def _short_name(name):
        """来源名取简洁版：在下划线/中划线/空格/点等分隔符处截断取首段。"""
        if not name:
            return name
        first = re.split(r'[_\-\s.]+', name.strip(), 1)[0]
        return first or name

    def _rebuild_groups(self):
        # 按首次出现顺序统计分组
        order = {}
        for ch in self._channels:
            cat = (ch.get("Category") or self._source_name or "默认分组").strip() or "默认分组"
            order[cat] = order.get(cat, 0) + 1
        self._groups = list(order.items())

        self.group_title.setText(self._source_name or "频道")
        self.group_subtitle.setText(f"{len(self._groups)} 个分组")

        # 构建分组列表：全部频道 + 各分组
        self.group_list.blockSignals(True)
        self.group_list.clear()
        self._add_group_row("全部频道", len(self._channels), ALL_CHANNELS)
        for cat, cnt in self._groups:
            self._add_group_row(cat, cnt, cat)
        self.group_list.blockSignals(False)

        # 默认选中“全部频道”
        self._selected_group = ALL_CHANNELS
        self.group_list.setCurrentRow(0)
        self._apply_filter()

    def _add_group_row(self, name, count, key):
        item = QListWidgetItem(name)
        item.setData(Qt.UserRole, key)            # 分组键
        item.setData(Qt.UserRole + 1, count)      # 数量（委托右对齐绘制）
        self.group_list.addItem(item)

    # ---------- 分组切换 / 过滤 ----------
    def _on_group_changed(self, row):
        if row < 0:
            return
        item = self.group_list.item(row)
        if item is None:
            return
        self._selected_group = item.data(Qt.UserRole) or ALL_CHANNELS
        self._apply_filter()

    def _apply_filter(self):
        keyword = self.search_input.text().strip().lower()
        result = []
        for ch in self._channels:
            if self._selected_group != ALL_CHANNELS:
                cat = (ch.get("Category") or self._source_name or "默认分组").strip() or "默认分组"
                if cat != self._selected_group:
                    continue
            if keyword and keyword not in (ch.get("Name", "") or "").lower():
                continue
            result.append(ch)
        self._filtered_channels = result

        # 右侧标题：当前分组名 + 数量
        title = "全部频道" if self._selected_group == ALL_CHANNELS else self._selected_group
        self.channel_title.setText(title)
        self.channel_subtitle.setText(f"{len(result)} 个频道")

        self.channel_list.clear()
        for ch in result:
            url = (ch.get("LogoUrl") or "").strip()
            icon = self._logo_cache.get(url, self._placeholder_icon)
            item = QListWidgetItem(icon, ch.get('Name', '未命名'))
            item.setData(Qt.UserRole, url)  # 台标 URL，用于懒加载
            item.setData(Qt.UserRole + 2, ch)
            item.setData(FAVORITE_ROLE, str(ch.get("_FavoriteFingerprint") or "") in self._favorite_fingerprints)
            self.channel_list.addItem(item)
        # 列表变化后，加载当前可见项的台标
        QTimer.singleShot(0, self._ensure_visible_logos)

    def showEvent(self, event):
        super().showEvent(event)
        # 显示后几何就绪，加载当前可见项台标
        QTimer.singleShot(50, self._ensure_visible_logos)

    # ---------- 台标懒加载 ----------
    def _ensure_visible_logos(self):
        count = self.channel_list.count()
        if count == 0:
            return
        vp = self.channel_list.viewport().rect()
        for row in range(count):
            item = self.channel_list.item(row)
            r = self.channel_list.visualItemRect(item)
            if r.bottom() < vp.top():
                continue
            if r.top() > vp.bottom():
                break  # 已超出可见区，下面的更不可见
            url = item.data(Qt.UserRole)
            if url and url not in self._logo_cache:
                self._logo_loader.request(url)

    def _on_logo_ready(self, url, icon):
        self._logo_cache[url] = icon
        for row in range(self.channel_list.count()):
            item = self.channel_list.item(row)
            if item.data(Qt.UserRole) == url:
                item.setIcon(icon)

    def _on_channel_clicked(self, item):
        channel = item.data(Qt.UserRole + 2)
        row = self.channel_list.row(item)
        if not channel and 0 <= row < len(self._filtered_channels):
            channel = self._filtered_channels[row]
        if channel:
            self.channel_selected.emit(channel)
            self.hide_with_animation()

    def _show_channel_context_menu(self, pos):
        item = self.channel_list.itemAt(pos)
        if not item:
            return
        channel = item.data(Qt.UserRole + 2)
        if not channel:
            return
        is_favorite = str(channel.get("_FavoriteFingerprint") or "") in self._favorite_fingerprints
        menu = QMenu(self)
        favorite_action = menu.addAction("取消收藏" if is_favorite else "添加到收藏")
        play_action = menu.addAction("播放")
        action = menu.exec(self.channel_list.mapToGlobal(pos))
        if action == favorite_action:
            self.channel_favorite_toggle_requested.emit(channel)
        elif action == play_action:
            self.channel_selected.emit(channel)
            self.hide_with_animation()
