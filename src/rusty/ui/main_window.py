from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from rusty.models import ChapterRecord, ParsedBook, ProjectSummary
from rusty.services import ModelService, PipelineService, ProjectService, PromptService
from rusty.ui.components import (
    STATUS_STYLES,
    create_card,
    create_danger_button,
    create_metric_card,
    create_page_header,
    create_primary_button,
    create_progress_bar,
    create_project_status_pill,
    create_secondary_button,
    create_status_pill,
    create_stepper,
)
from rusty.ui.task_runner import RunningTask, start_background_task
from rusty.ui.theme import apply_dark_theme


class NewProjectDialog:
    STEP_LABELS = [
        ("导入文件", "选择电子书文件"),
        ("TXT 拆分", "配置章节识别规则"),
        ("预览信息", "确认章节与元数据"),
        ("模型配置", "选择 AI 推理引擎"),
        ("提示词策略", "设定改写风格"),
        ("确认创建", "最终概览"),
    ]

    def __init__(
        self,
        parent,
        service: ProjectService,
        model_service: ModelService,
        prompt_service: PromptService,
    ) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QCheckBox,
            QComboBox,
            QDialog,
            QFileDialog,
            QFormLayout,
            QFrame,
            QGridLayout,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QLineEdit,
            QMessageBox,
            QPlainTextEdit,
            QPushButton,
            QRadioButton,
            QScrollArea,
            QSpinBox,
            QStackedWidget,
            QTableWidget,
            QTableWidgetItem,
            QTabWidget,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )

        self.Qt = Qt
        self.QFileDialog = QFileDialog
        self.QMessageBox = QMessageBox
        self.QTableWidgetItem = QTableWidgetItem
        self.service = service
        self.model_service = model_service
        self.prompt_service = prompt_service
        self.parsed_book: ParsedBook | None = None
        self.created_project_id: int | None = None
        self.current_step = 0

        self.dialog = QDialog(parent)
        self.dialog.setWindowTitle("新建工程")
        self.dialog.resize(1280, 780)
        apply_dark_theme(self.dialog)

        root = QHBoxLayout(self.dialog)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar, sidebar_layout = create_card(object_name="CardMuted")
        sidebar.setFixedWidth(300)
        sidebar_layout.setContentsMargins(28, 28, 28, 22)
        header = QHBoxLayout()
        icon = QLabel("✦")
        icon.setStyleSheet("font-size: 28px; font-weight: 700;")
        title = QLabel("新建项目")
        title.setObjectName("PageTitle")
        header.addWidget(icon)
        header.addWidget(title)
        header.addStretch(1)
        sidebar_layout.addLayout(header)
        self.step_widgets: list[tuple[QLabel, QLabel, QLabel]] = []
        for index, (step_title, step_subtitle) in enumerate(self.STEP_LABELS):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 10, 0, 10)
            row_layout.setSpacing(14)
            marker = QLabel(str(index + 1))
            marker.setFixedSize(38, 38)
            marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
            marker.setStyleSheet(
                "border: 1px solid #333333; border-radius: 19px; color: #6b7280; background-color: #1d1d1d;"
            )
            text_wrap = QVBoxLayout()
            title_label = QLabel(step_title)
            title_label.setStyleSheet("font-size: 16px; font-weight: 700; color: #6b7280;")
            subtitle_label = QLabel(step_subtitle)
            subtitle_label.setObjectName("SubtleText")
            text_wrap.addWidget(title_label)
            text_wrap.addWidget(subtitle_label)
            row_layout.addWidget(marker, 0, Qt.AlignmentFlag.AlignTop)
            row_layout.addLayout(text_wrap, 1)
            sidebar_layout.addWidget(row)
            self.step_widgets.append((marker, title_label, subtitle_label))
        sidebar_layout.addStretch(1)
        self.cancel_button = create_secondary_button("取消创建")
        sidebar_layout.addWidget(self.cancel_button, 0, Qt.AlignmentFlag.AlignLeft)
        root.addWidget(sidebar)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(24, 24, 24, 0)
        content_layout.setSpacing(18)
        root.addLayout(content_layout, 1)

        self.step_stack = QStackedWidget()
        content_layout.addWidget(self.step_stack, 1)

        self.file_edit = QLineEdit()
        self.file_edit.setReadOnly(True)
        self.workspace_edit = QLineEdit()
        self.workspace_edit.setPlaceholderText("选择工作目录...")
        self.project_name_edit = QLineEdit()
        self.summary_label = QLabel("点击或拖拽文件到此处")
        self.summary_label.setObjectName("SubtleText")
        self.file_button = create_secondary_button("选择文件")
        self.workspace_button = create_secondary_button("浏览")
        self.preview_button = create_secondary_button("预览")

        self.rule_simple_radio = QRadioButton("简易规则")
        self.rule_regex_radio = QRadioButton("正则表达式")
        self.rule_line_start_check = QCheckBox("行首标识")
        self.rule_simple_radio.setChecked(True)
        self.rule_line_start_check.setChecked(True)
        self.rule_prefix_combo = QComboBox()
        self.rule_prefix_combo.addItems(["第", "混合型数字"])
        self.rule_suffix_combo = QComboBox()
        self.rule_suffix_combo.addItems(["[章回卷节集部]", "章", "卷"])
        self.rule_extra_edit = QLineEdit(r"\s*(序言|序卷|序[1-9]|序曲|楔子|前言|后记|尾声|番外|最终章)")
        self.rule_regex_edit = QLineEdit(r"^\s*(\d+)\s+(.+)$")
        self.chapter_list = QTableWidget(0, 3)
        self.chapter_list.setHorizontalHeaderLabels(["#", "章节标题", "行号"])
        self.chapter_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.chapter_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.chapter_list.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.chapter_list.verticalHeader().setVisible(False)
        self.chapter_preview_label = QLabel("识别到 0 个章节")
        self.chapter_preview_label.setStyleSheet("font-size: 18px; font-weight: 700;")

        self.metadata_title = QLabel("未解析")
        self.metadata_title.setStyleSheet("font-size: 24px; font-weight: 700;")
        self.metadata_author = QLabel("未知")
        self.metadata_language = QLabel("未知")
        self.metadata_encoding = QLabel("未知")
        self.metadata_chapters = QLabel("0")
        self.metadata_words = QLabel("0")
        self.source_format_badge = create_status_pill("TXT", "#3b82f6")

        self.model_combo = QComboBox()
        self.model_detail = QTextEdit()
        self.model_detail.setReadOnly(True)
        self.model_test_button = create_secondary_button("测试连接")
        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 30)
        self.concurrency_spin.setValue(3)
        self.target_chars_spin = QSpinBox()
        self.target_chars_spin.setRange(1000, 20000)
        self.target_chars_spin.setValue(4000)

        self.template_combo = QComboBox()
        self.prompt_tabs = QTabWidget()
        self.prompt_global_edit = QPlainTextEdit()
        self.prompt_scene_edit = QPlainTextEdit()
        self.prompt_rewrite_edit = QPlainTextEdit()
        self.prompt_project_edit = QPlainTextEdit()
        for editor in (
            self.prompt_global_edit,
            self.prompt_scene_edit,
            self.prompt_rewrite_edit,
            self.prompt_project_edit,
        ):
            editor.setReadOnly(True)

        self.confirm_summary = QTextEdit()
        self.confirm_summary.setReadOnly(True)
        self.create_button = create_primary_button("创建工程")

        self._build_step_one()
        self._build_step_two()
        self._build_step_three()
        self._build_step_four()
        self._build_step_five()
        self._build_step_six()

        footer, footer_layout = create_card(layout_direction="horizontal", object_name="CardMuted")
        footer_layout.setContentsMargins(18, 14, 18, 14)
        self.back_button = create_secondary_button("上一步")
        self.next_button = create_primary_button("下一步")
        self.next_hint_label = QLabel("Enter 快速继续")
        self.next_hint_label.setObjectName("SubtleText")
        footer_layout.addWidget(self.back_button)
        footer_layout.addStretch(1)
        footer_layout.addWidget(self.next_hint_label)
        footer_layout.addWidget(self.next_button)
        content_layout.addWidget(footer)

        self.file_button.clicked.connect(self.choose_file)
        self.workspace_button.clicked.connect(self.choose_workspace)
        self.preview_button.clicked.connect(self.preview)
        self.cancel_button.clicked.connect(self.dialog.reject)
        self.back_button.clicked.connect(self.go_previous)
        self.next_button.clicked.connect(self.go_next)
        self.create_button.clicked.connect(self.create_project)
        self.model_combo.currentIndexChanged.connect(self.update_model_details)
        self.model_test_button.clicked.connect(self.test_model_connection)
        self.template_combo.currentIndexChanged.connect(self.update_template_preview)

        self.load_models()
        self.load_templates()
        self.refresh_step()

    def _scrollable(self, widget):
        from PySide6.QtWidgets import QFrame, QScrollArea

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(widget)
        return scroll

    def _build_step_one(self) -> None:
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(18)
        layout.addWidget(create_page_header("上传您的电子书", "支持 TXT / EPUB / DOCX，工作目录可选。"))
        upload_card, upload_layout = create_card(object_name="Card")
        icon = QLabel("⤴")
        icon.setAlignment(self.Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 42px;")
        upload_title = QLabel("点击或拖拽文件到此处")
        upload_title.setAlignment(self.Qt.AlignmentFlag.AlignCenter)
        upload_title.setStyleSheet("font-size: 20px; font-weight: 700;")
        upload_hint = QLabel("最大支持 50MB")
        upload_hint.setAlignment(self.Qt.AlignmentFlag.AlignCenter)
        upload_hint.setObjectName("SubtleText")
        file_row = QHBoxLayout()
        file_row.addWidget(self.file_edit, 1)
        file_row.addWidget(self.file_button)
        upload_layout.addWidget(icon)
        upload_layout.addWidget(upload_title)
        upload_layout.addWidget(upload_hint)
        upload_layout.addLayout(file_row)
        upload_layout.addWidget(self.summary_label, 0, self.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(upload_card)
        workspace_card, workspace_layout = create_card(object_name="Card")
        workspace_layout.addWidget(QLabel("工作目录"))
        workspace_row = QHBoxLayout()
        workspace_row.addWidget(self.workspace_edit, 1)
        workspace_row.addWidget(self.workspace_button)
        workspace_layout.addLayout(workspace_row)
        layout.addWidget(workspace_card)
        layout.addStretch(1)
        self.step_stack.addWidget(self._scrollable(page))

    def _build_step_two(self) -> None:
        from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(18)
        layout.addWidget(create_page_header("配置章节拆分规则", "TXT 可配置拆分规则；EPUB / DOCX 可直接预览章节结构。"))
        rule_card, rule_layout = create_card(object_name="Card")
        form = QFormLayout()
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.rule_simple_radio)
        mode_row.addWidget(self.rule_regex_radio)
        mode_row.addWidget(self.rule_line_start_check)
        mode_row.addStretch(1)
        form.addRow("识别模式", mode_row)
        simple_row = QHBoxLayout()
        simple_row.addWidget(self.rule_prefix_combo)
        simple_row.addWidget(self.rule_suffix_combo)
        form.addRow("简易规则", simple_row)
        form.addRow("附加规则", self.rule_extra_edit)
        form.addRow("正则表达式", self.rule_regex_edit)
        rule_layout.addLayout(form)
        note = QLabel("说明：本轮保留现有解析器结果，这些规则控件先作为 UI 与后续扩展入口。")
        note.setObjectName("SubtleText")
        note.setWordWrap(True)
        rule_layout.addWidget(note)
        layout.addWidget(rule_card)
        preview_card, preview_layout = create_card(object_name="Card")
        top_row = QHBoxLayout()
        top_row.addWidget(self.chapter_preview_label)
        top_row.addStretch(1)
        top_row.addWidget(self.preview_button)
        preview_layout.addLayout(top_row)
        preview_layout.addWidget(self.chapter_list)
        layout.addWidget(preview_card, 1)
        self.step_stack.addWidget(self._scrollable(page))

    def _build_step_three(self) -> None:
        from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(18)
        layout.addWidget(create_page_header("解析完成", "确认章节与元数据，可在此调整项目名称。"))
        row = QHBoxLayout()
        left_card, left_layout = create_card(object_name="Card")
        cover = QLabel("TXT")
        cover.setFixedSize(180, 240)
        cover.setAlignment(self.Qt.AlignmentFlag.AlignCenter)
        cover.setStyleSheet("border: 1px solid #333333; border-radius: 14px; font-size: 38px; font-weight: 700;")
        left_layout.addWidget(self.source_format_badge, 0, self.Qt.AlignmentFlag.AlignLeft)
        left_layout.addWidget(cover, 0, self.Qt.AlignmentFlag.AlignCenter)
        row.addWidget(left_card, 0)
        right_card, right_layout = create_card(object_name="Card")
        right_layout.addWidget(self.metadata_title)
        form = QFormLayout()
        form.addRow("项目名称", self.project_name_edit)
        form.addRow("作者", self.metadata_author)
        form.addRow("语言", self.metadata_language)
        form.addRow("编码", self.metadata_encoding)
        form.addRow("总章节", self.metadata_chapters)
        form.addRow("总字数", self.metadata_words)
        right_layout.addLayout(form)
        row.addWidget(right_card, 1)
        layout.addLayout(row)
        layout.addStretch(1)
        self.step_stack.addWidget(self._scrollable(page))

    def _build_step_four(self) -> None:
        from PySide6.QtWidgets import QFormLayout, QLabel, QHBoxLayout, QVBoxLayout, QWidget

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(18)
        layout.addWidget(create_page_header("选择 AI 模型", "复用现有模型配置与连接测试逻辑。"))
        model_card, model_layout = create_card(object_name="Card")
        form = QFormLayout()
        form.addRow("模型", self.model_combo)
        form.addRow("并发处理数", self.concurrency_spin)
        form.addRow("加料字数 / 目标字数", self.target_chars_spin)
        model_layout.addLayout(form)
        model_layout.addWidget(QLabel("已选模型详情"))
        model_layout.addWidget(self.model_detail)
        model_layout.addWidget(self.model_test_button, 0, self.Qt.AlignmentFlag.AlignLeft)
        hint = QLabel("半自动与手动模式暂未接通后端，本轮保持自动模式。")
        hint.setObjectName("SubtleText")
        hint.setWordWrap(True)
        model_layout.addWidget(hint)
        layout.addWidget(model_card, 1)
        self.step_stack.addWidget(self._scrollable(page))

    def _build_step_five(self) -> None:
        from PySide6.QtWidgets import QFormLayout, QWidget, QVBoxLayout

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(18)
        layout.addWidget(create_page_header("提示词策略", "默认读取 Prompt 模板，保留完整管理入口到提示词页面。"))
        card, card_layout = create_card(object_name="Card")
        form = QFormLayout()
        form.addRow("模板", self.template_combo)
        card_layout.addLayout(form)
        self.prompt_tabs.addTab(self.prompt_global_edit, "系统破甲")
        self.prompt_tabs.addTab(self.prompt_scene_edit, "改写规则")
        self.prompt_tabs.addTab(self.prompt_rewrite_edit, "总结策略")
        self.prompt_tabs.addTab(self.prompt_project_edit, "项目覆盖")
        card_layout.addWidget(self.prompt_tabs)
        layout.addWidget(card, 1)
        self.step_stack.addWidget(self._scrollable(page))

    def _build_step_six(self) -> None:
        from PySide6.QtWidgets import QWidget, QVBoxLayout

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(18)
        layout.addWidget(create_page_header("确认创建", "最终概览。确认后沿用当前导入与建库流程。"))
        card, card_layout = create_card(object_name="Card")
        card_layout.addWidget(self.confirm_summary)
        card_layout.addWidget(self.create_button, 0, self.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(card)
        layout.addStretch(1)
        self.step_stack.addWidget(self._scrollable(page))

    def exec(self) -> int:
        return self.dialog.exec()

    def choose_file(self) -> None:
        path, _ = self.QFileDialog.getOpenFileName(
            self.dialog,
            "导入书籍",
            str(Path.home()),
            "Book files (*.txt *.epub *.docx);;Text files (*.txt);;EPUB files (*.epub);;Word files (*.docx);;All files (*)",
        )
        if not path:
            return
        self.file_edit.setText(path)
        if not self.workspace_edit.text().strip():
            self.workspace_edit.setText(str(Path(path).parent))
        self.summary_label.setText(Path(path).name)
        self.preview()

    def choose_workspace(self) -> None:
        path = self.QFileDialog.getExistingDirectory(
            self.dialog,
            "选择工作目录",
            self.workspace_edit.text() or str(Path.home()),
        )
        if path:
            self.workspace_edit.setText(path)

    def preview(self) -> None:
        path = self.file_edit.text().strip()
        if not path:
            self.QMessageBox.information(self.dialog, "预览", "请先选择源文件。")
            return
        try:
            self.parsed_book = self.service.preview_book(path)
        except Exception as exc:  # noqa: BLE001
            self.QMessageBox.critical(self.dialog, "预览失败", str(exc))
            return
        if not self.project_name_edit.text().strip():
            self.project_name_edit.setText(self.parsed_book.title)
        self.summary_label.setText(f"已载入 {Path(path).name}")
        self.chapter_preview_label.setText(f"识别到 {len(self.parsed_book.chapters)} 个章节")
        self.chapter_list.setRowCount(0)
        for chapter in self.parsed_book.chapters:
            row = self.chapter_list.rowCount()
            self.chapter_list.insertRow(row)
            self.chapter_list.setItem(row, 0, self.QTableWidgetItem(str(chapter.index)))
            self.chapter_list.setItem(row, 1, self.QTableWidgetItem(chapter.title))
            line_text = f"L{chapter.start_line}" if chapter.start_line is not None else "-"
            self.chapter_list.setItem(row, 2, self.QTableWidgetItem(line_text))
        self.update_preview_metadata()

    def update_preview_metadata(self) -> None:
        if self.parsed_book is None:
            return
        book = self.parsed_book
        self.metadata_title.setText(book.title)
        self.metadata_author.setText(book.author or "未知")
        self.metadata_language.setText(book.language or "未知")
        self.metadata_encoding.setText(book.source_encoding or "未知")
        self.metadata_chapters.setText(str(len(book.chapters)))
        self.metadata_words.setText(str(book.total_words))
        self.source_format_badge.setText(book.source_format.upper())
        self.refresh_confirmation()

    def load_models(self) -> None:
        self.model_combo.clear()
        self.models = self.model_service.list_models()
        if not self.models:
            self.model_combo.addItem("尚未配置模型，请先到模型页面添加", None)
            self.model_detail.setPlainText("尚未配置模型。")
            self.model_test_button.setEnabled(False)
            return
        self.model_test_button.setEnabled(True)
        default_model = self.model_service.get_default_model()
        for model in self.models:
            self.model_combo.addItem(model.display_name, model.id)
        selected = default_model.id if default_model is not None else self.models[0].id
        for index in range(self.model_combo.count()):
            if self.model_combo.itemData(index) == selected:
                self.model_combo.setCurrentIndex(index)
                break
        self.update_model_details()

    def update_model_details(self) -> None:
        model_id = self.model_combo.currentData()
        model = self.model_service.get_model(model_id) if model_id is not None else None
        if model is None:
            self.model_detail.setPlainText("尚未选择模型。")
            return
        self.model_detail.setPlainText(
            "\n".join(
                [
                    f"Provider：{model.provider}",
                    f"Base URL：{model.base_url}",
                    f"Model：{model.model_name}",
                    f"Temperature：{model.temperature}",
                    f"Max tokens：{model.max_tokens or 0}",
                    f"Timeout：{model.timeout_seconds}s",
                ]
            )
        )
        self.refresh_confirmation()

    def test_model_connection(self) -> None:
        model_id = self.model_combo.currentData()
        if model_id is None:
            return
        result = self.model_service.test_connection(int(model_id))
        if result.ok:
            self.QMessageBox.information(self.dialog, "测试连接", result.message)
        else:
            self.QMessageBox.warning(self.dialog, "测试连接", result.message)

    def load_templates(self) -> None:
        self.template_combo.clear()
        self.templates = self.prompt_service.list_templates()
        for template in self.templates:
            label = template.name if not template.is_default else f"{template.name}（默认）"
            self.template_combo.addItem(label, template.id)
        default_template = self.prompt_service.get_default_template()
        if default_template is not None:
            for index in range(self.template_combo.count()):
                if self.template_combo.itemData(index) == default_template.id:
                    self.template_combo.setCurrentIndex(index)
                    break
        self.update_template_preview()

    def update_template_preview(self) -> None:
        template_id = self.template_combo.currentData()
        template = self.prompt_service.get_template(template_id) if template_id is not None else None
        if template is None:
            return
        self.prompt_global_edit.setPlainText(template.global_rules)
        self.prompt_scene_edit.setPlainText(template.rewrite_rules)
        self.prompt_rewrite_edit.setPlainText(template.summary_rules)
        self.prompt_project_edit.setPlainText("项目覆盖仍保留在提示词页面中完整编辑。")
        self.refresh_confirmation()

    def validate_step(self, step: int) -> bool:
        if step == 0 and not self.file_edit.text().strip():
            self.QMessageBox.information(self.dialog, "导入文件", "未选择文件时不能继续。")
            return False
        if step in (1, 2) and self.parsed_book is None:
            self.QMessageBox.information(self.dialog, "预览", "请先完成书籍预览。")
            return False
        return True

    def go_previous(self) -> None:
        self.current_step = max(0, self.current_step - 1)
        self.refresh_step()

    def go_next(self) -> None:
        if not self.validate_step(self.current_step):
            return
        if self.current_step == len(self.STEP_LABELS) - 1:
            self.create_project()
            return
        self.current_step += 1
        self.refresh_step()

    def refresh_step(self) -> None:
        self.step_stack.setCurrentIndex(self.current_step)
        for index, (marker, title_label, subtitle_label) in enumerate(self.step_widgets):
            if index < self.current_step:
                marker.setText("✓")
                marker.setStyleSheet(
                    "border: none; border-radius: 19px; color: #ffffff; background-color: #22c55e; font-weight: 700;"
                )
                title_label.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
            elif index == self.current_step:
                marker.setText(str(index + 1))
                marker.setStyleSheet(
                    "border: 2px solid #f5f5f5; border-radius: 19px; color: #ffffff; background-color: #1d1d1d; font-weight: 700;"
                )
                title_label.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
            else:
                marker.setText(str(index + 1))
                marker.setStyleSheet(
                    "border: 1px solid #333333; border-radius: 19px; color: #6b7280; background-color: #1d1d1d;"
                )
                title_label.setStyleSheet("font-size: 16px; font-weight: 700; color: #6b7280;")
            subtitle_label.setStyleSheet(f"color: {'#9ca3af' if index <= self.current_step else '#555555'};")
        self.back_button.setEnabled(self.current_step > 0)
        self.next_button.setText("创建工程" if self.current_step == len(self.STEP_LABELS) - 1 else "下一步")
        self.refresh_confirmation()

    def refresh_confirmation(self) -> None:
        if self.parsed_book is None:
            self.confirm_summary.setPlainText("请选择电子书并完成预览。")
            return
        self.confirm_summary.setPlainText(
            "\n".join(
                [
                    f"文件：{self.parsed_book.source_path.name}",
                    f"项目名称：{self.project_name_edit.text().strip() or self.parsed_book.title}",
                    f"工作目录：{self.workspace_edit.text().strip() or str(self.parsed_book.source_path.parent)}",
                    f"章节数：{len(self.parsed_book.chapters)}",
                    f"模型：{self.model_combo.currentText() or '未选择'}",
                    f"Prompt 模板：{self.template_combo.currentText() or '未选择'}",
                    "处理模式：自动模式",
                    f"并发数：{self.concurrency_spin.value()}",
                ]
            )
        )

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
            self.service.update_project_settings(
                self.created_project_id,
                model_id=self.model_combo.currentData(),
                prompt_template_id=self.template_combo.currentData(),
                processing_mode="auto",
                concurrency=self.concurrency_spin.value(),
                target_word_count=self.target_chars_spin.value(),
                min_expansion_ratio=None,
            )
        except Exception as exc:  # noqa: BLE001
            self.QMessageBox.critical(self.dialog, "创建失败", str(exc))
            return
        self.dialog.accept()


class RustyMainWindow:
    STAGES = ["书籍拆分", "内容总结", "识别待处理", "AI 改写", "合并输出"]

    def __init__(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QAbstractItemView,
            QCheckBox,
            QComboBox,
            QDoubleSpinBox,
            QFileDialog,
            QFormLayout,
            QFrame,
            QGridLayout,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QLineEdit,
            QListWidget,
            QListWidgetItem,
            QMainWindow,
            QMessageBox,
            QPlainTextEdit,
            QPushButton,
            QSpinBox,
            QStackedWidget,
            QTableWidget,
            QTableWidgetItem,
            QTextEdit,
            QVBoxLayout,
            QWidget,
            QTabWidget,
        )
        globals().update(
            {
                "QAbstractItemView": QAbstractItemView,
                "QCheckBox": QCheckBox,
                "QComboBox": QComboBox,
                "QDoubleSpinBox": QDoubleSpinBox,
                "QFileDialog": QFileDialog,
                "QFormLayout": QFormLayout,
                "QFrame": QFrame,
                "QGridLayout": QGridLayout,
                "QHBoxLayout": QHBoxLayout,
                "QHeaderView": QHeaderView,
                "QLabel": QLabel,
                "QLineEdit": QLineEdit,
                "QListWidget": QListWidget,
                "QListWidgetItem": QListWidgetItem,
                "QMainWindow": QMainWindow,
                "QMessageBox": QMessageBox,
                "QPlainTextEdit": QPlainTextEdit,
                "QPushButton": QPushButton,
                "QSpinBox": QSpinBox,
                "QStackedWidget": QStackedWidget,
                "QTableWidget": QTableWidget,
                "QTableWidgetItem": QTableWidgetItem,
                "QTextEdit": QTextEdit,
                "QVBoxLayout": QVBoxLayout,
                "QWidget": QWidget,
                "QTabWidget": QTabWidget,
            }
        )

        self.Qt = Qt
        self.QFileDialog = QFileDialog
        self.QListWidgetItem = QListWidgetItem
        self.QMessageBox = QMessageBox
        self.QTableWidgetItem = QTableWidgetItem
        self.service = ProjectService()
        self.model_service = ModelService(self.service.database_path)
        self.prompt_service = PromptService(self.service.database_path)
        self.pipeline_service = PipelineService(self.service.database_path)
        self.projects: list[ProjectSummary] = []
        self.chapters: list[ChapterRecord] = []
        self.current_project_id: int | None = None
        self.current_model_id: int | None = None
        self.current_template_id: int | None = None
        self.current_workspace_stage = 0
        self.running_tasks: list[RunningTask] = []

        self.window = QMainWindow()
        self.window.setWindowTitle("Rusty")
        self.window.resize(1500, 900)
        apply_dark_theme(self.window)

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        nav = QWidget()
        nav.setObjectName("NavBar")
        nav.setFixedWidth(56)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(8, 10, 8, 10)
        nav_layout.setSpacing(12)
        logo = QLabel("R")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("font-size: 22px; font-weight: 700; color: #ffffff;")
        nav_layout.addWidget(logo)
        self.workbench_nav = self._create_nav_button("◫", "工作台")
        self.preview_nav = self._create_nav_button("⌘", "项目工作区")
        self.models_nav = self._create_nav_button("⚙", "模型")
        self.prompts_nav = self._create_nav_button("✎", "提示词")
        self.ai_nav = self._create_nav_button("⇄", "AI 流水线")
        for button in (self.workbench_nav, self.preview_nav, self.models_nav, self.prompts_nav, self.ai_nav):
            nav_layout.addWidget(button)
        nav_layout.addStretch(1)
        root_layout.addWidget(nav, 0)

        self.stack = QStackedWidget()
        root_layout.addWidget(self.stack, 1)
        self.workbench_page = self._build_workbench_page()
        self.preview_page = self._build_preview_page()
        self.models_page = self._build_models_page()
        self.prompts_page = self._build_prompts_page()
        self.ai_page = self._build_ai_page()
        self.stack.addWidget(self.workbench_page)
        self.stack.addWidget(self.preview_page)
        self.stack.addWidget(self.models_page)
        self.stack.addWidget(self.prompts_page)
        self.stack.addWidget(self.ai_page)
        self.window.setCentralWidget(root)

        self.workbench_nav.clicked.connect(lambda: self.show_page(self.workbench_page, self.workbench_nav))
        self.preview_nav.clicked.connect(lambda: self.show_page(self.preview_page, self.preview_nav))
        self.models_nav.clicked.connect(lambda: self.show_page(self.models_page, self.models_nav))
        self.prompts_nav.clicked.connect(lambda: self.show_page(self.prompts_page, self.prompts_nav))
        self.ai_nav.clicked.connect(lambda: self.show_page(self.ai_page, self.ai_nav))
        self.new_project_button.clicked.connect(self.new_project)
        self.open_preview_button.clicked.connect(self.open_selected_project_preview)
        self.delete_project_button.clicked.connect(self.delete_selected_project)
        self.export_txt_button.clicked.connect(self.export_txt)
        self.export_epub_button.clicked.connect(self.export_epub)
        self.refresh_button.clicked.connect(self.load_projects)
        self.preview_export_txt_button.clicked.connect(self.export_txt)
        self.preview_export_epub_button.clicked.connect(self.export_epub)
        self.save_rewrite_button.clicked.connect(self.save_selected_chapter_rewrite)
        self.clear_rewrite_button.clicked.connect(self.clear_selected_chapter_rewrite)
        self.project_table.itemSelectionChanged.connect(self.project_table_selection_changed)
        self.project_list.currentItemChanged.connect(self.project_list_selection_changed)
        self.project_list.itemDoubleClicked.connect(lambda _: self.open_selected_project_preview())
        self.chapter_list.currentItemChanged.connect(self.chapter_selected)
        self.model_table.itemSelectionChanged.connect(self.model_selection_changed)
        self.model_list.currentRowChanged.connect(self.model_list_selection_changed)
        self.model_new_button.clicked.connect(self.clear_model_form)
        self.model_save_button.clicked.connect(self.save_model)
        self.model_delete_button.clicked.connect(self.delete_model)
        self.model_test_button.clicked.connect(self.test_model_connection)
        self.template_table.itemSelectionChanged.connect(self.template_selection_changed)
        self.template_list.currentRowChanged.connect(self.template_list_selection_changed)
        self.template_new_button.clicked.connect(self.clear_template_form)
        self.template_save_button.clicked.connect(self.save_template)
        self.template_delete_button.clicked.connect(self.delete_template)
        self.project_prompt_save_button.clicked.connect(self.save_project_prompt)
        self.ai_save_settings_button.clicked.connect(self.save_ai_project_settings)
        self.ai_run_project_button.clicked.connect(self.run_project_pipeline)
        self.ai_pause_project_button.clicked.connect(self.pause_current_project)
        self.ai_summary_button.clicked.connect(self.summarize_selected_chapter)
        self.ai_scene_button.clicked.connect(self.detect_selected_chapter_scene)
        self.ai_rewrite_button.clicked.connect(self.rewrite_selected_chapter)
        self.ai_retry_stage_button.clicked.connect(self.retry_selected_chapter_stage)
        self.project_search_edit.textChanged.connect(self.refresh_project_cards)
        self.project_filter_combo.currentIndexChanged.connect(self.refresh_project_cards)
        self.project_sort_combo.currentIndexChanged.connect(self.refresh_project_cards)
        for index, button in enumerate(self.workspace_step_buttons):
            button.clicked.connect(lambda checked=False, i=index: self.set_workspace_stage(i))
        self.workspace_continue_button.clicked.connect(self.continue_current_stage)
        self.chapter_top_button.clicked.connect(lambda: self.chapter_list.scrollToTop())
        self.chapter_bottom_button.clicked.connect(lambda: self.chapter_list.scrollToBottom())

        self.load_projects()
        self.load_models()
        self.load_templates()
        self.show_page(self.workbench_page, self.workbench_nav)

    def _create_nav_button(self, text: str, tooltip: str):
        from PySide6.QtWidgets import QPushButton

        button = QPushButton(text)
        button.setObjectName("NavButton")
        button.setToolTip(tooltip)
        button.setCheckable(True)
        return button

    def _wrap_page(self, title: str, subtitle: str, action=None):
        from PySide6.QtWidgets import QVBoxLayout, QWidget

        page = QWidget()
        page.setObjectName("PageRoot")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(create_page_header(title, subtitle, action))
        return page, layout

    def _build_workbench_page(self):
        from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QTableWidget, QVBoxLayout

        self.new_project_button = create_primary_button("+ 新建工程")
        page, layout = self._wrap_page("工作台", "共 0 个项目 · 快速定位与管理", self.new_project_button)
        body = QHBoxLayout()
        body.setSpacing(18)

        left_card, left_layout = create_card(object_name="Card")
        left_card.setFixedWidth(320)
        self.project_search_edit = QLineEdit()
        self.project_search_edit.setPlaceholderText("搜索项目名称...")
        filter_row = QHBoxLayout()
        self.project_filter_combo = QComboBox()
        self.project_filter_combo.addItems(["全部", "进行中", "已完成", "待启动", "已暂停"])
        self.project_sort_combo = QComboBox()
        self.project_sort_combo.addItems(["最近更新", "创建时间", "项目名称"])
        filter_row.addWidget(self.project_filter_combo)
        filter_row.addWidget(self.project_sort_combo)
        self.project_list = QListWidget()
        left_layout.addWidget(self.project_search_edit)
        left_layout.addLayout(filter_row)
        left_layout.addWidget(self.project_list, 1)
        body.addWidget(left_card, 0)

        right_col = QVBoxLayout()
        right_col.setSpacing(16)
        self.project_detail_card, detail_layout = create_card(object_name="Card")
        top_row = QHBoxLayout()
        self.project_detail_cover = QLabel("TXT")
        self.project_detail_cover.setFixedSize(180, 250)
        self.project_detail_cover.setAlignment(self.Qt.AlignmentFlag.AlignCenter)
        self.project_detail_cover.setStyleSheet(
            "border: 1px solid #333333; border-radius: 14px; font-size: 38px; font-weight: 700;"
        )
        meta_layout = QVBoxLayout()
        pills = QHBoxLayout()
        self.project_detail_status_container = QHBoxLayout()
        self.project_detail_updated_container = QHBoxLayout()
        self.project_detail_status_label = create_status_pill("Empty", "#9ca3af")
        self.project_detail_updated_label = create_status_pill("-", "#9ca3af")
        self.project_detail_status_container.addWidget(self.project_detail_status_label)
        self.project_detail_updated_container.addWidget(self.project_detail_updated_label)
        pills.addLayout(self.project_detail_status_container)
        pills.addLayout(self.project_detail_updated_container)
        pills.addStretch(1)
        self.project_detail_title = QLabel("还没有项目")
        self.project_detail_title.setStyleSheet("font-size: 34px; font-weight: 700;")
        self.project_detail_description = QLabel("导入 TXT / EPUB / DOCX 创建第一个改写工程")
        self.project_detail_description.setObjectName("SubtleText")
        self.project_detail_description.setWordWrap(True)
        metrics_row = QHBoxLayout()
        self.project_detail_metric_cards = [
            create_metric_card("章节", "--"),
            create_metric_card("字数", "--"),
            create_metric_card("阶段", "--"),
            create_metric_card("完成度", "--"),
        ]
        self.metric_chapters_value = self.project_detail_metric_cards[0].layout().itemAt(1).widget()
        self.metric_words_value = self.project_detail_metric_cards[1].layout().itemAt(1).widget()
        self.metric_stage_value = self.project_detail_metric_cards[2].layout().itemAt(1).widget()
        self.metric_progress_value = self.project_detail_metric_cards[3].layout().itemAt(1).widget()
        for card in self.project_detail_metric_cards:
            metrics_row.addWidget(card, 1)
        action_row = QHBoxLayout()
        self.open_preview_button = create_primary_button("进入工作台")
        self.edit_project_button = create_secondary_button("编辑")
        self.delete_project_button = create_danger_button("删除")
        action_row.addWidget(self.open_preview_button)
        action_row.addWidget(self.edit_project_button)
        action_row.addWidget(self.delete_project_button)
        action_row.addStretch(1)
        meta_layout.addLayout(pills)
        meta_layout.addWidget(self.project_detail_title)
        meta_layout.addWidget(self.project_detail_description)
        meta_layout.addLayout(metrics_row)
        meta_layout.addStretch(1)
        meta_layout.addLayout(action_row)
        top_row.addWidget(self.project_detail_cover)
        top_row.addLayout(meta_layout, 1)
        detail_layout.addLayout(top_row)
        right_col.addWidget(self.project_detail_card, 1)

        tip_card, tip_layout = create_card(object_name="CardMuted")
        self.status_label = QLabel("小技巧：双击左侧任意项目可直接进入项目工作区；筛选/排序会自动保持有效选择。")
        self.status_label.setObjectName("SubtleText")
        self.status_label.setWordWrap(True)
        tip_layout.addWidget(self.status_label)
        right_col.addWidget(tip_card)
        body.addLayout(right_col, 1)
        layout.addLayout(body, 1)

        footer = QHBoxLayout()
        self.refresh_button = create_secondary_button("刷新")
        self.export_txt_button = create_secondary_button("导出 TXT")
        self.export_epub_button = create_secondary_button("导出 EPUB")
        footer.addWidget(self.refresh_button)
        footer.addWidget(self.export_txt_button)
        footer.addWidget(self.export_epub_button)
        footer.addStretch(1)
        layout.addLayout(footer)

        self.project_table = QTableWidget(0, 9)
        self.project_table.setHorizontalHeaderLabels(
            ["ID", "Name", "Book", "Format", "Chapters", "Chars", "Progress", "Status", "Updated"]
        )
        self.project_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.project_table.setVisible(False)
        layout.addWidget(self.project_table)
        return page

    def _build_preview_page(self):
        from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QListWidget, QTextEdit, QVBoxLayout

        page, layout = self._wrap_page("项目工作区", "章节导航、总结、识别、改写与导出集中在一个项目级工作区。")
        header_card, header_layout = create_card(object_name="Card")
        top_row = QHBoxLayout()
        self.preview_project_label = QLabel("未选择项目")
        self.preview_project_label.setStyleSheet("font-size: 28px; font-weight: 700;")
        self.preview_status_container = QHBoxLayout()
        top_row.addWidget(self.preview_project_label)
        top_row.addLayout(self.preview_status_container)
        top_row.addStretch(1)
        self.workspace_settings_button = create_secondary_button("设置")
        top_row.addWidget(self.workspace_settings_button)
        header_layout.addLayout(top_row)
        self.workspace_stepper, self.workspace_step_buttons = create_stepper(self.STAGES)
        header_layout.addWidget(self.workspace_stepper)
        layout.addWidget(header_card)

        body = QHBoxLayout()
        body.setSpacing(18)
        chapter_card, chapter_layout = create_card(object_name="Card")
        chapter_card.setFixedWidth(300)
        chapter_title = QLabel("章节导航")
        chapter_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.chapter_nav_summary = QLabel("0 章 · 0 已完成")
        self.chapter_nav_summary.setObjectName("SubtleText")
        chapter_layout.addWidget(chapter_title)
        chapter_layout.addWidget(self.chapter_nav_summary)
        self.chapter_list = QListWidget()
        chapter_layout.addWidget(self.chapter_list, 1)
        chapter_footer = QHBoxLayout()
        self.chapter_top_button = create_secondary_button("回到顶部")
        self.chapter_bottom_button = create_secondary_button("回到底部")
        chapter_footer.addWidget(self.chapter_top_button)
        chapter_footer.addWidget(self.chapter_bottom_button)
        chapter_layout.addLayout(chapter_footer)
        body.addWidget(chapter_card, 0)

        center_layout = QVBoxLayout()
        self.workspace_content_stack = QStackedWidget()
        self.workspace_content_stack.addWidget(self._build_stage_split_view())
        self.workspace_content_stack.addWidget(self._build_stage_summary_view())
        self.workspace_content_stack.addWidget(self._build_stage_scene_view())
        self.workspace_content_stack.addWidget(self._build_stage_rewrite_view())
        self.workspace_content_stack.addWidget(self._build_stage_export_view())
        center_layout.addWidget(self.workspace_content_stack, 1)
        body.addLayout(center_layout, 1)

        stats_layout = QVBoxLayout()
        stats_layout.setSpacing(16)
        stats_card, stats_card_layout = create_card(object_name="Card")
        stats_card_layout.addWidget(QLabel("书籍统计 / 总结统计"))
        grid = QGridLayout()
        self.workspace_total_words_label = QLabel("0")
        self.workspace_total_chapters_label = QLabel("0")
        self.workspace_failed_label = QLabel("0")
        self.workspace_completed_label = QLabel("0")
        for label in (
            self.workspace_total_words_label,
            self.workspace_total_chapters_label,
            self.workspace_failed_label,
            self.workspace_completed_label,
        ):
            label.setStyleSheet("font-size: 22px; font-weight: 700;")
        grid.addWidget(QLabel("总字数"), 0, 0)
        grid.addWidget(self.workspace_total_words_label, 0, 1)
        grid.addWidget(QLabel("章节数"), 1, 0)
        grid.addWidget(self.workspace_total_chapters_label, 1, 1)
        grid.addWidget(QLabel("失败数"), 2, 0)
        grid.addWidget(self.workspace_failed_label, 2, 1)
        grid.addWidget(QLabel("已完成数"), 3, 0)
        grid.addWidget(self.workspace_completed_label, 3, 1)
        stats_card_layout.addLayout(grid)
        self.workspace_total_progress = create_progress_bar(0, 1)
        stats_card_layout.addWidget(self.workspace_total_progress)
        stats_layout.addWidget(stats_card)

        progress_card, progress_card_layout = create_card(object_name="Card")
        progress_card_layout.addWidget(QLabel("当前阶段进度"))
        self.workspace_stage_progress = create_progress_bar(0, 1)
        self.workspace_stage_progress_label = QLabel("0 / 0")
        self.workspace_continue_button = create_primary_button("继续")
        progress_card_layout.addWidget(self.workspace_stage_progress)
        progress_card_layout.addWidget(self.workspace_stage_progress_label)
        progress_card_layout.addWidget(self.workspace_continue_button, 0, self.Qt.AlignmentFlag.AlignLeft)
        stats_layout.addWidget(progress_card)

        export_card, export_card_layout = create_card(object_name="Card")
        export_card_layout.addWidget(QLabel("导出"))
        self.export_summary_button = create_secondary_button("导出总结文档")
        self.preview_export_txt_button = create_secondary_button("导出 TXT")
        self.preview_export_epub_button = create_secondary_button("导出 EPUB")
        export_card_layout.addWidget(self.export_summary_button)
        export_card_layout.addWidget(self.preview_export_txt_button)
        export_card_layout.addWidget(self.preview_export_epub_button)
        stats_layout.addWidget(export_card)
        stats_layout.addStretch(1)
        body.addLayout(stats_layout, 0)
        layout.addLayout(body, 1)
        return page

    def _build_stage_split_view(self):
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QTextEdit, QVBoxLayout, QWidget

        page = QWidget()
        layout = QVBoxLayout(page)
        card, card_layout = create_card(object_name="Card")
        top_row = QHBoxLayout()
        self.preview_title = QLabel("请选择章节")
        self.preview_title.setStyleSheet("font-size: 22px; font-weight: 700;")
        self.preview_meta = QLabel("")
        self.preview_meta.setObjectName("SubtleText")
        self.ignore_chapter_button = create_secondary_button("忽略此章节")
        top_row.addWidget(self.preview_title)
        top_row.addStretch(1)
        top_row.addWidget(self.preview_meta)
        top_row.addWidget(self.ignore_chapter_button)
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        card_layout.addLayout(top_row)
        card_layout.addWidget(self.preview_text, 1)
        layout.addWidget(card)
        return page

    def _build_stage_summary_view(self):
        from PySide6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

        page = QWidget()
        layout = QVBoxLayout(page)
        self.summary_output_text = QTextEdit()
        self.summary_output_text.setReadOnly(True)
        self.summary_output_text.setPlaceholderText("暂无章节总结，请点击生成总结。")
        self.summary_people_text = QTextEdit()
        self.summary_people_text.setReadOnly(True)
        self.summary_people_text.setPlaceholderText("暂无登场人物摘要。")
        self.summary_events_text = QTextEdit()
        self.summary_events_text.setReadOnly(True)
        self.summary_events_text.setPlaceholderText("暂无关键事件摘要。")
        for title, editor in (
            ("剧情概要", self.summary_output_text),
            ("登场人物", self.summary_people_text),
            ("关键事件", self.summary_events_text),
        ):
            card, card_layout = create_card(object_name="Card")
            card_layout.addWidget(QLabel(title))
            card_layout.addWidget(editor)
            layout.addWidget(card)
        return page

    def _build_stage_scene_view(self):
        from PySide6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

        page = QWidget()
        layout = QVBoxLayout(page)
        card, card_layout = create_card(object_name="Card")
        card_layout.addWidget(QLabel("场景识别结果"))
        self.scene_result_text = QTextEdit()
        self.scene_result_text.setReadOnly(True)
        self.scene_result_text.setPlaceholderText("暂无场景识别结果。")
        card_layout.addWidget(self.scene_result_text)
        layout.addWidget(card)
        return page

    def _build_stage_rewrite_view(self):
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QTextEdit, QVBoxLayout, QWidget

        page = QWidget()
        layout = QVBoxLayout(page)
        buttons = QHBoxLayout()
        self.generate_rewrite_button = create_primary_button("生成改写")
        self.retry_rewrite_button = create_secondary_button("重试阶段")
        self.save_rewrite_button = create_secondary_button("保存改写")
        self.clear_rewrite_button = create_secondary_button("清空改写")
        buttons.addWidget(self.generate_rewrite_button)
        buttons.addWidget(self.save_rewrite_button)
        buttons.addWidget(self.clear_rewrite_button)
        buttons.addWidget(self.retry_rewrite_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        row = QHBoxLayout()
        left_card, left_layout = create_card(object_name="Card")
        left_layout.addWidget(QLabel("原文"))
        self.rewrite_original_text = QTextEdit()
        self.rewrite_original_text.setReadOnly(True)
        left_layout.addWidget(self.rewrite_original_text)
        right_card, right_layout = create_card(object_name="Card")
        right_layout.addWidget(QLabel("改写文"))
        self.rewrite_text = QTextEdit()
        right_layout.addWidget(self.rewrite_text)
        row.addWidget(left_card, 1)
        row.addWidget(right_card, 1)
        layout.addLayout(row, 1)
        self.generate_rewrite_button.clicked.connect(self.rewrite_selected_chapter)
        self.retry_rewrite_button.clicked.connect(self.retry_selected_chapter_stage)
        return page

    def _build_stage_export_view(self):
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QTextEdit, QVBoxLayout, QWidget

        page = QWidget()
        layout = QVBoxLayout(page)
        card, card_layout = create_card(object_name="Card")
        actions = QHBoxLayout()
        self.preview_export_txt_button = create_secondary_button("导出 TXT")
        self.preview_export_epub_button = create_secondary_button("导出 EPUB")
        actions.addWidget(self.preview_export_txt_button)
        actions.addWidget(self.preview_export_epub_button)
        actions.addStretch(1)
        card_layout.addLayout(actions)
        card_layout.addWidget(QLabel("导出历史"))
        self.export_history_text = QTextEdit()
        self.export_history_text.setReadOnly(True)
        card_layout.addWidget(self.export_history_text)
        card_layout.addWidget(QLabel("合并文本预览"))
        self.merged_preview_text = QTextEdit()
        self.merged_preview_text.setReadOnly(True)
        card_layout.addWidget(self.merged_preview_text, 1)
        layout.addWidget(card)
        return page

    def _build_models_page(self):
        from PySide6.QtWidgets import (
            QCheckBox,
            QDoubleSpinBox,
            QFormLayout,
            QHBoxLayout,
            QListWidget,
            QLineEdit,
            QSpinBox,
            QTableWidget,
        )

        page, layout = self._wrap_page("模型管理", "管理 OpenAI-compatible API 模型配置")
        body = QHBoxLayout()
        left_card, left_layout = create_card(object_name="Card")
        left_card.setFixedWidth(320)
        self.model_list = QListWidget()
        left_layout.addWidget(self.model_list)
        body.addWidget(left_card, 0)

        right_card, right_layout = create_card(object_name="Card")
        buttons = QHBoxLayout()
        self.model_new_button = create_secondary_button("新建")
        self.model_save_button = create_primary_button("保存")
        self.model_test_button = create_secondary_button("测试连接")
        self.model_delete_button = create_danger_button("删除")
        for button in (self.model_new_button, self.model_save_button, self.model_test_button, self.model_delete_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        right_layout.addLayout(buttons)
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
        self.model_default_check = QCheckBox("默认模型")
        form.addRow("Display name", self.model_name_edit)
        form.addRow("Provider", self.model_provider_edit)
        form.addRow("Base URL", self.model_base_url_edit)
        form.addRow("Model", self.model_name_value_edit)
        form.addRow("API key", self.model_api_key_edit)
        form.addRow("Temperature", self.model_temperature_spin)
        form.addRow("Max tokens", self.model_max_tokens_spin)
        form.addRow("Timeout", self.model_timeout_spin)
        form.addRow("", self.model_default_check)
        right_layout.addLayout(form)
        body.addWidget(right_card, 1)
        layout.addLayout(body, 1)

        self.model_table = QTableWidget(0, 7)
        self.model_table.setHorizontalHeaderLabels(["ID", "Name", "Provider", "Model", "Base URL", "Default", "API Key"])
        self.model_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.model_table.setVisible(False)
        layout.addWidget(self.model_table)
        return page

    def _build_prompts_page(self):
        from PySide6.QtWidgets import (
            QCheckBox,
            QComboBox,
            QFormLayout,
            QHBoxLayout,
            QListWidget,
            QLineEdit,
            QPlainTextEdit,
            QTabWidget,
            QTableWidget,
        )

        page, layout = self._wrap_page("提示词策略", "保留模板管理和项目覆盖入口")
        body = QHBoxLayout()
        left_card, left_layout = create_card(object_name="Card")
        left_card.setFixedWidth(320)
        self.template_list = QListWidget()
        left_layout.addWidget(self.template_list)
        body.addWidget(left_card, 0)

        right_card, right_layout = create_card(object_name="Card")
        buttons = QHBoxLayout()
        self.template_new_button = create_secondary_button("新建")
        self.template_save_button = create_primary_button("保存")
        self.template_delete_button = create_danger_button("删除")
        buttons.addWidget(self.template_new_button)
        buttons.addWidget(self.template_save_button)
        buttons.addWidget(self.template_delete_button)
        buttons.addStretch(1)
        right_layout.addLayout(buttons)
        meta_form = QFormLayout()
        self.template_name_edit = QLineEdit()
        self.template_default_check = QCheckBox("默认模板")
        meta_form.addRow("模板名", self.template_name_edit)
        meta_form.addRow("", self.template_default_check)
        right_layout.addLayout(meta_form)
        self.prompt_tabs_manage = QTabWidget()
        self.global_rules_edit = QPlainTextEdit()
        self.summary_rules_edit = QPlainTextEdit()
        self.rewrite_rules_edit = QPlainTextEdit()
        self.project_prompt_text_edit = QPlainTextEdit()
        self.prompt_tabs_manage.addTab(self.global_rules_edit, "全局规则")
        self.prompt_tabs_manage.addTab(self.summary_rules_edit, "总结规则")
        self.prompt_tabs_manage.addTab(self.rewrite_rules_edit, "改写规则")
        self.prompt_tabs_manage.addTab(self.project_prompt_text_edit, "项目覆盖")
        right_layout.addWidget(self.prompt_tabs_manage, 1)
        project_form = QFormLayout()
        self.project_prompt_project_combo = QComboBox()
        self.project_prompt_key_edit = QLineEdit("global_override")
        self.project_prompt_save_button = create_secondary_button("保存项目覆盖")
        project_form.addRow("项目", self.project_prompt_project_combo)
        project_form.addRow("Prompt key", self.project_prompt_key_edit)
        project_form.addRow("", self.project_prompt_save_button)
        right_layout.addLayout(project_form)
        body.addWidget(right_card, 1)
        layout.addLayout(body, 1)

        self.template_table = QTableWidget(0, 4)
        self.template_table.setHorizontalHeaderLabels(["ID", "Name", "Version", "Default"])
        self.template_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.template_table.setVisible(False)
        layout.addWidget(self.template_table)
        return page

    def _build_ai_page(self):
        from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QSpinBox, QTextEdit

        page, layout = self._wrap_page("AI 流水线", "保留项目设置、项目级操作、章节级操作与诊断信息。")
        self.ai_status_label = QLabel("选择项目或章节后执行 AI 动作。")
        self.ai_status_label.setObjectName("SubtleText")
        layout.addWidget(self.ai_status_label)

        settings_card, settings_layout = create_card(object_name="Card")
        settings_layout.addWidget(QLabel("项目设置"))
        settings_form = QFormLayout()
        self.ai_model_combo = QComboBox()
        self.ai_template_combo = QComboBox()
        self.ai_concurrency_spin = QSpinBox()
        self.ai_concurrency_spin.setRange(1, 32)
        self.ai_concurrency_spin.setValue(1)
        self.ai_target_word_count_spin = QSpinBox()
        self.ai_target_word_count_spin.setRange(0, 10_000_000)
        self.ai_min_expansion_ratio_spin = QDoubleSpinBox()
        self.ai_min_expansion_ratio_spin.setRange(0, 20)
        self.ai_min_expansion_ratio_spin.setSingleStep(0.1)
        self.ai_min_expansion_ratio_spin.setDecimals(2)
        self.ai_save_settings_button = create_primary_button("保存项目 AI 设置")
        settings_form.addRow("Project model", self.ai_model_combo)
        settings_form.addRow("Prompt template", self.ai_template_combo)
        settings_form.addRow("Concurrency", self.ai_concurrency_spin)
        settings_form.addRow("Target chars", self.ai_target_word_count_spin)
        settings_form.addRow("Minimum expansion ratio", self.ai_min_expansion_ratio_spin)
        settings_form.addRow("", self.ai_save_settings_button)
        settings_layout.addLayout(settings_form)
        layout.addWidget(settings_card)

        project_card, project_layout = create_card(object_name="Card")
        project_layout.addWidget(QLabel("项目级操作"))
        self.ai_run_project_button = create_primary_button("运行项目流水线")
        self.ai_pause_project_button = create_secondary_button("暂停项目")
        project_layout.addWidget(self.ai_run_project_button)
        project_layout.addWidget(self.ai_pause_project_button)
        layout.addWidget(project_card)

        chapter_card, chapter_layout = create_card(object_name="Card")
        chapter_layout.addWidget(QLabel("章节级操作"))
        self.ai_summary_button = create_secondary_button("总结章节")
        self.ai_scene_button = create_secondary_button("识别场景")
        self.ai_rewrite_button = create_secondary_button("改写章节")
        self.ai_retry_stage_combo = QComboBox()
        self.ai_retry_stage_combo.addItem("总结", "summary")
        self.ai_retry_stage_combo.addItem("场景识别", "scene_detection")
        self.ai_retry_stage_combo.addItem("改写", "rewrite")
        self.ai_retry_stage_button = create_secondary_button("重试阶段")
        for widget in (self.ai_summary_button, self.ai_scene_button, self.ai_rewrite_button, self.ai_retry_stage_combo, self.ai_retry_stage_button):
            chapter_layout.addWidget(widget)
        layout.addWidget(chapter_card)

        output_card, output_layout = create_card(object_name="Card")
        output_layout.addWidget(QLabel("AI 输出"))
        self.ai_output_text = QTextEdit()
        self.ai_output_text.setReadOnly(True)
        output_layout.addWidget(self.ai_output_text)
        layout.addWidget(output_card)

        diagnostics_card, diagnostics_layout = create_card(object_name="Card")
        diagnostics_layout.addWidget(QLabel("诊断信息"))
        self.ai_diagnostics_text = QTextEdit()
        self.ai_diagnostics_text.setReadOnly(True)
        diagnostics_layout.addWidget(self.ai_diagnostics_text)
        layout.addWidget(diagnostics_card, 1)
        return page

    def show_page(self, page, active_button=None) -> None:
        self.stack.setCurrentWidget(page)
        for button in (self.workbench_nav, self.preview_nav, self.models_nav, self.prompts_nav, self.ai_nav):
            button.setChecked(button is active_button)

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
                self.project_progress_text(project),
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
        self.refresh_project_cards()
        if self.projects and self.current_project_id is None:
            self.current_project_id = self.projects[0].id
            self.project_table.selectRow(0)
        elif self.current_project_id is not None:
            self.select_project_row(self.current_project_id)
        else:
            self.clear_preview()
        self.load_project_ai_settings(self.current_project_id)

    def load_models(self) -> None:
        selected_model_id = self.ai_model_combo.currentData()
        self.ai_model_combo.clear()
        self.ai_model_combo.addItem("Use default model", None)
        self.model_table.setRowCount(0)
        self.model_list.clear()
        for model in self.model_service.list_models():
            self.ai_model_combo.addItem(model.display_name, model.id)
            self.model_list.addItem(f"{model.display_name}\n{model.provider} · {model.model_name}")
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
        self.select_combo_value(self.ai_model_combo, selected_model_id)

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

    def test_model_connection(self) -> None:
        if self.current_model_id is None:
            self.QMessageBox.information(self.window, "Test connection", "Select a saved model first.")
            return
        model_id = self.current_model_id

        def on_success(result) -> None:
            if result.ok:
                elapsed = f" ({result.elapsed_ms} ms)" if result.elapsed_ms is not None else ""
                self.QMessageBox.information(
                    self.window,
                    "Test connection",
                    f"Connection OK{elapsed}\n{result.message}",
                )
            else:
                self.QMessageBox.critical(self.window, "Test connection failed", result.message)

        self.run_background_task(
            "Testing model connection...",
            lambda: self.model_service.test_connection(model_id),
            on_success,
        )

    def load_templates(self) -> None:
        selected_template_id = self.ai_template_combo.currentData()
        self.ai_template_combo.clear()
        self.ai_template_combo.addItem("Use default template", None)
        self.template_table.setRowCount(0)
        self.template_list.clear()
        for template in self.prompt_service.list_templates():
            self.ai_template_combo.addItem(template.name, template.id)
            self.template_list.addItem(f"{template.name}\nv{template.version}")
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
        self.select_combo_value(self.ai_template_combo, selected_template_id)

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
        self.rewrite_rules_edit.setPlainText(template.rewrite_rules)

    def clear_template_form(self) -> None:
        self.current_template_id = None
        self.template_table.clearSelection()
        self.template_name_edit.clear()
        self.template_default_check.setChecked(False)
        self.global_rules_edit.clear()
        self.summary_rules_edit.clear()
        self.rewrite_rules_edit.clear()

    def save_template(self) -> None:
        try:
            if self.current_template_id is None:
                self.current_template_id = self.prompt_service.create_template(
                    name=self.template_name_edit.text().strip(),
                    global_rules=self.global_rules_edit.toPlainText(),
                    summary_rules=self.summary_rules_edit.toPlainText(),
                    rewrite_rules=self.rewrite_rules_edit.toPlainText(),
                    is_default=self.template_default_check.isChecked(),
                )
            else:
                self.prompt_service.update_template(
                    template_id=self.current_template_id,
                    name=self.template_name_edit.text().strip(),
                    global_rules=self.global_rules_edit.toPlainText(),
                    summary_rules=self.summary_rules_edit.toPlainText(),
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

    def refresh_ai_diagnostics(self, chapter_id: int | None = None) -> None:
        target_chapter_id = chapter_id if chapter_id is not None else self.selected_chapter_id()
        if target_chapter_id is None:
            self.ai_diagnostics_text.clear()
            return

        statuses = self.pipeline_service.list_chapter_stage_statuses(target_chapter_id)
        errors = self.pipeline_service.list_chapter_errors(target_chapter_id)
        outputs = self.pipeline_service.get_chapter_ai_outputs(target_chapter_id)
        lines: list[str] = ["Stage status"]
        if statuses:
            for status in statuses:
                elapsed = f", {status.elapsed_ms} ms" if status.elapsed_ms is not None else ""
                lines.append(f"- {status.stage}: {status.status} (retries: {status.retry_count}{elapsed})")
        else:
            lines.append("- No stage records yet.")

        lines.append("")
        lines.append("AI outputs")
        if outputs.plot_summary:
            lines.append(f"- Summary: {self.compact_text(outputs.plot_summary, 220)}")
        else:
            lines.append("- Summary: not generated.")
        if outputs.needs_rewrite is None:
            lines.append("- Scene: not detected.")
        else:
            labels = ", ".join(outputs.scene_labels or []) or "-"
            decision = "needs rewrite" if outputs.needs_rewrite else "keep original"
            reasoning = self.compact_text(outputs.scene_reasoning or "", 160)
            lines.append(f"- Scene: {decision}; labels: {labels}; reason: {reasoning or '-'}")
        if outputs.rewritten_word_count is None:
            lines.append("- Rewrite: not generated.")
        else:
            ratio = f", ratio {outputs.expansion_ratio:.2f}" if outputs.expansion_ratio is not None else ""
            elapsed = f", {outputs.rewrite_elapsed_ms} ms" if outputs.rewrite_elapsed_ms is not None else ""
            lines.append(f"- Rewrite: {outputs.rewritten_word_count} chars{ratio}{elapsed}")

        lines.append("")
        lines.append("Open errors")
        if errors:
            for error in errors:
                lines.append(f"- [{error.stage}] {error.error_type or 'Error'}: {error.message}")
        else:
            lines.append("- No open errors.")

        self.ai_diagnostics_text.setPlainText("\n".join(lines))

    def save_ai_project_settings(self) -> None:
        project_id = self.active_project_id()
        if project_id is None:
            self.QMessageBox.information(self.window, "AI settings", "Select a project first.")
            return
        self.service.update_project_settings(
            project_id=project_id,
            model_id=self.ai_model_combo.currentData(),
            prompt_template_id=self.ai_template_combo.currentData(),
            concurrency=self.ai_concurrency_spin.value(),
            target_word_count=self.ai_target_word_count_spin.value() or None,
            min_expansion_ratio=self.ai_min_expansion_ratio_spin.value() or None,
        )
        self.ai_status_label.setText("Project AI settings saved.")

    def load_project_ai_settings(self, project_id: int | None) -> None:
        if project_id is None:
            self.select_combo_value(self.ai_model_combo, None)
            self.select_combo_value(self.ai_template_combo, None)
            self.ai_concurrency_spin.setValue(1)
            self.ai_target_word_count_spin.setValue(0)
            self.ai_min_expansion_ratio_spin.setValue(0)
            return
        settings = self.service.get_project_settings(project_id)
        self.select_combo_value(self.ai_model_combo, settings.model_id if settings else None)
        self.select_combo_value(self.ai_template_combo, settings.prompt_template_id if settings else None)
        self.ai_concurrency_spin.setValue(settings.concurrency if settings else 1)
        self.ai_target_word_count_spin.setValue(settings.target_word_count if settings and settings.target_word_count else 0)
        self.ai_min_expansion_ratio_spin.setValue(
            settings.min_expansion_ratio if settings and settings.min_expansion_ratio else 0
        )

    def run_project_pipeline(self) -> None:
        project_id = self.active_project_id()
        if project_id is None:
            self.QMessageBox.information(self.window, "AI Pipeline", "Select a project first.")
            return

        def on_success(result) -> None:
            self.ai_status_label.setText(
                f"Processed: {result.processed} | Failed: {result.failed} | Paused: {result.paused}"
            )
            self.load_projects()
            self.open_project_preview(project_id)

        self.run_background_task(
            "Project pipeline running...",
            lambda: self.pipeline_service.run_project(project_id),
            on_success,
        )

    def pause_current_project(self) -> None:
        project_id = self.active_project_id()
        if project_id is None:
            self.QMessageBox.information(self.window, "AI Pipeline", "Select a project first.")
            return
        self.pipeline_service.set_project_paused(project_id, True)
        self.ai_status_label.setText("Project paused.")
        self.load_projects()

    def summarize_selected_chapter(self) -> None:
        self._run_chapter_ai_action(self.pipeline_service.summarize_chapter, "Summary")

    def detect_selected_chapter_scene(self) -> None:
        self._run_chapter_ai_action(self.pipeline_service.detect_scene, "Scene detection")

    def rewrite_selected_chapter(self) -> None:
        self._run_chapter_ai_action(self.pipeline_service.rewrite_chapter, "Rewrite", refresh_preview=True)

    def retry_selected_chapter_stage(self) -> None:
        stage = self.ai_retry_stage_combo.currentData()
        label = self.ai_retry_stage_combo.currentText()
        self._run_chapter_ai_action(
            lambda chapter_id: self.pipeline_service.retry_chapter_stage(chapter_id, stage),
            f"Retry {label}",
            refresh_preview=stage == "rewrite",
        )

    def _run_chapter_ai_action(self, action, label: str, refresh_preview: bool = False) -> None:
        chapter_id = self.selected_chapter_id()
        if chapter_id is None:
            self.QMessageBox.information(self.window, "AI Pipeline", "Select a chapter first.")
            return

        def on_success(text) -> None:
            self.ai_output_text.setPlainText(text)
            self.ai_status_label.setText(f"{label} completed.")
            self.refresh_ai_diagnostics(chapter_id)
            if refresh_preview and self.current_project_id is not None:
                self.open_project_preview(self.current_project_id, chapter_id)

        self.run_background_task(
            f"{label} running...",
            lambda: action(chapter_id),
            on_success,
            failure_title=f"{label} failed",
        )

    def run_background_task(
        self,
        status_text: str,
        task,
        on_success,
        failure_title: str = "Task failed",
    ) -> None:
        self.set_ai_controls_enabled(False)
        self.ai_status_label.setText(status_text)
        running_task: RunningTask | None = None

        def on_failure(message: str) -> None:
            self.QMessageBox.critical(self.window, failure_title, message)
            self.ai_status_label.setText(message)

        def on_finished() -> None:
            self.set_ai_controls_enabled(True)
            if running_task in self.running_tasks:
                self.running_tasks.remove(running_task)

        running_task = start_background_task(task, on_success, on_failure, on_finished)
        self.running_tasks.append(running_task)

    def set_ai_controls_enabled(self, enabled: bool) -> None:
        for button in (
            self.model_test_button,
            self.ai_run_project_button,
            self.ai_summary_button,
            self.ai_scene_button,
            self.ai_rewrite_button,
            self.ai_retry_stage_button,
        ):
            button.setEnabled(enabled)
        self.ai_retry_stage_combo.setEnabled(enabled)

    def select_table_row(self, table, row_id: int) -> None:
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item is not None and int(item.data(self.Qt.ItemDataRole.UserRole)) == row_id:
                table.selectRow(row)
                return

    @staticmethod
    def select_combo_value(combo, value) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return
        combo.setCurrentIndex(0)

    @staticmethod
    def compact_text(text: str, limit: int) -> str:
        compacted = " ".join(text.split())
        if len(compacted) <= limit:
            return compacted
        return f"{compacted[: max(0, limit - 3)]}..."

    @staticmethod
    def project_progress_text(project: ProjectSummary) -> str:
        if project.total_chapters <= 0:
            return "0/0"
        percent = round(project.completed_chapters * 100 / project.total_chapters)
        return f"{project.completed_chapters}/{project.total_chapters} ({percent}%)"

    def new_project(self) -> None:
        dialog = NewProjectDialog(self.window, self.service, self.model_service, self.prompt_service)
        result = dialog.exec()
        if result and dialog.created_project_id is not None:
            self.current_project_id = dialog.created_project_id
            self.load_projects()
            self.open_project_preview(dialog.created_project_id)

    def refresh_project_cards(self) -> None:
        if not hasattr(self, "project_list"):
            return
        current_id = self.current_project_id
        search_text = self.project_search_edit.text().strip().lower() if hasattr(self, "project_search_edit") else ""
        status_filter = self.project_filter_combo.currentText() if hasattr(self, "project_filter_combo") else "All"
        projects = list(self.projects)
        if search_text:
            projects = [
                project
                for project in projects
                if search_text in project.name.lower() or search_text in (project.book_title or "").lower()
            ]
        if status_filter and status_filter != "All":
            projects = [project for project in projects if project.status == status_filter]
        if hasattr(self, "project_sort_combo"):
            sort_text = self.project_sort_combo.currentText()
            if sort_text == "Project name":
                projects.sort(key=lambda project: project.name.lower())
            elif sort_text == "Created at":
                projects.sort(key=lambda project: project.created_at, reverse=True)
            else:
                projects.sort(key=lambda project: project.updated_at, reverse=True)

        self.project_list.blockSignals(True)
        self.project_list.clear()
        for project in projects:
            item = self.QListWidgetItem(
                f"{project.name}\n{project.status} · {project.current_stage or '-'} · {project.updated_at}"
            )
            item.setData(self.Qt.ItemDataRole.UserRole, project.id)
            self.project_list.addItem(item)
            if current_id is not None and project.id == current_id:
                self.project_list.setCurrentItem(item)
        self.project_list.blockSignals(False)
        if current_id is not None:
            self.update_project_detail(current_id)
        elif projects:
            self.project_list.setCurrentRow(0)
            self.project_list_selection_changed(self.project_list.currentItem(), None)
        else:
            self.update_project_detail(None)

    def update_project_detail(self, project_id: int | None) -> None:
        project = next((item for item in self.projects if item.id == project_id), None)
        if project is None:
            self.project_detail_cover.setText("R")
            self.project_detail_title.setText("No projects yet")
            self.project_detail_description.setText("Import TXT / EPUB / DOCX to create the first rewrite project.")
            self.project_detail_status_container.itemAt(0).widget().setText("Empty")
            self.project_detail_updated_container.itemAt(0).widget().setText("-")
            self.metric_chapters_value.setText("0")
            self.metric_words_value.setText("0")
            self.metric_stage_value.setText("-")
            self.metric_progress_value.setText("0%")
            return
        self.project_detail_cover.setText((project.source_format or "TXT").upper()[:4])
        self.project_detail_title.setText(project.name)
        self.project_detail_description.setText(project.book_title or "No description yet.")
        self.project_detail_status_container.itemAt(0).widget().setText(project.status or "pending")
        self.project_detail_updated_container.itemAt(0).widget().setText(project.updated_at or "-")
        self.metric_chapters_value.setText(str(project.total_chapters))
        self.metric_words_value.setText(str(project.total_words))
        self.metric_stage_value.setText(project.current_stage or "-")
        progress = round(project.completed_chapters * 100 / project.total_chapters) if project.total_chapters else 0
        self.metric_progress_value.setText(f"{progress}%")

    def project_list_selection_changed(self, current, previous) -> None:
        if current is None:
            self.update_project_detail(None)
            return
        project_id = int(current.data(self.Qt.ItemDataRole.UserRole))
        self.current_project_id = project_id
        self.select_project_row(project_id)
        self.update_project_detail(project_id)
        self.load_project_ai_settings(project_id)

    def model_list_selection_changed(self, row: int) -> None:
        if row >= 0 and row < self.model_table.rowCount():
            self.model_table.selectRow(row)

    def template_list_selection_changed(self, row: int) -> None:
        if row >= 0 and row < self.template_table.rowCount():
            self.template_table.selectRow(row)

    def set_workspace_stage(self, stage_index: int) -> None:
        self.current_workspace_stage = max(0, min(stage_index, self.workspace_content_stack.count() - 1))
        self.workspace_content_stack.setCurrentIndex(self.current_workspace_stage)
        for index, button in enumerate(self.workspace_step_buttons):
            button.setChecked(index == self.current_workspace_stage)

    def continue_current_stage(self) -> None:
        if self.current_workspace_stage == 0:
            self.summarize_selected_chapter()
        elif self.current_workspace_stage == 1:
            self.detect_selected_chapter_scene()
        elif self.current_workspace_stage == 2:
            self.rewrite_selected_chapter()
        elif self.current_workspace_stage >= 3:
            self.run_project_pipeline()

    def project_table_selection_changed(self) -> None:
        project_id = self.selected_project_id()
        if project_id is not None:
            self.current_project_id = project_id
            self.update_project_detail(project_id)
            self.load_project_ai_settings(project_id)

    def open_selected_project_preview(self) -> None:
        project_id = self.selected_project_id()
        if project_id is None:
            self.QMessageBox.information(self.window, "Chapter Preview", "Select a project first.")
            return
        self.open_project_preview(project_id)

    def delete_selected_project(self) -> None:
        project_id = self.selected_project_id()
        if project_id is None:
            self.QMessageBox.information(self.window, "Delete Project", "Select a project first.")
            return

        project_name = self.project_name(project_id) or f"Project {project_id}"
        answer = self.QMessageBox.question(
            self.window,
            "Delete Project",
            f"Delete project '{project_name}' from the workbench?",
            self.QMessageBox.StandardButton.Yes | self.QMessageBox.StandardButton.No,
            self.QMessageBox.StandardButton.No,
        )
        if answer != self.QMessageBox.StandardButton.Yes:
            return

        try:
            self.service.delete_project(project_id)
        except Exception as exc:  # noqa: BLE001
            self.QMessageBox.critical(self.window, "Delete project failed", str(exc))
            return

        if self.current_project_id == project_id:
            self.clear_preview()
        self.load_projects()
        self.QMessageBox.information(self.window, "Delete Project", "Project removed from the workbench.")

    def open_project_preview(self, project_id: int, focus_chapter_id: int | None = None) -> None:
        self.current_project_id = project_id
        self.chapters = self.service.list_chapters(project_id)
        self.load_project_ai_settings(project_id)
        project = self.service.get_project(project_id)
        self.preview_project_label.setText(project.name if project is not None else f"Project {project_id}")
        self.refresh_export_history(project_id)
        self.chapter_list.clear()
        for chapter in self.chapters:
            item = self.QListWidgetItem(
                f"{chapter.index}. {chapter.title}\n{chapter.word_count} chars | {chapter.status}"
            )
            item.setData(self.Qt.ItemDataRole.UserRole, chapter.id)
            self.chapter_list.addItem(item)

        self.stack.setCurrentWidget(self.preview_page)
        if self.chapters:
            self.select_chapter_item(focus_chapter_id or self.chapters[0].id)
        else:
            self.preview_title.setText("No chapters")
            self.preview_meta.setText("")
            self.preview_text.clear()
            self.rewrite_text.clear()

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
        self.rewrite_text.setPlainText(chapter.rewritten_text or "")
        self.refresh_ai_diagnostics(chapter.id)

    def save_selected_chapter_rewrite(self) -> None:
        chapter_id = self.selected_chapter_id()
        if chapter_id is None:
            self.QMessageBox.information(self.window, "Save rewrite", "Select a chapter first.")
            return

        try:
            self.service.save_chapter_rewrite(chapter_id, self.rewrite_text.toPlainText())
        except Exception as exc:  # noqa: BLE001
            self.QMessageBox.critical(self.window, "Save rewrite failed", str(exc))
            return

        if self.current_project_id is not None:
            self.open_project_preview(self.current_project_id, chapter_id)
        self.QMessageBox.information(self.window, "Save rewrite", "Rewritten text saved.")

    def clear_selected_chapter_rewrite(self) -> None:
        chapter_id = self.selected_chapter_id()
        if chapter_id is None:
            self.QMessageBox.information(self.window, "Clear rewrite", "Select a chapter first.")
            return

        try:
            self.service.save_chapter_rewrite(chapter_id, "")
        except Exception as exc:  # noqa: BLE001
            self.QMessageBox.critical(self.window, "Clear rewrite failed", str(exc))
            return

        self.rewrite_text.clear()
        if self.current_project_id is not None:
            self.open_project_preview(self.current_project_id, chapter_id)

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
        if self.current_project_id is not None:
            self.refresh_export_history(self.current_project_id)
        self.QMessageBox.information(self.window, title, f"Exported to:\n{output}")

    def refresh_export_history(self, project_id: int | None = None) -> None:
        target_project_id = project_id if project_id is not None else self.current_project_id
        if target_project_id is None:
            self.export_history_text.clear()
            return
        exports = self.service.list_exports(target_project_id)
        if not exports:
            self.export_history_text.setPlainText("No exports yet.")
            return
        lines = [
            f"{record.created_at} | {record.export_format.upper()} | {record.chapter_count} chapters | "
            f"{record.word_count} chars | {record.output_path}"
            for record in exports[:10]
        ]
        self.export_history_text.setPlainText("\n".join(lines))

    def selected_project_id(self) -> int | None:
        selected = self.project_table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        item = self.project_table.item(row, 0)
        return int(item.data(self.Qt.ItemDataRole.UserRole))

    def selected_chapter_id(self) -> int | None:
        current = self.chapter_list.currentItem()
        if current is None:
            return None
        return int(current.data(self.Qt.ItemDataRole.UserRole))

    def select_chapter_item(self, chapter_id: int) -> None:
        for row in range(self.chapter_list.count()):
            item = self.chapter_list.item(row)
            if item is not None and int(item.data(self.Qt.ItemDataRole.UserRole)) == chapter_id:
                self.chapter_list.setCurrentRow(row)
                return
        self.chapter_list.setCurrentRow(0)

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
        self.rewrite_text.clear()
        self.export_history_text.clear()
