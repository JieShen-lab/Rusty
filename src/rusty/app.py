from __future__ import annotations

import sys
from pathlib import Path

from rusty.models import ChapterRecord, ProjectSummary
from rusty.services import ProjectService


class RustyMainWindow:
    def __init__(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QAbstractItemView,
            QFileDialog,
            QHBoxLayout,
            QLabel,
            QListWidget,
            QListWidgetItem,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QSplitter,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )

        self.Qt = Qt
        self.QFileDialog = QFileDialog
        self.QListWidgetItem = QListWidgetItem
        self.QMessageBox = QMessageBox
        self.service = ProjectService()
        self.projects: list[ProjectSummary] = []
        self.chapters: list[ChapterRecord] = []
        self.current_project_id: int | None = None

        self.window = QMainWindow()
        self.window.setWindowTitle("Rusty")
        self.window.resize(1280, 780)

        root = QWidget()
        root_layout = QVBoxLayout(root)

        toolbar = QHBoxLayout()
        self.import_button = QPushButton("Import TXT")
        self.export_button = QPushButton("Export TXT")
        self.refresh_button = QPushButton("Refresh")
        self.status_label = QLabel("")
        toolbar.addWidget(self.import_button)
        toolbar.addWidget(self.export_button)
        toolbar.addWidget(self.refresh_button)
        toolbar.addStretch(1)
        toolbar.addWidget(self.status_label)
        root_layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(splitter, 1)

        self.project_list = QListWidget()
        self.project_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        splitter.addWidget(self.project_list)

        self.chapter_list = QListWidget()
        self.chapter_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        splitter.addWidget(self.chapter_list)

        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        self.preview_title = QLabel("Select a chapter")
        self.preview_title.setWordWrap(True)
        self.preview_meta = QLabel("")
        self.preview_meta.setWordWrap(True)
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        preview_layout.addWidget(self.preview_title)
        preview_layout.addWidget(self.preview_meta)
        preview_layout.addWidget(self.preview_text, 1)
        splitter.addWidget(preview_panel)
        splitter.setSizes([300, 360, 620])

        self.window.setCentralWidget(root)

        self.import_button.clicked.connect(self.import_txt)
        self.export_button.clicked.connect(self.export_txt)
        self.refresh_button.clicked.connect(self.load_projects)
        self.project_list.currentItemChanged.connect(self.project_selected)
        self.chapter_list.currentItemChanged.connect(self.chapter_selected)

        self.load_projects()

    def show(self) -> None:
        self.window.show()

    def load_projects(self) -> None:
        self.projects = self.service.list_projects()
        self.project_list.clear()
        for project in self.projects:
            item = self.QListWidgetItem(
                f"{project.name}\n"
                f"{project.total_chapters} chapters | {project.total_words} chars | {project.status}"
            )
            item.setData(self.Qt.ItemDataRole.UserRole, project.id)
            self.project_list.addItem(item)

        self.status_label.setText(f"{len(self.projects)} project(s)")
        if self.projects:
            self.project_list.setCurrentRow(0)
        else:
            self.current_project_id = None
            self.chapter_list.clear()
            self.preview_title.setText("No projects yet")
            self.preview_meta.setText("")
            self.preview_text.setPlainText("Import a TXT file to create the first project.")

    def project_selected(self, current, previous) -> None:
        if current is None:
            return
        project_id = current.data(self.Qt.ItemDataRole.UserRole)
        self.current_project_id = int(project_id)
        self.chapters = self.service.list_chapters(self.current_project_id)
        self.chapter_list.clear()
        for chapter in self.chapters:
            item = self.QListWidgetItem(
                f"{chapter.index}. {chapter.title}\n{chapter.word_count} chars | {chapter.status}"
            )
            item.setData(self.Qt.ItemDataRole.UserRole, chapter.id)
            self.chapter_list.addItem(item)
        self.status_label.setText(f"{len(self.chapters)} chapter(s)")
        if self.chapters:
            self.chapter_list.setCurrentRow(0)
        else:
            self.preview_title.setText("No chapters")
            self.preview_meta.setText("")
            self.preview_text.clear()

    def chapter_selected(self, current, previous) -> None:
        if current is None:
            return
        chapter_id = int(current.data(self.Qt.ItemDataRole.UserRole))
        chapter = self.service.get_chapter(chapter_id)
        if chapter is None:
            return

        line_info = ""
        if chapter.start_line is not None and chapter.end_line is not None:
            line_info = f" | lines {chapter.start_line}-{chapter.end_line}"
        self.preview_title.setText(f"{chapter.index}. {chapter.title}")
        self.preview_meta.setText(f"{chapter.word_count} chars | {chapter.status}{line_info}")
        self.preview_text.setPlainText(chapter.original_text)

    def import_txt(self) -> None:
        path, _ = self.QFileDialog.getOpenFileName(
            self.window,
            "Import TXT",
            str(Path.home()),
            "Text files (*.txt);;All files (*)",
        )
        if not path:
            return

        try:
            project_id = self.service.import_txt(path)
        except Exception as exc:  # noqa: BLE001
            self.QMessageBox.critical(self.window, "Import failed", str(exc))
            return

        self.load_projects()
        self.select_project(project_id)

    def export_txt(self) -> None:
        if self.current_project_id is None:
            self.QMessageBox.information(self.window, "Export TXT", "Select a project first.")
            return

        default_name = self.current_project_name() or "rusty-export"
        path, _ = self.QFileDialog.getSaveFileName(
            self.window,
            "Export TXT",
            str(Path.home() / f"{default_name}.txt"),
            "Text files (*.txt);;All files (*)",
        )
        if not path:
            return

        try:
            output = self.service.export_txt(self.current_project_id, path)
        except Exception as exc:  # noqa: BLE001
            self.QMessageBox.critical(self.window, "Export failed", str(exc))
            return

        self.QMessageBox.information(self.window, "Export TXT", f"Exported to:\n{output}")

    def select_project(self, project_id: int) -> None:
        for row in range(self.project_list.count()):
            item = self.project_list.item(row)
            if int(item.data(self.Qt.ItemDataRole.UserRole)) == project_id:
                self.project_list.setCurrentRow(row)
                return

    def current_project_name(self) -> str | None:
        for project in self.projects:
            if project.id == self.current_project_id:
                return project.name
        return None


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise SystemExit(
            "PySide6 is not installed. Install project dependencies with "
            "`python -m pip install -e .` before launching the app."
        ) from exc

    app = QApplication(sys.argv)
    window = RustyMainWindow()
    window.show()
    return app.exec()
