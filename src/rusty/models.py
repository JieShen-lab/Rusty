from __future__ import annotations

from dataclasses import dataclass
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


def count_text_units(text: str) -> int:
    return sum(1 for char in text if not char.isspace())

