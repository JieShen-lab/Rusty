from __future__ import annotations


DARK_THEME_QSS = """
QMainWindow, QWidget {
    background-color: #171717;
    color: #f5f5f5;
    font-family: "Microsoft YaHei UI", "Segoe UI";
    font-size: 13px;
}
QWidget#NavBar {
    background-color: #141414;
    border-right: 1px solid #222222;
}
QWidget#PageRoot {
    background-color: #171717;
}
QFrame#Card, QWidget#Card {
    background-color: #242424;
    border: 1px solid #333333;
    border-radius: 12px;
}
QFrame#CardMuted, QWidget#CardMuted {
    background-color: #1f1f1f;
    border: 1px solid #2d2d2d;
    border-radius: 12px;
}
QLabel#PageTitle {
    font-size: 28px;
    font-weight: 700;
    color: #ffffff;
}
QLabel#SectionTitle {
    font-size: 18px;
    font-weight: 600;
    color: #ffffff;
}
QLabel#SubtleText, QLabel#HintText {
    color: #9ca3af;
}
QLabel#WeakText {
    color: #6b7280;
}
QPushButton {
    min-height: 36px;
    padding: 0 14px;
    border-radius: 10px;
    border: 1px solid #3a3a3a;
    background-color: #222222;
    color: #f5f5f5;
}
QPushButton:hover {
    background-color: #2f2f2f;
}
QPushButton:pressed {
    background-color: #303030;
}
QPushButton:disabled {
    color: #7f7f7f;
    background-color: #1d1d1d;
    border-color: #2b2b2b;
}
QPushButton#PrimaryButton {
    background-color: #3b82f6;
    border-color: #3b82f6;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#PrimaryButton:hover {
    background-color: #4b8ef7;
}
QPushButton#DangerButton {
    background-color: transparent;
    border-color: #ef4444;
    color: #ef4444;
}
QPushButton#DangerButton:hover {
    background-color: rgba(239, 68, 68, 0.12);
}
QPushButton#SecondaryButton {
    background-color: #242424;
}
QPushButton#NavButton {
    min-width: 40px;
    max-width: 40px;
    min-height: 40px;
    max-height: 40px;
    padding: 0;
    border-radius: 10px;
    border: 1px solid transparent;
    background-color: transparent;
    color: #9ca3af;
    font-size: 18px;
}
QPushButton#NavButton:hover {
    background-color: #242424;
    color: #ffffff;
}
QPushButton#NavButton:checked {
    background-color: #202a3a;
    color: #ffffff;
    border-left: 3px solid #3b82f6;
}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #1d1d1d;
    color: #f5f5f5;
    border: 1px solid #343434;
    border-radius: 10px;
    padding: 8px 10px;
    selection-background-color: #3b82f6;
    selection-color: #ffffff;
}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
    color: #8a8a8a;
    background-color: #1a1a1a;
    border-color: #2c2c2c;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QListWidget, QTableWidget, QTabWidget::pane {
    background-color: #1f1f1f;
    border: 1px solid #333333;
    border-radius: 12px;
}
QListWidget::item, QTableWidget::item {
    padding: 6px;
}
QListWidget::item:selected, QTableWidget::item:selected {
    background-color: #27364d;
    color: #ffffff;
}
QHeaderView::section {
    background-color: #202020;
    color: #9ca3af;
    border: none;
    border-bottom: 1px solid #333333;
    padding: 8px;
}
QTabBar::tab {
    background-color: #1f1f1f;
    color: #9ca3af;
    padding: 10px 14px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    margin-right: 4px;
}
QTabBar::tab:selected {
    background-color: #2a2a2a;
    color: #ffffff;
}
QProgressBar {
    border: 1px solid #333333;
    border-radius: 8px;
    background-color: #1d1d1d;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #3b82f6;
    border-radius: 7px;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: transparent;
    border: none;
    margin: 2px;
}
QScrollBar:vertical {
    width: 10px;
}
QScrollBar:horizontal {
    height: 10px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #4b4b4b;
    border-radius: 5px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
    border: none;
}
"""


def apply_dark_theme(app_or_widget) -> None:
    app_or_widget.setStyleSheet(DARK_THEME_QSS)
