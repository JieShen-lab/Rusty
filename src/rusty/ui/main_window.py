from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from rusty.models import ChapterRecord, ParsedBook, ProjectSummary
from rusty.services import ProjectService


class NewProjectDialog:
    def __init__(self, parent, service: ProjectService) -> None:
        from PySide6.QtWidgets import (
            QDialog,
            QFileDialog,
            QFormLayout,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QListWidget,
            QMessageBox,
            QPushButton,
            QVBoxLayout,
        )

        self.QFileDialog = QFileDialog
        self.QMessageBox = QMessageBox
        self.service = service
        self.parsed_book: ParsedBook | None = None
        self.created_project_id: int | None = None

        self.dialog = QDialog(parent)
        self.dialog.setWindowTitle("New Project")
        self.dialog.resize(760, 620)

        layout = QVBoxLayout(self.dialog)
        form = QFormLayout()

        file_row = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_button = QPushButton("Browse")
        file_row.addWidget(self.file_edit, 1)
        file_row.addWidget(self.file_button)
        form.addRow("Source file", file_row)

        workspace_row = QHBoxLayout()
        self.workspace_edit = QLineEdit()
        self.workspace_button = QPushButton("Browse")
        workspace_row.addWidget(self.workspace_edit, 1)
        workspace_row.addWidget(self.workspace_button)
        form.addRow("Workspace", workspace_row)

        self.project_name_edit = QLineEdit()
        form.addRow("Project name", self.project_name_edit)

        self.summary_label = QLabel("Select a TXT, EPUB, or DOCX file.")
        self.summary_label.setWordWrap(True)
        form.addRow("Preview", self.summary_label)
        layout.addLayout(form)

        self.chapter_list = QListWidget()
        layout.addWidget(self.chapter_list, 1)

        buttons = QHBoxLayout()
        self.preview_button = QPushButton("Preview")
        self.create_button = QPushButton("Create Project")
        self.cancel_button = QPushButton("Cancel")
        buttons.addStretch(1)
        buttons.addWidget(self.preview_button)
        buttons.addWidget(self.create_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self.file_button.clicked.connect(self.choose_file)
        self.workspace_button.clicked.connect(self.choose_workspace)
        self.preview_button.clicked.connect(self.preview)
        self.create_button.clicked.connect(self.create_project)
        self.cancel_button.clicked.connect(self.dialog.reject)

    def exec(self) -> int:
        return self.dialog.exec()

    def choose_file(self) -> None:
        path, _ = self.QFileDialog.getOpenFileName(
            self.dialog,
            "Import Book",
            str(Path.home()),
            "Book files (*.txt *.epub *.docx);;Text files (*.txt);;EPUB files (*.epub);;Word files (*.docx);;All files (*)",
        )
        if not path:
            return
        self.file_edit.setText(path)
        self.workspace_edit.setText(str(Path(path).parent))
        self.preview()

    def choose_workspace(self) -> None:
        path = self.QFileDialog.getExistingDirectory(
            self.dialog,
            "Select Workspace",
            self.workspace_edit.text() or str(Path.home()),
        )
        if path:
            self.workspace_edit.setText(path)

    def preview(self) -> None:
        path = self.file_edit.text().strip()
        if not path:
            self.QMessageBox.information(self.dialog, "Preview", "Select a source file first.")
            return

        try:
            self.parsed_book = self.service.preview_book(path)
        except Exception as exc:  # noqa: BLE001
            self.QMessageBox.critical(self.dialog, "Preview failed", str(exc))
            return

        if not self.project_name_edit.text().strip():
            self.project_name_edit.setText(self.parsed_book.title)

        self.summary_label.setText(
            f"Format: {self.parsed_book.source_format.upper()} | "
            f"Title: {self.parsed_book.title} | "
            f"Author: {self.parsed_book.author or '-'} | "
            f"Language: {self.parsed_book.language or '-'} | "
            f"Chapters: {len(self.parsed_book.chapters)} | "
            f"Chars: {self.parsed_book.total_words}"
        )
        self.chapter_list.clear()
        for chapter in self.parsed_book.chapters:
            self.chapter_list.addItem(f"{chapter.index}. {chapter.title} | {chapter.word_count} chars")

    def create_project(self) -> None:
        if self.parsed_book is None:
            self.preview()
        if self.parsed_book is None:
            return

        workspace = self.workspace_edit.text().strip() or str(self.parsed_book.source_path.parent)
        project_name = self.project_name_edit.text().strip() or self.parsed_book.title
        try:
            book = replace(self.parsed_book)
            self.created_project_id = self.service.create_project(book, workspace, project_name=project_name)
        except Exception as exc:  # noqa: BLE001
            self.QMessageBox.critical(self.dialog, "Create failed", str(exc))
            return

        self.dialog.accept()


class RustyMainWindow:
    def __init__(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QAbstractItemView,
            QFileDialog,
            QFrame,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QListWidget,
            QListWidgetItem,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QSplitter,
            QStackedWidget,
            QTableWidget,
            QTableWidgetItem,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )

        self.Qt = Qt
        self.QFileDialog = QFileDialog
        self.QListWidgetItem = QListWidgetItem
        self.QMessageBox = QMessageBox
        self.QTableWidgetItem = QTableWidgetItem
        self.service = ProjectService()
        self.projects: list[ProjectSummary] = []
        self.chapters: list[ChapterRecord] = []
        self.current_project_id: int | None = None

        self.window = QMainWindow()
        self.window.setWindowTitle("Rusty")
        self.window.resize(1320, 820)

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)

        nav = QFrame()
        nav.setFrameShape(QFrame.Shape.StyledPanel)
        nav_layout = QVBoxLayout(nav)
        nav_title = QLabel("Rusty")
        self.workbench_nav = QPushButton("Workbench")
        self.preview_nav = QPushButton("Chapter Preview")
        nav_layout.addWidget(nav_title)
        nav_layout.addWidget(self.workbench_nav)
        nav_layout.addWidget(self.preview_nav)
        nav_layout.addStretch(1)
        root_layout.addWidget(nav, 0)

        self.stack = QStackedWidget()
        root_layout.addWidget(self.stack, 1)
        self.workbench_page = self._build_workbench_page()
        self.preview_page = self._build_preview_page()
        self.stack.addWidget(self.workbench_page)
        self.stack.addWidget(self.preview_page)
        self.window.setCentralWidget(root)

        self.workbench_nav.clicked.connect(lambda: self.stack.setCurrentWidget(self.workbench_page))
        self.preview_nav.clicked.connect(lambda: self.stack.setCurrentWidget(self.preview_page))
        self.new_project_button.clicked.connect(self.new_project)
        self.open_preview_button.clicked.connect(self.open_selected_project_preview)
        self.export_txt_button.clicked.connect(self.export_txt)
        self.export_epub_button.clicked.connect(self.export_epub)
        self.refresh_button.clicked.connect(self.load_projects)
        self.preview_export_txt_button.clicked.connect(self.export_txt)
        self.preview_export_epub_button.clicked.connect(self.export_epub)
        self.project_table.itemSelectionChanged.connect(self.project_table_selection_changed)
        self.project_table.doubleClicked.connect(self.open_selected_project_preview)
        self.chapter_list.currentItemChanged.connect(self.chapter_selected)

        self.load_projects()

    def _build_workbench_page(self):
        from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QVBoxLayout, QWidget

        page = QWidget()
        layout = QVBoxLayout(page)
        toolbar = QHBoxLayout()
        self.new_project_button = QPushButton("New Project")
        self.open_preview_button = QPushButton("Open Preview")
        self.export_txt_button = QPushButton("Export TXT")
        self.export_epub_button = QPushButton("Export EPUB")
        self.refresh_button = QPushButton("Refresh")
        self.status_label = QLabel("")
        toolbar.addWidget(self.new_project_button)
        toolbar.addWidget(self.open_preview_button)
        toolbar.addWidget(self.export_txt_button)
        toolbar.addWidget(self.export_epub_button)
        toolbar.addWidget(self.refresh_button)
        toolbar.addStretch(1)
        toolbar.addWidget(self.status_label)
        layout.addLayout(toolbar)

        self.project_table = QTableWidget(0, 8)
        self.project_table.setHorizontalHeaderLabels(
            ["ID", "Name", "Book", "Format", "Chapters", "Chars", "Status", "Updated"]
        )
        self.project_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.project_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.project_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.project_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.project_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.project_table, 1)
        return page

    def _build_preview_page(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QLabel, QListWidget, QPushButton, QSplitter, QTextEdit, QVBoxLayout, QWidget

        page = QWidget()
        layout = QVBoxLayout(page)
        toolbar = QHBoxLayout()
        self.preview_project_label = QLabel("No project selected")
        self.preview_export_txt_button = QPushButton("Export TXT")
        self.preview_export_epub_button = QPushButton("Export EPUB")
        toolbar.addWidget(self.preview_project_label)
        toolbar.addStretch(1)
        toolbar.addWidget(self.preview_export_txt_button)
        toolbar.addWidget(self.preview_export_epub_button)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.chapter_list = QListWidget()
        self.chapter_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        splitter.addWidget(self.chapter_list)

        preview_panel = QWidget()
        preview_panel_layout = QVBoxLayout(preview_panel)
        self.preview_title = QLabel("Select a project")
        self.preview_title.setWordWrap(True)
        self.preview_meta = QLabel("")
        self.preview_meta.setWordWrap(True)
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        preview_panel_layout.addWidget(self.preview_title)
        preview_panel_layout.addWidget(self.preview_meta)
        preview_panel_layout.addWidget(self.preview_text, 1)
        splitter.addWidget(preview_panel)
        splitter.setSizes([360, 840])
        layout.addWidget(splitter, 1)
        return page

    def show(self) -> None:
        self.window.show()

    def load_projects(self) -> None:
        self.projects = self.service.list_projects()
        self.project_table.setRowCount(0)
        for project in self.projects:
            row = self.project_table.rowCount()
            self.project_table.insertRow(row)
            values = [
                project.id,
                project.name,
                project.book_title or "",
                (project.source_format or "").upper(),
                project.total_chapters,
                project.total_words,
                project.status,
                project.updated_at,
            ]
            for column, value in enumerate(values):
                item = self.QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(self.Qt.ItemDataRole.UserRole, project.id)
                self.project_table.setItem(row, column, item)

        self.status_label.setText(f"{len(self.projects)} project(s)")
        if self.projects and self.current_project_id is None:
            self.current_project_id = self.projects[0].id
            self.project_table.selectRow(0)
        elif self.current_project_id is not None:
            self.select_project_row(self.current_project_id)
        else:
            self.clear_preview()

    def new_project(self) -> None:
        dialog = NewProjectDialog(self.window, self.service)
        result = dialog.exec()
        if result and dialog.created_project_id is not None:
            self.current_project_id = dialog.created_project_id
            self.load_projects()
            self.open_project_preview(dialog.created_project_id)

    def project_table_selection_changed(self) -> None:
        project_id = self.selected_project_id()
        if project_id is not None:
            self.current_project_id = project_id

    def open_selected_project_preview(self) -> None:
        project_id = self.selected_project_id()
        if project_id is None:
            self.QMessageBox.information(self.window, "Chapter Preview", "Select a project first.")
            return
        self.open_project_preview(project_id)

    def open_project_preview(self, project_id: int) -> None:
        self.current_project_id = project_id
        self.chapters = self.service.list_chapters(project_id)
        project = self.service.get_project(project_id)
        self.preview_project_label.setText(project.name if project is not None else f"Project {project_id}")
        self.chapter_list.clear()
        for chapter in self.chapters:
            item = self.QListWidgetItem(
                f"{chapter.index}. {chapter.title}\n{chapter.word_count} chars | {chapter.status}"
            )
            item.setData(self.Qt.ItemDataRole.UserRole, chapter.id)
            self.chapter_list.addItem(item)

        self.stack.setCurrentWidget(self.preview_page)
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

    def export_txt(self) -> None:
        project_id = self.active_project_id()
        if project_id is None:
            self.QMessageBox.information(self.window, "Export TXT", "Select a project first.")
            return
        default_name = self.project_name(project_id) or "rusty-export"
        path, _ = self.QFileDialog.getSaveFileName(
            self.window,
            "Export TXT",
            str(Path.home() / f"{default_name}.txt"),
            "Text files (*.txt);;All files (*)",
        )
        if path:
            self._run_export(lambda: self.service.export_txt(project_id, path), "Export TXT")

    def export_epub(self) -> None:
        project_id = self.active_project_id()
        if project_id is None:
            self.QMessageBox.information(self.window, "Export EPUB", "Select a project first.")
            return
        default_name = self.project_name(project_id) or "rusty-export"
        path, _ = self.QFileDialog.getSaveFileName(
            self.window,
            "Export EPUB",
            str(Path.home() / f"{default_name}.epub"),
            "EPUB files (*.epub);;All files (*)",
        )
        if path:
            self._run_export(lambda: self.service.export_epub(project_id, path), "Export EPUB")

    def _run_export(self, export_func, title: str) -> None:
        try:
            output = export_func()
        except Exception as exc:  # noqa: BLE001
            self.QMessageBox.critical(self.window, "Export failed", str(exc))
            return
        self.QMessageBox.information(self.window, title, f"Exported to:\n{output}")

    def selected_project_id(self) -> int | None:
        selected = self.project_table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        item = self.project_table.item(row, 0)
        return int(item.data(self.Qt.ItemDataRole.UserRole))

    def active_project_id(self) -> int | None:
        return self.selected_project_id() or self.current_project_id

    def select_project_row(self, project_id: int) -> None:
        for row in range(self.project_table.rowCount()):
            item = self.project_table.item(row, 0)
            if item is not None and int(item.data(self.Qt.ItemDataRole.UserRole)) == project_id:
                self.project_table.selectRow(row)
                return

    def project_name(self, project_id: int) -> str | None:
        for project in self.projects:
            if project.id == project_id:
                return project.name
        return None

    def clear_preview(self) -> None:
        self.current_project_id = None
        self.chapters = []
        self.chapter_list.clear()
        self.preview_project_label.setText("No project selected")
        self.preview_title.setText("No projects yet")
        self.preview_meta.setText("")
        self.preview_text.setPlainText("Create a project to preview chapters.")

