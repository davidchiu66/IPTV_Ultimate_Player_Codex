"""Shared glass-style message dialog helpers."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

from ui.dialog_style import apply_light_dialog_style


def create_message_box(
    parent: QWidget | None,
    title: str,
    *,
    icon: QMessageBox.Icon = QMessageBox.NoIcon,
) -> QMessageBox:
    """Create a QMessageBox with the shared custom glass chrome."""
    dialog = QMessageBox(parent)
    apply_light_dialog_style(dialog)
    dialog.setWindowTitle(title)
    dialog.setIcon(icon)
    return dialog


def information(parent: QWidget | None, title: str, text: str) -> QMessageBox.StandardButton:
    """Show a glass-style information message box."""
    dialog = create_message_box(parent, title, icon=QMessageBox.Information)
    dialog.setText(text)
    dialog.setStandardButtons(QMessageBox.Ok)
    return QMessageBox.StandardButton(dialog.exec())


def warning(parent: QWidget | None, title: str, text: str) -> QMessageBox.StandardButton:
    """Show a glass-style warning message box."""
    dialog = create_message_box(parent, title, icon=QMessageBox.Warning)
    dialog.setText(text)
    dialog.setStandardButtons(QMessageBox.Ok)
    return QMessageBox.StandardButton(dialog.exec())


def critical(parent: QWidget | None, title: str, text: str) -> QMessageBox.StandardButton:
    """Show a glass-style critical message box."""
    dialog = create_message_box(parent, title, icon=QMessageBox.Critical)
    dialog.setText(text)
    dialog.setStandardButtons(QMessageBox.Ok)
    return QMessageBox.StandardButton(dialog.exec())


def question(
    parent: QWidget | None,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButtons = QMessageBox.Yes | QMessageBox.No,
    default_button: QMessageBox.StandardButton = QMessageBox.NoButton,
) -> QMessageBox.StandardButton:
    """Show a glass-style question message box."""
    dialog = create_message_box(parent, title, icon=QMessageBox.Question)
    dialog.setText(text)
    dialog.setStandardButtons(buttons)
    if default_button != QMessageBox.NoButton:
        dialog.setDefaultButton(default_button)
    return QMessageBox.StandardButton(dialog.exec())
