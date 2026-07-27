from __future__ import annotations

import re
from pathlib import Path

from rusty.importers.txt import parse_txt, read_text_with_encoding, split_chapters
from rusty.models import ParsedBook


CHINESE_NUMERALS = "零〇一二三四五六七八九十百千万两"
DEFAULT_TITLE_SUFFIXES = ("章", "回", "节", "卷", "集", "部", "篇")


class ChapterSplitService:
    def preview_txt(
        self,
        source_path: str | Path,
        *,
        mode: str = "auto",
        line_prefix: str = "第",
        number_style: str = "mixed",
        title_suffixes: list[str] | None = None,
        extra_title_regex: str | None = None,
        custom_regex: str | None = None,
    ) -> ParsedBook:
        path = Path(source_path)
        normalized_mode = mode.strip().lower()
        if normalized_mode == "auto":
            return parse_txt(path)

        text, encoding = read_text_with_encoding(path)
        if normalized_mode == "simple":
            pattern = build_simple_chapter_pattern(
                line_prefix=line_prefix,
                number_style=number_style,
                title_suffixes=title_suffixes,
                extra_title_regex=extra_title_regex,
            )
            chapters = split_chapters(text, pattern)
        elif normalized_mode == "regex":
            if not custom_regex or not custom_regex.strip():
                raise ValueError("正则拆分模式需要填写章节标题正则表达式。")
            try:
                pattern = re.compile(custom_regex)
            except re.error as exc:
                raise ValueError(f"章节正则表达式无效：{exc}") from exc
            chapters = split_chapters(text, pattern)
        else:
            raise ValueError(f"不支持的章节拆分模式：{mode}")

        return ParsedBook(
            title=path.stem,
            author=None,
            language=None,
            source_path=path,
            source_format="txt",
            source_encoding=encoding,
            chapters=chapters,
        )

def build_simple_chapter_pattern(
    *,
    line_prefix: str = "第",
    number_style: str = "mixed",
    title_suffixes: list[str] | None = None,
    extra_title_regex: str | None = None,
) -> re.Pattern[str]:
    prefix = re.escape(line_prefix.strip()) if line_prefix.strip() else ""
    suffixes = [item.strip() for item in (title_suffixes or list(DEFAULT_TITLE_SUFFIXES)) if item.strip()]
    if not suffixes:
        raise ValueError("简易拆分规则至少需要一个章节单位。")
    suffix_pattern = "|".join(re.escape(item) for item in suffixes)
    if number_style == "arabic":
        number_pattern = r"[0-9]+"
    elif number_style == "chinese":
        number_pattern = rf"[{CHINESE_NUMERALS}]+"
    elif number_style == "mixed":
        number_pattern = rf"[{CHINESE_NUMERALS}0-9]+"
    else:
        raise ValueError(f"不支持的章节数字类型：{number_style}")

    main = rf"{prefix}{number_pattern}(?:{suffix_pattern})(?:\s+.*|.*)?"
    alternatives = [main]
    if extra_title_regex and extra_title_regex.strip():
        try:
            re.compile(extra_title_regex)
        except re.error as exc:
            raise ValueError(f"附加章节规则无效：{exc}") from exc
        alternatives.append(f"(?:{extra_title_regex})")
    return re.compile(rf"^\s*(?:{'|'.join(alternatives)})\s*$")
