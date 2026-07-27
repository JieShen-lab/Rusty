from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rusty.services.chapter_split_service import ChapterSplitService


class ChapterSplitServiceTests(unittest.TestCase):
    def test_simple_split_builds_chapters_from_configured_title_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text("第一章 起\n甲。\n\n第二章 承\n乙。", encoding="utf-8")
            book = ChapterSplitService().preview_txt(
                source,
                mode="simple",
                line_prefix="第",
                number_style="chinese",
                title_suffixes=["章"],
            )

        self.assertEqual(["第一章 起", "第二章 承"], [chapter.title for chapter in book.chapters])
        self.assertEqual(["甲。", "乙。"], [chapter.text for chapter in book.chapters])

    def test_regex_split_rejects_invalid_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text("正文", encoding="utf-8")
            service = ChapterSplitService()
            with self.assertRaisesRegex(ValueError, "正则"):
                service.preview_txt(source, mode="regex", custom_regex="[")

if __name__ == "__main__":
    unittest.main()
