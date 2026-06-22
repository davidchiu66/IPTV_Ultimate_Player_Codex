from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
)

from ui.dialog_style import apply_light_dialog_style


class ChannelEditorDialog(QDialog):
    def __init__(self, channel, default_category="", parent=None):
        super().__init__(parent)
        self._source = dict(channel or {})
        title = "编辑频道" if self._source else "添加频道"
        self.setWindowTitle(f"{title} - IPTV 播放器")
        self.resize(560, 620)
        apply_light_dialog_style(self)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.name_input = QLineEdit(self._source.get("Name") or "")
        self.category_input = QLineEdit(self._source.get("Category") or default_category or "")
        self.manifest_input = QLineEdit(self._source.get("Manifest") or "")
        self.logo_input = QLineEdit(self._source.get("LogoUrl") or "")
        self.tvg_id_input = QLineEdit(self._source.get("TvgId") or "")
        self.tvg_name_input = QLineEdit(self._source.get("TvgName") or "")

        self.drm_input = QComboBox()
        self.drm_input.addItems(["none", "clearkey", "widevine", "playready"])
        current_drm = self._source.get("DrmType") or "none"
        self.drm_input.setCurrentText(current_drm)

        self.license_input = QLineEdit(self._source.get("LicenseUrl") or "")
        self.proxy_input = QCheckBox("启用本地代理")
        self.proxy_input.setChecked(self._source.get("UseLocalProxy", False))
        self.ua_input = QLineEdit(self._source.get("UserAgent") or "")
        self.referer_input = QLineEdit(self._source.get("Referer") or "")

        self.keys_input = QTextEdit()
        keys_list = self._source.get("Keys") or []
        if isinstance(keys_list, list):
            self.keys_input.setPlainText("\n".join(str(k) for k in keys_list if k))

        form.addRow("名称", self.name_input)
        form.addRow("分类", self.category_input)
        form.addRow("播放地址", self.manifest_input)
        form.addRow("台标地址", self.logo_input)
        form.addRow("节目单 ID", self.tvg_id_input)
        form.addRow("节目单名称", self.tvg_name_input)
        form.addRow("解密类型", self.drm_input)
        form.addRow("许可证地址", self.license_input)
        form.addRow("代理", self.proxy_input)
        form.addRow("User-Agent", self.ua_input)
        form.addRow("Referer", self.referer_input)
        form.addRow("密钥", self.keys_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_channel_data(self):
        keys_text = self.keys_input.toPlainText().strip()
        keys_list = [line.strip() for line in keys_text.splitlines() if ":" in line]

        return {
            "Name": self.name_input.text().strip(),
            "Category": self.category_input.text().strip(),
            "Manifest": self.manifest_input.text().strip(),
            "LogoUrl": self.logo_input.text().strip(),
            "TvgId": self.tvg_id_input.text().strip(),
            "TvgName": self.tvg_name_input.text().strip(),
            "DrmType": self.drm_input.currentText().strip(),
            "LicenseUrl": self.license_input.text().strip(),
            "Keys": keys_list,
            "UseLocalProxy": self.proxy_input.isChecked(),
            "UserAgent": self.ua_input.text().strip(),
            "Referer": self.referer_input.text().strip(),
        }
