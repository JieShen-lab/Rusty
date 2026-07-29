from __future__ import annotations

from rusty.models import ChapterRecord, EffectiveExportChapter


def build_txt_export(
    chapters: list[ChapterRecord] | list[EffectiveExportChapter],
    use_rewrites: bool = True,
    volume_titles: dict[int, str] | None = None,
) -> str:
    parts: list[str] = []
    active_volume_id: int | None = None
    for chapter in chapters:
        volume_id = getattr(chapter, "volume_id", None)
        if volume_id is not None and volume_id != active_volume_id:
            volume_title = (volume_titles or {}).get(volume_id)
            if volume_title:
                parts.append(volume_title)
        active_volume_id = volume_id
        text = chapter.rewritten_text if use_rewrites and chapter.rewritten_text else chapter.original_text
        parts.append(f"{chapter.title}\n\n{text.strip()}")
    return "\n\n".join(parts).strip() + "\n"
