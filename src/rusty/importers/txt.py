from __future__ import annotations

import re
from pathlib import Path

from rusty.models import ParsedBook, ParsedChapter, ParsedVolume

DEFAULT_CHAPTER_PATTERN = re.compile(
    r"^\s*(第[一二三四五六七八九十百千万零〇两0-9]+[章节集部篇回].*|[0-9]+[、.．\s].*)\s*$"
)
VOLUME_TITLE_PATTERN = re.compile(
    r"^\s*(?:第[一二三四五六七八九十百千万零〇两0-9]+卷|卷[一二三四五六七八九十百千万零〇两0-9]+)(?:\s.*|[：:].*)?\s*$"
)


def parse_txt(path: str | Path, chapter_pattern: re.Pattern[str] | None = None) -> ParsedBook:
    source_path = Path(path)
    text, encoding = read_text_with_encoding(source_path)
    chapters, volumes = split_document_structure(text, chapter_pattern or DEFAULT_CHAPTER_PATTERN)
    return ParsedBook(
        title=source_path.stem,
        author=None,
        language=None,
        source_path=source_path,
        source_format="txt",
        source_encoding=encoding,
        chapters=chapters,
        volumes=volumes,
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
    chapters, _ = split_document_structure(text, chapter_pattern)
    return chapters


def split_document_structure(
    text: str,
    chapter_pattern: re.Pattern[str] = DEFAULT_CHAPTER_PATTERN,
    known_volume_titles: set[str] | None = None,
) -> tuple[list[ParsedChapter], list[ParsedVolume]]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    headings: list[tuple[int, str, str]] = []

    for line_number, line in enumerate(lines, start=1):
        title = line.strip()
        if not title:
            continue
        if title in (known_volume_titles or set()) or VOLUME_TITLE_PATTERN.fullmatch(title):
            headings.append((line_number, title, "volume"))
        elif chapter_pattern.fullmatch(title):
            headings.append((line_number, title, "chapter"))

    chapter_headings = [item for item in headings if item[2] == "chapter"]
    volume_headings = [item for item in headings if item[2] == "volume"]
    if not chapter_headings and not volume_headings:
        content = normalized.strip()
        return [
            ParsedChapter(
                index=1,
                title="第一章",
                text=content,
                start_line=1 if content else None,
                end_line=len(lines) if content else None,
            )
        ], []

    volumes = [
        ParsedVolume(
            index=index,
            title=title,
            start_line=line_number,
            end_line=(volume_headings[index][0] - 1 if index < len(volume_headings) else len(lines)),
        )
        for index, (line_number, title, _) in enumerate(volume_headings, start=1)
    ]
    chapters: list[ParsedChapter] = []
    if not chapter_headings:
        for volume in volumes:
            start_line = min(volume.end_line, volume.start_line + 1)
            body = "\n".join(lines[start_line - 1:volume.end_line]).strip()
            chapters.append(
                ParsedChapter(
                    index=len(chapters) + 1,
                    title="第一章",
                    text=body,
                    start_line=start_line,
                    end_line=volume.end_line,
                    volume_index=volume.index,
                )
            )
        return chapters, volumes

    for index, (line_number, title, _) in enumerate(chapter_headings, start=1):
        following_headings = [item for item in headings if item[0] > line_number]
        next_line = following_headings[0][0] if following_headings else len(lines) + 1
        body_lines = lines[line_number: next_line - 1]
        body = "\n".join(body_lines).strip()
        containing_volume = next(
            (
                volume
                for volume in reversed(volumes)
                if volume.start_line < line_number <= volume.end_line
            ),
            None,
        )
        chapters.append(
            ParsedChapter(
                index=index,
                title=title,
                text=body,
                start_line=line_number,
                end_line=next_line - 1,
                volume_index=containing_volume.index if containing_volume else None,
            )
        )

    return chapters, volumes
