"""Shared glass-style input dialog helpers."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLineEdit, QSpinBox, QLabel, QVBoxLayout, QWidget

from ui.dialog_style import apply_light_dialog_style


def _base_dialog(parent: QWidget | None, title: str, label: str) -> tuple[QDialog, QVBoxLayout]:
    """Create a shared input dialog shell."""
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setMinimumWidth(420)
    apply_light_dialog_style(dialog)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(20, 20, 20, 18)
    layout.setSpacing(12)

    prompt = QLabel(label, dialog)
    prompt.setWordWrap(True)
    prompt.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    layout.addWidget(prompt)
    return dialog, layout


def get_text(
    parent: QWidget | None,
    title: str,
    label: str,
    *,
    text: str = "",
) -> tuple[str, bool]:
    """Show a glass-style text input dialog."""
    dialog, layout = _base_dialog(parent, title, label)
    input_widget = QLineEdit(dialog)
    input_widget.setText(text or "")
    input_widget.selectAll()
    layout.addWidget(input_widget)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dialog)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    accepted = dialog.exec() == QDialog.Accepted
    return input_widget.text(), accepted


def get_int(
    parent: QWidget | None,
    title: str,
    label: str,
    value: int,
    minimum: int,
    maximum: int,
) -> tuple[int, bool]:
    """Show a glass-style integer input dialog."""
    dialog, layout = _base_dialog(parent, title, label)
    input_widget = QSpinBox(dialog)
    input_widget.setRange(int(minimum), int(maximum))
    input_widget.setValue(max(int(minimum), min(int(maximum), int(value))))
    layout.addWidget(input_widget)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dialog)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    accepted = dialog.exec() == QDialog.Accepted
    return int(input_widget.value()), accepted
