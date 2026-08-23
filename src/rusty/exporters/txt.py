from __future__ import annotations

from typing import Protocol

from rusty.chapter_titles import format_chapter_heading


class ExportChapter(Protocol):
    title: str
    original_text: str
    rewritten_text: str | None


def build_txt_export(
    chapters: list[ExportChapter],
    use_rewrites: bool = True,
    volume_titles: dict[int, str] | None = None,
) -> str:
    parts: list[str] = []
    active_volume_id: int | None = None
    for export_index, chapter in enumerate(chapters, start=1):
        volume_id = getattr(chapter, "volume_id", None)
        if volume_id is not None and volume_id != active_volume_id:
            volume_title = (volume_titles or {}).get(volume_id)
            if volume_title:
                parts.append(volume_title)
        active_volume_id = volume_id
        text = chapter.rewritten_text if use_rewrites and chapter.rewritten_text else chapter.original_text
        parts.append(f"{format_chapter_heading(export_index, chapter.title)}\n\n{text.strip()}")
    return "\n\n".join(parts).strip() + "\n"
