from __future__ import annotations

import re


_CHAPTER_PREFIX = re.compile(
    r"^\s*(?:(?:第\s*[一二三四五六七八九十百千万零〇两0-9]+\s*[章节回篇]|[0-9]+\s*[章节回篇])(?:\s*[-—:：、.．]\s*|\s+)?|[0-9]+\s*[、.．]\s*)",
)


def normalize_chapter_title(value: str) -> str:
    """Return the user-authored title without its generated chapter ordinal."""
    return _CHAPTER_PREFIX.sub("", value.strip(), count=1).strip()


def format_chapter_heading(index: int, title: str) -> str:
    ordinal = _chinese_number(max(1, index))
    normalized_title = normalize_chapter_title(title)
    return f"第{ordinal}章{f' {normalized_title}' if normalized_title else ''}"


def _chinese_number(value: int) -> str:
    if value <= 0:
        return str(value)
    digits = "零一二三四五六七八九"
    units = ("", "十", "百", "千")
    if value >= 10_000:
        return str(value)
    result: list[str] = []
    zero_pending = False
    for position in range(3, -1, -1):
        divisor = 10**position
        digit = value // divisor % 10
        if digit:
            if zero_pending and result:
                result.append("零")
            if not (digit == 1 and position == 1 and not result):
                result.append(digits[digit])
            result.append(units[position])
            zero_pending = False
        elif result and value % divisor:
            zero_pending = True
    return "".join(result)
