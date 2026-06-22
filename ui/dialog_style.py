"""Shared dialog styling helpers."""

from ui.theme import GLASS_DIALOG_QSS, apply_glass_dialog_style


LIGHT_DIALOG_QSS = GLASS_DIALOG_QSS


def apply_light_dialog_style(dialog):
    """Compatibility wrapper for the current glass dialog style."""
    apply_glass_dialog_style(dialog)


def apply_dialog_style(dialog):
    """Apply the shared glass dialog style to new dialogs."""
    apply_glass_dialog_style(dialog)
