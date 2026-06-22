"""Shared glassmorphism UI theme for panels and dialogs."""

from __future__ import annotations

from ui.window_chrome import install_custom_window_chrome


PANEL_QSS = """
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(58, 68, 86, 238),
        stop:1 rgba(22, 28, 37, 238)
    );
    border: 1px solid rgba(120, 180, 255, 145);
    border-radius: 18px;
"""


def overlay_qss(object_name: str) -> str:
    """Return a complete overlay stylesheet for the given object name."""
    return f"""
        #{object_name} {{
            {PANEL_QSS}
        }}
        QLabel#panelTitle {{
            color: #f3f7ff;
            font-size: 20px;
            font-weight: 700;
            background: transparent;
        }}
        QLabel#sectionLabel, QLabel#hintLabel {{
            color: #9fc9ff;
            font-size: 12px;
            background: transparent;
        }}
        QLabel#metaValue {{
            color: rgba(215, 230, 255, 180);
            font-size: 12px;
            background: transparent;
        }}
        QLabel#infoValue, QLabel {{
            color: #d7e6ff;
            font-size: 13px;
            background: transparent;
        }}
        QLabel#heroTitle {{
            color: #ffffff;
            font-size: 18px;
            font-weight: 700;
            background: transparent;
        }}
        QLabel#infoBadge {{
            color: #d7e6ff;
            background: rgba(120, 180, 255, 34);
            border: 1px solid rgba(120, 180, 255, 70);
            border-radius: 8px;
            padding: 5px 8px;
            font-size: 12px;
        }}
        QFrame#summaryCard {{
            background: rgba(255, 255, 255, 18);
            border: 1px solid rgba(120, 180, 255, 70);
            border-radius: 12px;
        }}
        QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit {{
            background: rgba(18, 22, 29, 215);
            color: #f2f6ff;
            border: 1px solid rgba(120, 180, 255, 105);
            border-radius: 8px;
            padding: 7px 9px;
            min-height: 24px;
            selection-background-color: rgba(105, 178, 255, 150);
            selection-color: #ffffff;
        }}
        QTextEdit, QPlainTextEdit {{
            font-family: Consolas, "Courier New", monospace;
            font-size: 12px;
        }}
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 1px solid rgba(130, 195, 255, 210);
            background: rgba(25, 32, 43, 230);
        }}
        QComboBox:hover, QSpinBox:hover, QLineEdit:hover {{
            border: 1px solid rgba(120, 180, 255, 170);
        }}
        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}
        QComboBox QAbstractItemView {{
            background: #202a39;
            color: #f2f6ff;
            selection-background-color: rgba(120, 180, 255, 85);
            border: 1px solid rgba(120, 180, 255, 120);
            outline: 0;
        }}
        QPushButton {{
            background: rgba(255, 255, 255, 24);
            color: #f6f9ff;
            border: 1px solid rgba(120, 180, 255, 105);
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 13px;
            min-height: 24px;
        }}
        QPushButton:hover {{
            background: rgba(120, 180, 255, 55);
            border: 1px solid rgba(120, 180, 255, 170);
        }}
        QPushButton:pressed {{
            background: rgba(80, 150, 255, 80);
        }}
        QPushButton:disabled {{
            background: rgba(255, 255, 255, 10);
            color: rgba(220, 230, 245, 95);
            border: 1px solid rgba(120, 180, 255, 45);
        }}
        QPushButton#dangerButton {{
            background: rgba(150, 70, 70, 100);
            border: 1px solid rgba(255, 150, 150, 100);
        }}
        QPushButton#dangerButton:hover {{
            background: rgba(180, 85, 85, 135);
            border: 1px solid rgba(255, 170, 170, 145);
        }}
        QPushButton#secondaryButton, QPushButton#cancelButton {{
            background: rgba(255, 255, 255, 14);
            color: #d7e6ff;
        }}
        QCheckBox, QRadioButton {{
            color: #d7e6ff;
            font-size: 13px;
            spacing: 7px;
            background: transparent;
        }}
        QCheckBox::indicator, QRadioButton::indicator {{
            width: 14px;
            height: 14px;
        }}
        QListWidget, QTableView {{
            background: rgba(13, 18, 26, 190);
            color: #edf4ff;
            border: 1px solid rgba(120, 180, 255, 75);
            border-radius: 8px;
            padding: 4px;
            outline: none;
        }}
        QListWidget::item {{
            padding: 6px 8px;
            border-bottom: 1px solid rgba(255, 255, 255, 16);
        }}
        QListWidget::item:selected, QTableView::item:selected {{
            background: rgba(105, 178, 255, 115);
            color: #ffffff;
            border-radius: 4px;
        }}
        QListWidget::item:hover, QTableView::item:hover {{
            background: rgba(120, 180, 255, 42);
            border-radius: 4px;
        }}
        QTabWidget::pane {{
            border: 1px solid rgba(120, 180, 255, 75);
            border-radius: 10px;
            background: rgba(12, 18, 25, 120);
        }}
        QTabBar::tab {{
            background: rgba(255, 255, 255, 18);
            color: #c7d7ef;
            padding: 7px 9px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            margin-right: 2px;
            font-size: 12px;
        }}
        QTabBar::tab:selected {{
            background: rgba(120, 180, 255, 65);
            color: #ffffff;
            font-weight: 600;
        }}
        QHeaderView::section {{
            background: rgba(20, 28, 38, 230);
            color: #d7e6ff;
            border: none;
            border-bottom: 1px solid rgba(120, 180, 255, 60);
            padding: 7px 8px;
        }}
        QScrollArea {{
            background: transparent;
            border: none;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: rgba(120, 180, 255, 120);
            border-radius: 4px;
            min-height: 24px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
    """


