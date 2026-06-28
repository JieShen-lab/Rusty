from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup
from ebooklib import ITEM_DOCUMENT
from ebooklib import epub

from rusty.models import ParsedBook, ParsedChapter


def parse_epub(path: str | Path) -> ParsedBook:
    source_path = Path(path)
    book = epub.read_epub(str(source_path))
    title = _first_metadata(book, "DC", "title") or source_path.stem
    author = _first_metadata(book, "DC", "creator")
    language = _first_metadata(book, "DC", "language")
    publisher = _first_metadata(book, "DC", "publisher")
    description = _first_metadata(book, "DC", "description")
    identifier = _first_metadata(book, "DC", "identifier")

    chapters: list[ParsedChapter] = []
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        name = item.get_name().lower()
        if name.endswith("nav.xhtml") or name.endswith("toc.xhtml"):
            continue

        html = item.get_content().decode("utf-8", errors="replace")
        chapter_title, chapter_text = _extract_document_text(html, fallback_title=Path(item.get_name()).stem)
        if not chapter_text:
            continue

        chapters.append(
            ParsedChapter(
                index=len(chapters) + 1,
                title=chapter_title,
                text=chapter_text,
            )
        )

    if not chapters:
        chapters.append(ParsedChapter(index=1, title=title, text=""))

    return ParsedBook(
        title=title,
        author=author,
        language=language,
        source_path=source_path,
        source_format="epub",
        source_encoding="utf-8",
        chapters=chapters,
        publisher=publisher,
        description=description,
        source_identifier=identifier,
        metadata={
            "epub_version": getattr(book, "EPUB_VERSION", None),
            "item_count": len(list(book.get_items())),
        },
    )


def _first_metadata(book: epub.EpubBook, namespace: str, name: str) -> str | None:
    values = book.get_metadata(namespace, name)
    if not values:
        return None
    value = values[0][0]
    return str(value).strip() or None


def _extract_document_text(html: str, fallback_title: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    title_tag = soup.find(["h1", "h2", "h3", "title"])
    title = title_tag.get_text(" ", strip=True) if title_tag else fallback_title
    text = soup.get_text("\n")
    lines = [line.strip() for line in text.splitlines()]
    cleaned_lines = [line for line in lines if line]

    if cleaned_lines and cleaned_lines[0] == title:
        cleaned_lines = cleaned_lines[1:]

    return title or fallback_title, "\n".join(cleaned_lines).strip()

