from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ui.base_overlay import BaseOverlay
from ui.theme import overlay_qss
from utils.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, tr


class SettingsOverlay(BaseOverlay):
    """Right-side application settings panel."""

    settings_saved = Signal(str, int, int, bool, str, str, str, str, bool, bool)

    def __init__(self, parent=None):
        super().__init__(parent, side="right", width=380)
        self.setObjectName("settingsOverlay")
        self.setStyleSheet(overlay_qss("settingsOverlay"))

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        title = QLabel("应用设置")
        title.setObjectName("panelTitle")
        root.addWidget(title)

        hint = QLabel("代理优先级：系统代理 > 用户代理 > 频道代理 > 直连")
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        root.addWidget(hint)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)

        self.system_proxy_label = QLabel("-")
        self.system_proxy_label.setWordWrap(True)
        self.effective_proxy_label = QLabel("-")
        self.effective_proxy_label.setWordWrap(True)

        self.user_proxy_input = QLineEdit()
        self.user_proxy_input.setPlaceholderText("例如 http://127.0.0.1:7890，留空则不用用户代理")

        self.probe_timeout_spin = QSpinBox()
        self.probe_timeout_spin.setRange(3, 120)
        self.probe_timeout_spin.setSuffix(" 秒")

        self.browser_port_spin = QSpinBox()
        self.browser_port_spin.setRange(1024, 65535)

        self.local_playback_mode_combo = QComboBox()
        self.local_playback_mode_combo.addItem("4K 流畅", "smooth")
        self.local_playback_mode_combo.addItem("高画质", "quality")
        self.local_playback_mode_combo.addItem("极致画质", "extreme")

        self.live_playback_mode_combo = QComboBox()
        self.live_playback_mode_combo.addItem("流畅优先", "smooth")
        self.live_playback_mode_combo.addItem("画质优先", "quality")

        self.language_combo = QComboBox()
        for language in SUPPORTED_LANGUAGES:
            self.language_combo.addItem(tr(f"app.language.{language}", language), language)

        self.diagnostics_enabled_check = QCheckBox("启用诊断日志")
        self.diagnostics_level_combo = QComboBox()
        self.diagnostics_level_combo.addItem("仅错误", "error")
        self.diagnostics_level_combo.addItem("信息", "info")
        self.diagnostics_level_combo.addItem("调试", "debug")
        self.clock_weekday_check = QCheckBox("悬浮时钟显示星期")
        self.clock_weekday_check.setChecked(True)
        self.safe_mode_check = QCheckBox("兼容/安全启动模式（重启生效）")

        form.addRow("系统代理", self.system_proxy_label)
        form.addRow("用户代理", self.user_proxy_input)
        form.addRow("当前生效", self.effective_proxy_label)
        form.addRow("探测超时", self.probe_timeout_spin)
        form.addRow("浏览器端口", self.browser_port_spin)
        form.addRow("本地渲染模式", self.local_playback_mode_combo)
        form.addRow("直播渲染模式", self.live_playback_mode_combo)
        form.addRow("界面语言", self.language_combo)
        form.addRow("悬浮时钟", self.clock_weekday_check)
        form.addRow("启动兼容", self.safe_mode_check)
        form.addRow("诊断日志", self.diagnostics_enabled_check)
        form.addRow("日志级别", self.diagnostics_level_combo)
        root.addLayout(form)
        root.addStretch(1)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.save_button = QPushButton("保存")
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("cancelButton")
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.save_button)
        root.addLayout(actions)

        self.save_button.clicked.connect(self._on_save_clicked)
        self.cancel_button.clicked.connect(self.hide_with_animation)

    def set_values(
        self,
        system_proxy,
        user_proxy,
        effective_proxy,
        source,
        timeout_ms,
        browser_port,
        diagnostics_enabled=False,
        diagnostics_level="error",
        local_playback_mode="smooth",
        live_playback_mode="smooth",
        language=DEFAULT_LANGUAGE,
        clock_show_weekday=True,
        safe_mode=False,
    ):
        self.system_proxy_label.setText(system_proxy or "无")
        source_text = {
            "system": "系统代理",
            "user": "用户代理",
            "channel": "频道代理",
            "direct": "直连",
        }.get(source or "", source or "直连")
        self.effective_proxy_label.setText(f"{effective_proxy or '直连'}（{source_text}）")
        self.user_proxy_input.setText(user_proxy or "")
        self.probe_timeout_spin.setValue(max(3, min(120, int(timeout_ms or 30000) // 1000)))
        self.browser_port_spin.setValue(int(browser_port or 8000))
        local_index = self.local_playback_mode_combo.findData(local_playback_mode or "smooth")
        self.local_playback_mode_combo.setCurrentIndex(local_index if local_index >= 0 else 0)
        live_index = self.live_playback_mode_combo.findData(live_playback_mode or "smooth")
        self.live_playback_mode_combo.setCurrentIndex(live_index if live_index >= 0 else 0)
        language_index = self.language_combo.findData(language or DEFAULT_LANGUAGE)
        self.language_combo.setCurrentIndex(language_index if language_index >= 0 else 0)
        self.diagnostics_enabled_check.setChecked(bool(diagnostics_enabled))
        index = self.diagnostics_level_combo.findData(diagnostics_level or "error")
        self.diagnostics_level_combo.setCurrentIndex(index if index >= 0 else 0)
        self.clock_weekday_check.setChecked(bool(clock_show_weekday))
        self.safe_mode_check.setChecked(bool(safe_mode))

    def _on_save_clicked(self):
        timeout_ms = int(self.probe_timeout_spin.value()) * 1000
        self.settings_saved.emit(
            self.user_proxy_input.text().strip(),
            timeout_ms,
            int(self.browser_port_spin.value()),
            self.diagnostics_enabled_check.isChecked(),
            self.diagnostics_level_combo.currentData() or "error",
            self.local_playback_mode_combo.currentData() or "smooth",
            self.live_playback_mode_combo.currentData() or "smooth",
            self.language_combo.currentData() or DEFAULT_LANGUAGE,
            self.clock_weekday_check.isChecked(),
            self.safe_mode_check.isChecked(),
        )
        self.hide_with_animation()
