from __future__ import annotations

import re
from pathlib import Path

from rusty.models import ParsedBook, ParsedChapter

DEFAULT_CHAPTER_PATTERN = re.compile(
    r"^\s*(第[一二三四五六七八九十百千万零〇两0-9]+[章节卷集部篇回].*|[0-9]+[、.．\s].*)\s*$"
)


def parse_txt(path: str | Path, chapter_pattern: re.Pattern[str] | None = None) -> ParsedBook:
    source_path = Path(path)
    text, encoding = read_text_with_encoding(source_path)
    chapters = split_chapters(text, chapter_pattern or DEFAULT_CHAPTER_PATTERN)
    return ParsedBook(
        title=source_path.stem,
        author=None,
        language=None,
        source_path=source_path,
        source_format="txt",
        source_encoding=encoding,
        chapters=chapters,
    )


def read_text_with_encoding(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"

    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            pass

    try:
        from charset_normalizer import from_bytes
    except ImportError:
        return raw.decode("utf-8", errors="replace"), "utf-8-replace"

    best = from_bytes(raw).best()
    if best is None:
        return raw.decode("utf-8", errors="replace"), "utf-8-replace"
    return str(best), best.encoding or "unknown"


def split_chapters(text: str, chapter_pattern: re.Pattern[str]) -> list[ParsedChapter]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    headings: list[tuple[int, str]] = []

    for line_number, line in enumerate(lines, start=1):
        title = line.strip()
        if title and chapter_pattern.match(title):
            headings.append((line_number, title))

    if not headings:
        content = normalized.strip()
        return [
            ParsedChapter(
                index=1,
                title="正文",
                text=content,
                start_line=1 if content else None,
                end_line=len(lines) if content else None,
            )
        ]

    chapters: list[ParsedChapter] = []
    for index, (line_number, title) in enumerate(headings, start=1):
        next_line = headings[index][0] if index < len(headings) else len(lines) + 1
        body_lines = lines[line_number: next_line - 1]
        body = "\n".join(body_lines).strip()
        chapters.append(
            ParsedChapter(
                index=index,
                title=title,
                text=body,
                start_line=line_number,
                end_line=next_line - 1,
            )
        )

    return chapters

