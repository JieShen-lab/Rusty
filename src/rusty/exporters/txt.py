from __future__ import annotations

from rusty.models import ChapterRecord, EffectiveExportChapter


def build_txt_export(chapters: list[ChapterRecord] | list[EffectiveExportChapter], use_rewrites: bool = True) -> str:
    parts: list[str] = []
    for chapter in chapters:
        text = chapter.rewritten_text if use_rewrites and chapter.rewritten_text else chapter.original_text
        parts.append(f"{chapter.title}\n\n{text.strip()}")
    return "\n\n".join(parts).strip() + "\n"