APP_QSS = f"""
    QMainWindow {{
        background: #090d14;
        color: #eaf3ff;
    }}
    QStatusBar {{
        background: rgba(16, 22, 32, 240);
        color: #9fc9ff;
        border-top: 1px solid rgba(120, 180, 255, 80);
    }}
    QSplitter::handle {{
        background: rgba(120, 180, 255, 45);
        width: 2px;
    }}
    QFrame#playerPanel, QFrame#playerHost {{
        background: rgba(14, 20, 27, 170);
        border: 1px solid rgba(120, 180, 255, 75);
        border-radius: 14px;
    }}
    QFrame#summaryCard {{
        background: rgba(255, 255, 255, 18);
        border: 1px solid rgba(120, 180, 255, 70);
        border-radius: 12px;
    }}
    QFrame#mpvViewport {{
        background: #000000;
        border-radius: 8px;
    }}
    QFrame#loadingOverlay {{
        background: rgba(0, 0, 0, 205);
        border-radius: 8px;
    }}
    QFrame#progressOverlay {{
        background: transparent;
    }}
    QFrame#progressContainer {{
        background: rgba(10, 14, 20, 220);
        border: 1px solid rgba(120, 180, 255, 85);
        border-radius: 10px;
    }}
    QLabel#panelTitle {{
        color: #f3f7ff;
        font-size: 18px;
        font-weight: 700;
        background: transparent;
    }}
    QLabel#sectionLabel {{
        color: #9fc9ff;
        font-size: 13px;
        background: transparent;
    }}
    QLabel#infoValue {{
        color: #d7e6ff;
        font-size: 13px;
        background: transparent;
    }}
    QLabel#metaValue {{
        color: rgba(215, 230, 255, 180);
        font-size: 12px;
        background: transparent;
    }}
    QLabel#heroTitle {{
        color: #ffffff;
        font-size: 18px;
        font-weight: 700;
        background: transparent;
    }}
    QLabel#stateBadge {{
        background: rgba(120, 180, 255, 42);
        color: #f6f9ff;
        border: 1px solid rgba(120, 180, 255, 95);
        border-radius: 8px;
        padding: 6px 12px;
        font-size: 12px;
        font-weight: 600;
    }}
    QLabel#warningLabel {{
        background: rgba(184, 108, 35, 145);
        color: #fff4df;
        border: 1px solid rgba(255, 190, 100, 145);
        border-radius: 8px;
        padding: 11px 14px;
        font-size: 13px;
        font-weight: 600;
    }}
    QLabel#timeLabel {{
        color: #ffffff;
        font-size: 14px;
        font-weight: 600;
        background: transparent;
    }}
    QLabel#infoBadge {{
        color: #d7e6ff;
        background: rgba(120, 180, 255, 34);
        border: 1px solid rgba(120, 180, 255, 70);
        border-radius: 8px;
        padding: 5px 8px;
        font-size: 12px;
    }}
    QDialog, QMessageBox, QInputDialog {{
        background: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 rgba(58, 68, 86, 248),
            stop:1 rgba(22, 28, 37, 248)
        );
        color: #f2f6ff;
    }}
    QDialog QLabel, QMessageBox QLabel, QInputDialog QLabel {{
        color: #d7e6ff;
        background: transparent;
    }}
    QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit {{
        background: rgba(18, 22, 29, 215);
        color: #f2f6ff;
        border: 1px solid rgba(120, 180, 255, 105);
        border-radius: 8px;
        padding: 7px 9px;
        selection-background-color: rgba(105, 178, 255, 150);
    }}
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border: 1px solid rgba(130, 195, 255, 210);
        background: rgba(25, 32, 43, 230);
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background: #202a39;
        color: #f2f6ff;
        selection-background-color: rgba(120, 180, 255, 85);
        border: 1px solid rgba(120, 180, 255, 120);
        outline: 0;
    }}
    QPushButton {{
        background: rgba(255, 255, 255, 24);
        color: #f6f9ff;
        border: 1px solid rgba(120, 180, 255, 105);
        border-radius: 8px;
        padding: 8px 12px;
        font-size: 13px;
        min-height: 24px;
    }}
    QPushButton:hover {{
        background: rgba(120, 180, 255, 55);
        border: 1px solid rgba(120, 180, 255, 170);
    }}
    QPushButton:pressed {{
        background: rgba(80, 150, 255, 80);
    }}
    QPushButton:disabled {{
        background: rgba(255, 255, 255, 10);
        color: rgba(220, 230, 245, 95);
        border: 1px solid rgba(120, 180, 255, 45);
    }}
    QDialogButtonBox QPushButton {{
        min-width: 84px;
    }}
    QCheckBox, QRadioButton {{
        color: #d7e6ff;
        spacing: 7px;
        background: transparent;
    }}
    QListWidget, QTableView {{
        background: rgba(13, 18, 26, 190);
        color: #edf4ff;
        border: 1px solid rgba(120, 180, 255, 75);
        border-radius: 8px;
        outline: none;
    }}
    QListWidget::item {{
        padding: 6px 8px;
    }}
    QListWidget::item:selected, QTableView::item:selected {{
        background: rgba(105, 178, 255, 115);
        color: #ffffff;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(120, 180, 255, 120);
        border-radius: 4px;
        min-height: 24px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
"""


GLASS_DIALOG_QSS = overlay_qss("glassDialog").replace("#glassDialog", "QDialog")


def apply_glass_dialog_style(dialog) -> None:
    """Apply the shared glass style to standalone dialogs."""
    dialog.setObjectName("glassDialog")
    dialog.setStyleSheet(GLASS_DIALOG_QSS)
    install_custom_window_chrome(dialog, show_window_controls=False, resizable=False)
