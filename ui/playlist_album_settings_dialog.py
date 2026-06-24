import os

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ui.dialog_style import apply_light_dialog_style


class PlaylistAlbumSettingsDialog(QDialog):
    """Dialog for creating or editing a local playback album."""

    def __init__(self, parent=None, album: dict | None = None, create_mode: bool = False):
        super().__init__(parent)
        self.setWindowTitle("专辑设置")
        self.album = dict(album or {})
        self.create_mode = bool(create_mode)
        self.setMinimumWidth(460)
        apply_light_dialog_style(self)

        root = QVBoxLayout(self)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.name_input = QLineEdit()
        self.dir_input = QLineEdit()
        self.browse_button = QPushButton("...")
        self.browse_button.setObjectName("secondaryButton")
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.dir_input, 1)
        dir_row.addWidget(self.browse_button)

        self.recursive_check = QCheckBox("包含子文件夹")
        self.auto_play_check = QCheckBox("自动连播")
        self.remember_playback_check = QCheckBox("播放记忆")
        self.skip_intro_check = QCheckBox("跳过片头")
        self.intro_spin = QSpinBox()
        self.intro_spin.setRange(0, 3600)
        self.intro_spin.setSuffix(" 秒")
        self.skip_outro_check = QCheckBox("跳过片尾")
        self.outro_spin = QSpinBox()
        self.outro_spin.setRange(0, 3600)
        self.outro_spin.setSuffix(" 秒")

        form.addRow("专辑名称", self.name_input)
        form.addRow("来源文件夹", dir_row)
        form.addRow("", self.recursive_check)
        form.addRow("", self.auto_play_check)
        form.addRow("", self.remember_playback_check)
        form.addRow("", self.skip_intro_check)
        form.addRow("片头时长", self.intro_spin)
        form.addRow("", self.skip_outro_check)
        form.addRow("片尾时长", self.outro_spin)
        root.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.browse_button.clicked.connect(self._browse_directory)
        self._load_values()

    def _load_values(self) -> None:
        settings = self.album.get("settings") or {}
        self.name_input.setText(self.album.get("name") or "")
        self.dir_input.setText(self.album.get("source_dir") or "")
        self.recursive_check.setChecked(bool(self.album.get("recursive")))
        self.auto_play_check.setChecked(bool(settings.get("auto_play_next", True)))
        self.remember_playback_check.setChecked(bool(settings.get("remember_playback")))
        self.skip_intro_check.setChecked(bool(settings.get("skip_intro")))
        self.intro_spin.setValue(max(0, int(settings.get("intro_seconds") or 0)))
        self.skip_outro_check.setChecked(bool(settings.get("skip_outro")))
        self.outro_spin.setValue(max(0, int(settings.get("outro_seconds") or 0)))

    def _browse_directory(self) -> None:
        start = self.dir_input.text().strip()
        if not start or not os.path.isdir(start):
            start = os.getcwd()
        selected = QFileDialog.getExistingDirectory(self, "选择专辑文件夹", start)
        if selected:
            self.dir_input.setText(selected)
            if not self.name_input.text().strip():
                self.name_input.setText(os.path.basename(os.path.normpath(selected)))

    def values(self) -> dict:
        """Return dialog values."""
        return {
            "name": self.name_input.text().strip(),
            "source_dir": self.dir_input.text().strip(),
            "recursive": self.recursive_check.isChecked(),
            "settings": {
                "auto_play_next": self.auto_play_check.isChecked(),
                "remember_playback": self.remember_playback_check.isChecked(),
                "skip_intro": self.skip_intro_check.isChecked(),
                "intro_seconds": int(self.intro_spin.value()),
                "skip_outro": self.skip_outro_check.isChecked(),
                "outro_seconds": int(self.outro_spin.value()),
            },
        }
