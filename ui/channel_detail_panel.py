from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class ChannelDetailPanel(QFrame):
    add_requested = Signal()
    edit_requested = Signal()
    delete_requested = Signal()
    save_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("channelDetailPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel("频道详情")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self.summary_card = QFrame()
        self.summary_card.setObjectName("summaryCard")
        summary_layout = QVBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(14, 14, 14, 14)
        summary_layout.setSpacing(8)

        self.hero_name = QLabel("未选择频道")
        self.hero_name.setObjectName("heroTitle")
        summary_layout.addWidget(self.hero_name)

        self.hero_category = QLabel("请选择一个播放列表条目，以查看它的流媒体详细信息。")
        self.hero_category.setObjectName("sectionLabel")
        self.hero_category.setWordWrap(True)
        summary_layout.addWidget(self.hero_category)

        badge_grid = QGridLayout()
        badge_grid.setHorizontalSpacing(8)
        badge_grid.setVerticalSpacing(8)

        self.drm_badge = QLabel("解密：-")
        self.proxy_badge = QLabel("代理：-")
        self.tvg_badge = QLabel("节目单：-")
        self.keys_badge = QLabel("密钥：0")
        for badge in [self.drm_badge, self.proxy_badge, self.tvg_badge, self.keys_badge]:
            badge.setObjectName("infoBadge")

        badge_grid.addWidget(self.drm_badge, 0, 0)
        badge_grid.addWidget(self.proxy_badge, 0, 1)
        badge_grid.addWidget(self.tvg_badge, 1, 0)
        badge_grid.addWidget(self.keys_badge, 1, 1)
        summary_layout.addLayout(badge_grid)
        layout.addWidget(self.summary_card)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.name_value = QLabel("-")
        self.category_value = QLabel("-")
        self.drm_value = QLabel("-")
        self.proxy_value = QLabel("-")
        self.tvg_value = QLabel("-")
        self.ua_value = QLabel("-")

        for label in [
            self.name_value,
            self.category_value,
            self.drm_value,
            self.proxy_value,
            self.tvg_value,
            self.ua_value,
        ]:
            label.setWordWrap(True)
            label.setObjectName("infoValue")

        form.addRow("名称", self.name_value)
        form.addRow("分类", self.category_value)
        form.addRow("解密", self.drm_value)
        form.addRow("代理", self.proxy_value)
        form.addRow("节目单", self.tvg_value)
        form.addRow("User-Agent", self.ua_value)
        layout.addLayout(form)

        button_row = QHBoxLayout()
        self.add_button = QPushButton("新增")
        self.edit_button = QPushButton("编辑")
        self.delete_button = QPushButton("删除")
        self.save_button = QPushButton("保存")
        button_row.addWidget(self.add_button)
        button_row.addWidget(self.edit_button)
        button_row.addWidget(self.delete_button)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

        manifest_label = QLabel("播放地址 / 流地址")
        manifest_label.setObjectName("sectionLabel")
        layout.addWidget(manifest_label)

        self.manifest_text = QTextEdit()
        self.manifest_text.setReadOnly(True)
        self.manifest_text.setPlaceholderText("播放地址 / URL")
        self.manifest_text.setMinimumHeight(130)
        self.manifest_text.setMaximumHeight(180)
        layout.addWidget(self.manifest_text)
        layout.addStretch(1)

        self.add_button.clicked.connect(self.add_requested.emit)
        self.edit_button.clicked.connect(self.edit_requested.emit)
        self.delete_button.clicked.connect(self.delete_requested.emit)
        self.save_button.clicked.connect(self.save_requested.emit)

    def set_channel(self, channel):
        if not channel:
            self.hero_name.setText("未选择频道")
            self.hero_category.setText("请选择一个播放列表条目，以查看它的流媒体详细信息。")
            self.name_value.setText("-")
            self.category_value.setText("-")
            self.drm_value.setText("-")
            self.proxy_value.setText("-")
            self.tvg_value.setText("-")
            self.ua_value.setText("-")
            self.drm_badge.setText("解密：-")
            self.proxy_badge.setText("代理：-")
            self.tvg_badge.setText("节目单：-")
            self.keys_badge.setText("密钥：0")
            self.manifest_text.clear()
            return

        keys_list = channel.get("Keys") or []
        keys_count = len(keys_list) if isinstance(keys_list, list) else 0
        drm_type = channel.get("DrmType") or ("clearkey" if keys_count else "none")
        tvg_text = channel.get("TvgId") or channel.get("TvgName") or "-"
        proxy_text = "已启用" if channel.get("UseLocalProxy", False) else "未启用"

        self.hero_name.setText(channel.get("Name") or "未命名频道")
        self.hero_category.setText(channel.get("Category") or "未分类流")

        self.name_value.setText(channel.get("Name") or "未命名频道")
        self.category_value.setText(channel.get("Category") or "-")
        self.drm_value.setText(drm_type)
        self.proxy_value.setText(proxy_text)
        self.tvg_value.setText(tvg_text)
        self.ua_value.setText(channel.get("UserAgent") or "-")

        self.drm_badge.setText(f"解密：{drm_type}")
        self.proxy_badge.setText(f"代理：{proxy_text}")
        self.tvg_badge.setText(f"节目单：{tvg_text}")
        self.keys_badge.setText(f"密钥：{keys_count}")
        self.manifest_text.setPlainText(channel.get("Manifest") or "")
