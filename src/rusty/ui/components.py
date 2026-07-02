from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QProgressBar, QVBoxLayout, QWidget


STATUS_STYLES = {
    "idle": ("待启动", "#6b7280"),
    "imported": ("待启动", "#6b7280"),
    "ready": ("待启动", "#6b7280"),
    "processing": ("处理中", "#3b82f6"),
    "processed": ("已完成", "#22c55e"),
    "partial": ("部分完成", "#eab308"),
    "paused": ("已暂停", "#9ca3af"),
    "failed": ("失败", "#ef4444"),
    "needs_rewrite": ("需改写", "#eab308"),
}


def create_card(layout_direction: str = "vertical", object_name: str = "Card") -> tuple[QFrame, QVBoxLayout | QHBoxLayout]:
    frame = QFrame()
    frame.setObjectName(object_name)
    layout = QHBoxLayout(frame) if layout_direction == "horizontal" else QVBoxLayout(frame)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)
    return frame, layout


def create_page_header(title: str, subtitle: str, action: QPushButton | None = None) -> QWidget:
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    text_block = QWidget()
    text_layout = QVBoxLayout(text_block)
    text_layout.setContentsMargins(0, 0, 0, 0)
    text_layout.setSpacing(4)
    title_label = QLabel(title)
    title_label.setObjectName("PageTitle")
    subtitle_label = QLabel(subtitle)
    subtitle_label.setObjectName("SubtleText")
    text_layout.addWidget(title_label)
    text_layout.addWidget(subtitle_label)
    layout.addWidget(text_block, 1)
    if action is not None:
        layout.addWidget(action, 0, Qt.AlignmentFlag.AlignTop)
    return widget


def create_status_pill(text: str, color: str, object_name: str = "Pill") -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setStyleSheet(
        f"background-color: transparent; color: {color}; border: 1px solid {color}; "
        "border-radius: 11px; padding: 4px 10px;"
    )
    return label


def create_project_status_pill(status: str) -> QLabel:
    text, color = STATUS_STYLES.get(status, (status or "未知", "#9ca3af"))
    return create_status_pill(text, color)


def create_metric_card(label: str, value: str, accent: str = "#f5f5f5") -> QFrame:
    card, layout = create_card(object_name="CardMuted")
    title_label = QLabel(label)
    title_label.setObjectName("SubtleText")
    value_label = QLabel(value)
    value_label.setStyleSheet(f"font-size: 24px; font-weight: 700; color: {accent};")
    layout.addWidget(title_label)
    layout.addWidget(value_label)
    layout.addStretch(1)
    return card


def create_primary_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("PrimaryButton")
    return button


def create_secondary_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("SecondaryButton")
    return button


def create_danger_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("DangerButton")
    return button


def create_empty_state(title: str, subtitle: str, button: QPushButton | None = None) -> QFrame:
    card, layout = create_card(object_name="Card")
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title_label = QLabel(title)
    title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title_label.setStyleSheet("font-size: 22px; font-weight: 700; color: #ffffff;")
    subtitle_label = QLabel(subtitle)
    subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    subtitle_label.setWordWrap(True)
    subtitle_label.setObjectName("SubtleText")
    layout.addWidget(title_label)
    layout.addWidget(subtitle_label)
    if button is not None:
        layout.addWidget(button, 0, Qt.AlignmentFlag.AlignCenter)
    return card


def create_progress_bar(value: int, maximum: int) -> QProgressBar:
    bar = QProgressBar()
    bar.setRange(0, max(1, maximum))
    bar.setValue(min(value, max(1, maximum)))
    return bar


def create_stepper(labels: list[str]) -> tuple[QWidget, list[QPushButton]]:
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    buttons: list[QPushButton] = []
    for index, label in enumerate(labels):
        button = create_secondary_button(f"{index + 1}. {label}")
        button.setCheckable(True)
        buttons.append(button)
        layout.addWidget(button)
    layout.addStretch(1)
    return widget, buttons
