from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.exporters import build_txt_export
from rusty.importers.txt import DEFAULT_CHAPTER_PATTERN, split_chapters, split_document_structure
from rusty.models import ChapterRecord, count_text_units


class TxtImporterTests(unittest.TestCase):
    def test_split_chapters_detects_chinese_headings(self) -> None:
        text = "\n".join(
            [
                "第一章 初遇",
                "她推开门。",
                "夜色很深。",
                "",
                "第二章 回声",
                "旧钟响了三次。",
            ]
        )

        chapters = split_chapters(text, chapter_pattern=DEFAULT_CHAPTER_PATTERN)

        self.assertEqual(2, len(chapters))
        self.assertEqual("第一章 初遇", chapters[0].title)
        self.assertEqual("她推开门。\n夜色很深。", chapters[0].text)
        self.assertEqual(1, chapters[0].start_line)
        self.assertEqual(4, chapters[0].end_line)
        self.assertEqual("第二章 回声", chapters[1].title)

    def test_split_chapters_falls_back_to_single_body(self) -> None:
        chapters = split_chapters("没有章节标题\n只有正文", chapter_pattern=DEFAULT_CHAPTER_PATTERN)

        self.assertEqual(1, len(chapters))
        self.assertEqual("第一章", chapters[0].title)
        self.assertEqual("没有章节标题\n只有正文", chapters[0].text)

    def test_volume_and_chapter_titles_are_parsed_as_distinct_levels(self) -> None:
        chapters, volumes = split_document_structure(
            "第七卷 雨夜\n\n第787章 雨夜\n正文一。\n\n第788章 风声\n正文二。\n"
        )

        self.assertEqual(["第七卷 雨夜"], [volume.title for volume in volumes])
        self.assertEqual(["第787章 雨夜", "第788章 风声"], [chapter.title for chapter in chapters])
        self.assertEqual([1, 1], [chapter.volume_index for chapter in chapters])

    def test_real_chapter_does_not_add_default_first_chapter(self) -> None:
        chapters, volumes = split_document_structure("第787章 雨夜\n正文。")

        self.assertEqual([], volumes)
        self.assertEqual(["第787章 雨夜"], [chapter.title for chapter in chapters])

    def test_build_txt_export_uses_rewritten_text_when_available(self) -> None:
        chapters = [
            ChapterRecord(
                id=1,
                project_id=1,
                index=1,
                title="第一章",
                original_text="原文",
                rewritten_text="改写",
                word_count=2,
                status="imported",
                start_line=1,
                end_line=2,
            )
        ]

        self.assertEqual("第一章\n\n改写\n", build_txt_export(chapters))

    def test_count_text_units_ignores_whitespace(self) -> None:
        self.assertEqual(4, count_text_units("ab\n c d "))


if __name__ == "__main__":
    unittest.main()
