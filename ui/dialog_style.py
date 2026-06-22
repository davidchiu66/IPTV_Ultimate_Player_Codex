"""统一的浅色对话框样式（与频道列表 / 频道详情 / 资源库保持一致）。"""

LIGHT_DIALOG_QSS = """
QDialog { background: #f4f4f6; }
QLabel { color: #2a2a2a; font-size: 13px; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {
    background: #ffffff; color: #2a2a2a;
    border: 1px solid #dcdce0; border-radius: 6px; padding: 6px 8px;
    selection-background-color: #dce8f7; selection-color: #14385f;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
    border: 1px solid #3d6fb0;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: #ffffff; color: #2a2a2a; border: 1px solid #dcdce0;
    selection-background-color: #dce8f7; selection-color: #14385f;
}
QCheckBox { color: #2a2a2a; }
QPushButton {
    background: #3d6fb0; color: #ffffff; border: none;
    border-radius: 6px; padding: 8px 16px; font-size: 13px;
}
QPushButton:hover { background: #4a7fc4; }
QPushButton:pressed { background: #335f97; }
QPushButton:disabled { background: #b9c4d3; color: #eef1f6; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 2px; }
QScrollBar::handle:vertical { background: #c4c4cc; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def apply_light_dialog_style(dialog):
    """给对话框套用统一浅色样式。"""
    dialog.setStyleSheet(LIGHT_DIALOG_QSS)
