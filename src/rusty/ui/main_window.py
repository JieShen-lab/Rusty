from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from rusty.models import ChapterRecord, ParsedBook, ProjectSummary
from rusty.services import ModelService, ProjectService, PromptService


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
        self.model_service = ModelService(self.service.database_path)
        self.prompt_service = PromptService(self.service.database_path)
        self.projects: list[ProjectSummary] = []
        self.chapters: list[ChapterRecord] = []
        self.current_project_id: int | None = None
        self.current_model_id: int | None = None
        self.current_template_id: int | None = None

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
        self.models_nav = QPushButton("Models")
        self.prompts_nav = QPushButton("Prompts")
        nav_layout.addWidget(nav_title)
        nav_layout.addWidget(self.workbench_nav)
        nav_layout.addWidget(self.preview_nav)
        nav_layout.addWidget(self.models_nav)
        nav_layout.addWidget(self.prompts_nav)
        nav_layout.addStretch(1)
        root_layout.addWidget(nav, 0)

        self.stack = QStackedWidget()
        root_layout.addWidget(self.stack, 1)
        self.workbench_page = self._build_workbench_page()
        self.preview_page = self._build_preview_page()
        self.models_page = self._build_models_page()
        self.prompts_page = self._build_prompts_page()
        self.stack.addWidget(self.workbench_page)
        self.stack.addWidget(self.preview_page)
        self.stack.addWidget(self.models_page)
        self.stack.addWidget(self.prompts_page)
        self.window.setCentralWidget(root)

        self.workbench_nav.clicked.connect(lambda: self.stack.setCurrentWidget(self.workbench_page))
        self.preview_nav.clicked.connect(lambda: self.stack.setCurrentWidget(self.preview_page))
        self.models_nav.clicked.connect(lambda: self.stack.setCurrentWidget(self.models_page))
        self.prompts_nav.clicked.connect(lambda: self.stack.setCurrentWidget(self.prompts_page))
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
        self.model_table.itemSelectionChanged.connect(self.model_selection_changed)
        self.model_new_button.clicked.connect(self.clear_model_form)
        self.model_save_button.clicked.connect(self.save_model)
        self.model_delete_button.clicked.connect(self.delete_model)
        self.template_table.itemSelectionChanged.connect(self.template_selection_changed)
        self.template_new_button.clicked.connect(self.clear_template_form)
        self.template_save_button.clicked.connect(self.save_template)
        self.template_delete_button.clicked.connect(self.delete_template)
        self.project_prompt_save_button.clicked.connect(self.save_project_prompt)

        self.load_projects()
        self.load_models()
        self.load_templates()

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

    def _build_models_page(self):
        from PySide6.QtWidgets import (
            QAbstractItemView,
            QCheckBox,
            QDoubleSpinBox,
            QFormLayout,
            QHBoxLayout,
            QHeaderView,
            QLineEdit,
            QPushButton,
            QSpinBox,
            QTableWidget,
            QVBoxLayout,
            QWidget,
        )

        page = QWidget()
        layout = QVBoxLayout(page)
        buttons = QHBoxLayout()
        self.model_new_button = QPushButton("New")
        self.model_save_button = QPushButton("Save")
        self.model_delete_button = QPushButton("Delete")
        buttons.addWidget(self.model_new_button)
        buttons.addWidget(self.model_save_button)
        buttons.addWidget(self.model_delete_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.model_table = QTableWidget(0, 7)
        self.model_table.setHorizontalHeaderLabels(
            ["ID", "Name", "Provider", "Model", "Base URL", "Default", "API Key"]
        )
        self.model_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.model_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.model_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.model_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.model_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.model_table, 1)

        form = QFormLayout()
        self.model_name_edit = QLineEdit()
        self.model_provider_edit = QLineEdit("openai_compatible")
        self.model_base_url_edit = QLineEdit("https://api.openai.com/v1")
        self.model_name_value_edit = QLineEdit()
        self.model_api_key_edit = QLineEdit()
        self.model_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.model_temperature_spin = QDoubleSpinBox()
        self.model_temperature_spin.setRange(0, 2)
        self.model_temperature_spin.setSingleStep(0.1)
        self.model_temperature_spin.setValue(0.7)
        self.model_max_tokens_spin = QSpinBox()
        self.model_max_tokens_spin.setRange(0, 2_000_000)
        self.model_timeout_spin = QSpinBox()
        self.model_timeout_spin.setRange(1, 3600)
        self.model_timeout_spin.setValue(60)
        self.model_default_check = QCheckBox("Default model")
        form.addRow("Display name", self.model_name_edit)
        form.addRow("Provider", self.model_provider_edit)
        form.addRow("Base URL", self.model_base_url_edit)
        form.addRow("Model", self.model_name_value_edit)
        form.addRow("API key", self.model_api_key_edit)
        form.addRow("Temperature", self.model_temperature_spin)
        form.addRow("Max tokens (0 = unset)", self.model_max_tokens_spin)
        form.addRow("Timeout seconds", self.model_timeout_spin)
        form.addRow("", self.model_default_check)
        layout.addLayout(form)
        return page

    def _build_prompts_page(self):
        from PySide6.QtWidgets import (
            QAbstractItemView,
            QCheckBox,
            QComboBox,
            QFormLayout,
            QHBoxLayout,
            QHeaderView,
            QLineEdit,
            QPlainTextEdit,
            QPushButton,
            QTableWidget,
            QVBoxLayout,
            QWidget,
        )

        page = QWidget()
        layout = QVBoxLayout(page)
        buttons = QHBoxLayout()
        self.template_new_button = QPushButton("New")
        self.template_save_button = QPushButton("Save")
        self.template_delete_button = QPushButton("Delete")
        buttons.addWidget(self.template_new_button)
        buttons.addWidget(self.template_save_button)
        buttons.addWidget(self.template_delete_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.template_table = QTableWidget(0, 4)
        self.template_table.setHorizontalHeaderLabels(["ID", "Name", "Version", "Default"])
        self.template_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.template_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.template_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.template_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.template_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.template_table, 1)

        form = QFormLayout()
        self.template_name_edit = QLineEdit()
        self.template_default_check = QCheckBox("Default template")
        self.global_rules_edit = QPlainTextEdit()
        self.summary_rules_edit = QPlainTextEdit()
        self.scene_rules_edit = QPlainTextEdit()
        self.rewrite_rules_edit = QPlainTextEdit()
        form.addRow("Template name", self.template_name_edit)
        form.addRow("", self.template_default_check)
        form.addRow("Global rules", self.global_rules_edit)
        form.addRow("Summary rules", self.summary_rules_edit)
        form.addRow("Scene detection rules", self.scene_rules_edit)
        form.addRow("Rewrite rules", self.rewrite_rules_edit)
        layout.addLayout(form)

        project_form = QFormLayout()
        self.project_prompt_project_combo = QComboBox()
        self.project_prompt_key_edit = QLineEdit("global_override")
        self.project_prompt_text_edit = QPlainTextEdit()
        self.project_prompt_save_button = QPushButton("Save Project Prompt")
        project_form.addRow("Project", self.project_prompt_project_combo)
        project_form.addRow("Prompt key", self.project_prompt_key_edit)
        project_form.addRow("Prompt text", self.project_prompt_text_edit)
        project_form.addRow("", self.project_prompt_save_button)
        layout.addLayout(project_form)
        return page

    def show(self) -> None:
        self.window.show()

    def load_projects(self) -> None:
        self.projects = self.service.list_projects()
        self.project_table.setRowCount(0)
        self.project_prompt_project_combo.clear()
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
            self.project_prompt_project_combo.addItem(project.name, project.id)

        self.status_label.setText(f"{len(self.projects)} project(s)")
        if self.projects and self.current_project_id is None:
            self.current_project_id = self.projects[0].id
            self.project_table.selectRow(0)
        elif self.current_project_id is not None:
            self.select_project_row(self.current_project_id)
        else:
            self.clear_preview()

    def load_models(self) -> None:
        self.model_table.setRowCount(0)
        for model in self.model_service.list_models():
            row = self.model_table.rowCount()
            self.model_table.insertRow(row)
            values = [
                model.id,
                model.display_name,
                model.provider,
                model.model_name,
                model.base_url,
                "yes" if model.is_default else "",
                "saved" if model.has_api_key else "",
            ]
            for column, value in enumerate(values):
                item = self.QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(self.Qt.ItemDataRole.UserRole, model.id)
                self.model_table.setItem(row, column, item)

    def model_selection_changed(self) -> None:
        selected = self.model_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        self.current_model_id = int(self.model_table.item(row, 0).data(self.Qt.ItemDataRole.UserRole))
        models = {model.id: model for model in self.model_service.list_models()}
        model = models.get(self.current_model_id)
        if model is None:
            return
        self.model_name_edit.setText(model.display_name)
        self.model_provider_edit.setText(model.provider)
        self.model_base_url_edit.setText(model.base_url)
        self.model_name_value_edit.setText(model.model_name)
        self.model_api_key_edit.clear()
        self.model_api_key_edit.setPlaceholderText("Saved; enter a new key to replace")
        self.model_temperature_spin.setValue(model.temperature)
        self.model_max_tokens_spin.setValue(model.max_tokens or 0)
        self.model_timeout_spin.setValue(model.timeout_seconds)
        self.model_default_check.setChecked(model.is_default)

    def clear_model_form(self) -> None:
        self.current_model_id = None
        self.model_table.clearSelection()
        self.model_name_edit.clear()
        self.model_provider_edit.setText("openai_compatible")
        self.model_base_url_edit.setText("https://api.openai.com/v1")
        self.model_name_value_edit.clear()
        self.model_api_key_edit.clear()
        self.model_api_key_edit.setPlaceholderText("")
        self.model_temperature_spin.setValue(0.7)
        self.model_max_tokens_spin.setValue(0)
        self.model_timeout_spin.setValue(60)
        self.model_default_check.setChecked(False)

    def save_model(self) -> None:
        max_tokens = self.model_max_tokens_spin.value() or None
        api_key = self.model_api_key_edit.text().strip() or None
        try:
            if self.current_model_id is None:
                self.current_model_id = self.model_service.create_model(
                    display_name=self.model_name_edit.text().strip(),
                    provider=self.model_provider_edit.text().strip(),
                    base_url=self.model_base_url_edit.text().strip(),
                    model_name=self.model_name_value_edit.text().strip(),
                    api_key=api_key,
                    temperature=self.model_temperature_spin.value(),
                    max_tokens=max_tokens,
                    timeout_seconds=self.model_timeout_spin.value(),
                    is_default=self.model_default_check.isChecked(),
                )
            else:
                self.model_service.update_model(
                    model_id=self.current_model_id,
                    display_name=self.model_name_edit.text().strip(),
                    provider=self.model_provider_edit.text().strip(),
                    base_url=self.model_base_url_edit.text().strip(),
                    model_name=self.model_name_value_edit.text().strip(),
                    api_key=api_key,
                    temperature=self.model_temperature_spin.value(),
                    max_tokens=max_tokens,
                    timeout_seconds=self.model_timeout_spin.value(),
                    is_default=self.model_default_check.isChecked(),
                )
        except Exception as exc:  # noqa: BLE001
            self.QMessageBox.critical(self.window, "Save model failed", str(exc))
            return
        self.model_api_key_edit.clear()
        self.load_models()
        if self.current_model_id is not None:
            self.select_table_row(self.model_table, self.current_model_id)

    def delete_model(self) -> None:
        if self.current_model_id is None:
            return
        self.model_service.delete_model(self.current_model_id)
        self.clear_model_form()
        self.load_models()

    def load_templates(self) -> None:
        self.template_table.setRowCount(0)
        for template in self.prompt_service.list_templates():
            row = self.template_table.rowCount()
            self.template_table.insertRow(row)
            values = [
                template.id,
                template.name,
                template.version,
                "yes" if template.is_default else "",
            ]
            for column, value in enumerate(values):
                item = self.QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(self.Qt.ItemDataRole.UserRole, template.id)
                self.template_table.setItem(row, column, item)

    def template_selection_changed(self) -> None:
        selected = self.template_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        self.current_template_id = int(self.template_table.item(row, 0).data(self.Qt.ItemDataRole.UserRole))
        template = self.prompt_service.get_template(self.current_template_id)
        if template is None:
            return
        self.template_name_edit.setText(template.name)
        self.template_default_check.setChecked(template.is_default)
        self.global_rules_edit.setPlainText(template.global_rules)
        self.summary_rules_edit.setPlainText(template.summary_rules)
        self.scene_rules_edit.setPlainText(template.scene_detection_rules)
        self.rewrite_rules_edit.setPlainText(template.rewrite_rules)

    def clear_template_form(self) -> None:
        self.current_template_id = None
        self.template_table.clearSelection()
        self.template_name_edit.clear()
        self.template_default_check.setChecked(False)
        self.global_rules_edit.clear()
        self.summary_rules_edit.clear()
        self.scene_rules_edit.clear()
        self.rewrite_rules_edit.clear()

    def save_template(self) -> None:
        try:
            if self.current_template_id is None:
                self.current_template_id = self.prompt_service.create_template(
                    name=self.template_name_edit.text().strip(),
                    global_rules=self.global_rules_edit.toPlainText(),
                    summary_rules=self.summary_rules_edit.toPlainText(),
                    scene_detection_rules=self.scene_rules_edit.toPlainText(),
                    rewrite_rules=self.rewrite_rules_edit.toPlainText(),
                    is_default=self.template_default_check.isChecked(),
                )
            else:
                self.prompt_service.update_template(
                    template_id=self.current_template_id,
                    name=self.template_name_edit.text().strip(),
                    global_rules=self.global_rules_edit.toPlainText(),
                    summary_rules=self.summary_rules_edit.toPlainText(),
                    scene_detection_rules=self.scene_rules_edit.toPlainText(),
                    rewrite_rules=self.rewrite_rules_edit.toPlainText(),
                    is_default=self.template_default_check.isChecked(),
                )
        except Exception as exc:  # noqa: BLE001
            self.QMessageBox.critical(self.window, "Save template failed", str(exc))
            return
        self.load_templates()
        if self.current_template_id is not None:
            self.select_table_row(self.template_table, self.current_template_id)

    def delete_template(self) -> None:
        if self.current_template_id is None:
            return
        self.prompt_service.delete_template(self.current_template_id)
        self.clear_template_form()
        self.load_templates()

    def save_project_prompt(self) -> None:
        project_id = self.project_prompt_project_combo.currentData()
        prompt_key = self.project_prompt_key_edit.text().strip()
        if project_id is None or not prompt_key:
            self.QMessageBox.information(self.window, "Project prompt", "Select a project and prompt key first.")
            return
        try:
            self.prompt_service.save_project_prompt(
                int(project_id),
                prompt_key,
                self.project_prompt_text_edit.toPlainText(),
            )
        except Exception as exc:  # noqa: BLE001
            self.QMessageBox.critical(self.window, "Save project prompt failed", str(exc))
            return
        self.QMessageBox.information(self.window, "Project prompt", "Project prompt saved.")

    def select_table_row(self, table, row_id: int) -> None:
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item is not None and int(item.data(self.Qt.ItemDataRole.UserRole)) == row_id:
                table.selectRow(row)
                return

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
