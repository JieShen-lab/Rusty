from __future__ import annotations

import html
from pathlib import Path

from ebooklib import epub

from rusty.models import ChapterRecord, EffectiveExportChapter


def export_epub(
    chapters: list[ChapterRecord] | list[EffectiveExportChapter],
    output_path: str | Path,
    title: str,
    author: str | None = None,
    language: str | None = None,
    identifier: str | None = None,
    use_rewrites: bool = True,
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
    for export_index, chapter in enumerate(chapters, start=1):
        chapter_doc = epub.EpubHtml(
            title=chapter.title,
            file_name=f"chap_{export_index:04d}.xhtml",
            lang=language or "zh-CN",
        )
        chapter_doc.content = _chapter_html(chapter, use_rewrites=use_rewrites)
        book.add_item(chapter_doc)
        epub_chapters.append(chapter_doc)

    book.toc = tuple(epub_chapters)
    book.spine = ["nav", *epub_chapters]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(output), book)
    return output


def _chapter_html(chapter: ChapterRecord | EffectiveExportChapter, use_rewrites: bool) -> str:
    text = chapter.rewritten_text if use_rewrites and chapter.rewritten_text else chapter.original_text
    paragraphs = [part.strip() for part in text.splitlines() if part.strip()]
    body = "\n".join(f"<p>{html.escape(paragraph)}</p>" for paragraph in paragraphs)
    return (
        "<html><head>"
        f"<title>{html.escape(chapter.title)}</title>"
        "</head><body>"
        f"<h1>{html.escape(chapter.title)}</h1>"
        f"{body}"
        "</body></html>"
    )
