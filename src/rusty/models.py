from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from pathlib import Path


@dataclass(frozen=True)
class ParsedChapter:
    index: int
    title: str
    text: str
    start_line: int | None = None
    end_line: int | None = None

    @property
    def word_count(self) -> int:
        return count_text_units(self.text)


@dataclass(frozen=True)
class ParsedBook:
    title: str
    author: str | None
    language: str | None
    source_path: Path
    source_format: str
    source_encoding: str | None
    chapters: list[ParsedChapter]
    publisher: str | None = None
    description: str | None = None
    source_identifier: str | None = None
    metadata: dict[str, Any] | None = None

    @property
    def total_words(self) -> int:
        return sum(chapter.word_count for chapter in self.chapters)


@dataclass(frozen=True)
class ProjectSummary:
    id: int
    name: str
    status: str
    current_stage: str
    source_format: str | None
    source_path: str | None
    workspace_path: str | None
    total_chapters: int
    total_words: int
    completed_chapters: int
    book_title: str | None
    author: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ProjectSettings:
    project_id: int
    model_id: int | None
    prompt_template_id: int | None
    txt_split_rule_id: int | None
    processing_mode: str
    concurrency: int
    target_word_count: int | None
    min_expansion_ratio: float | None


@dataclass(frozen=True)
class ChapterRecord:
    id: int
    project_id: int
    index: int
    title: str
    original_text: str
    rewritten_text: str | None
    word_count: int
    status: str
    start_line: int | None
    end_line: int | None


@dataclass(frozen=True)
class ExportPlanItem:
    chapter_id: int
    export_order: int
    export_title: str
    include_in_export: bool
    source_status: str = "original"


@dataclass(frozen=True)
class EffectiveExportChapter:
    id: int
    project_id: int
    index: int
    title: str
    original_title: str
    original_text: str
    rewritten_text: str | None
    word_count: int
    status: str
    source_status: str
    include_in_export: bool
    start_line: int | None
    end_line: int | None


@dataclass(frozen=True)
class StageStatus:
    stage: str
    status: str
    retry_count: int
    elapsed_ms: int | None
    started_at: str | None
    finished_at: str | None


@dataclass(frozen=True)
class ChapterError:
    id: int
    stage: str
    error_type: str | None
    message: str
    created_at: str
    resolved_at: str | None


@dataclass(frozen=True)
class ChapterAIOutputs:
    plot_summary: str | None = None
    needs_rewrite: bool | None = None
    scene_labels: list[str] | None = None
    scene_reasoning: str | None = None
    plot_expansion_enabled: bool | None = None
    expanded_plot: str | None = None
    rewrite_source: str | None = None
    rewritten_word_count: int | None = None
    expansion_ratio: float | None = None
    rewrite_elapsed_ms: int | None = None


@dataclass(frozen=True)
class ExportRecord:
    id: int
    project_id: int
    export_format: str
    output_path: str
    chapter_count: int
    word_count: int
    created_at: str


def count_text_units(text: str) -> int:
    return sum(1 for char in text if not char.isspace())
