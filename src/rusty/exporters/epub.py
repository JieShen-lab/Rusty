from __future__ import annotations

import html
from pathlib import Path

from ebooklib import epub

from rusty.chapter_titles import format_chapter_heading
from rusty.models import ChapterRecord, EffectiveExportChapter


def export_epub(
    chapters: list[ChapterRecord] | list[EffectiveExportChapter],
    output_path: str | Path,
    title: str,
    author: str | None = None,
    language: str | None = None,
    identifier: str | None = None,
    use_rewrites: bool = True,
    volume_titles: dict[int, str] | None = None,
) -> Path:
    if not chapters:
        raise ValueError("Project has no chapters to export.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    book = epub.EpubBook()
    book.set_identifier(identifier or f"rusty-{title}")
    book.set_title(title)
    book.set_language(language or "zh-CN")
    if author:
        book.add_author(author)

    epub_chapters = []
    toc_items: list[object] = []
    volume_chapters: dict[int, list[epub.EpubHtml]] = {}
    volume_order: list[int] = []
    for export_index, chapter in enumerate(chapters, start=1):
        heading = format_chapter_heading(export_index, chapter.title)
        chapter_doc = epub.EpubHtml(
            title=heading,
            file_name=f"chap_{export_index:04d}.xhtml",
            lang=language or "zh-CN",
        )
        chapter_doc.content = _chapter_html(chapter, heading, use_rewrites=use_rewrites)
        book.add_item(chapter_doc)
        epub_chapters.append(chapter_doc)
        volume_id = getattr(chapter, "volume_id", None)
        if volume_id is None or volume_id not in (volume_titles or {}):
            toc_items.append(chapter_doc)
        else:
            if volume_id not in volume_chapters:
                volume_chapters[volume_id] = []
                volume_order.append(volume_id)
                toc_items.append(volume_id)
            volume_chapters[volume_id].append(chapter_doc)

    nested_toc: list[object] = []
    for item in toc_items:
        if isinstance(item, int):
            nested_toc.append(
                (
                    epub.Section(html.escape((volume_titles or {})[item])),
                    tuple(volume_chapters[item]),
                )
            )
        else:
            nested_toc.append(item)
    book.toc = tuple(nested_toc)
    book.spine = ["nav", *epub_chapters]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(output), book)
    return output


def _chapter_html(
    chapter: ChapterRecord | EffectiveExportChapter,
    heading: str,
    use_rewrites: bool,
) -> str:
    text = chapter.rewritten_text if use_rewrites and chapter.rewritten_text else chapter.original_text
    paragraphs = [part.strip() for part in text.splitlines() if part.strip()]
    body = "\n".join(f"<p>{html.escape(paragraph)}</p>" for paragraph in paragraphs)
    return (
        "<html><head>"
        f"<title>{html.escape(heading)}</title>"
        "</head><body>"
        f"<h1>{html.escape(heading)}</h1>"
        f"{body}"
        "</body></html>"
    )
