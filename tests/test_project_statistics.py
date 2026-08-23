from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from support import initialized_database
from rusty.db import session
from rusty.models import ParsedBook, ParsedChapter
from rusty.services.project_service import ProjectService


def make_project(database: Path, root: Path) -> int:
    source = root / "source.txt"
    source.write_text("source", encoding="utf-8")
    book = ParsedBook(
        title="统计测试",
        author=None,
        language="zh-CN",
        source_path=source,
        source_format="txt",
        source_encoding="utf-8",
        chapters=[
            ParsedChapter(index=1, title="第一章", text="甲" * 1000),
            ParsedChapter(index=2, title="第二章", text="乙" * 1000),
        ],
    )
    return ProjectService(database).create_project(book, root / "workspace")


class ProjectStatisticsTests(unittest.TestCase):
    def test_source_chapter_expansion_and_contraction_use_word_delta(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            database = initialized_database(root / "rusty.db")
            project_id = make_project(database, root)
            service = ProjectService(database)
            with session(database) as connection:
                chapter_ids = [
                    int(row[0])
                    for row in connection.execute(
                        "SELECT id FROM chapters WHERE project_id=? ORDER BY chapter_index", (project_id,)
                    ).fetchall()
                ]
                connection.execute(
                    "UPDATE chapters SET rewritten_text=? WHERE id=?",
                    ("改" * 1300, chapter_ids[0]),
                )
                connection.execute(
                    "UPDATE chapters SET rewritten_text=? WHERE id=?",
                    ("缩" * 850, chapter_ids[1]),
                )
                connection.execute(
                    """INSERT INTO chapters(
                           project_id,chapter_index,title,original_text,word_count,origin_kind,status
                       ) VALUES(?,?,?,?,?, 'expansion', 'imported')""",
                    (project_id, 3, "新增章节", "新" * 1200, 1200),
                )
                expansion_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])

                connection.execute(
                    "UPDATE chapters SET rewritten_text=? WHERE id=?",
                    ("新改" * 675, expansion_id),
                )

            chapters = service.list_chapters(project_id)
            first, second, expansion = chapters
            self.assertEqual((1000, 1300, 300, False), (
                first.baseline_word_count,
                first.current_word_count,
                first.word_delta,
                first.is_added_chapter,
            ))
            self.assertEqual((1000, 850, -150, False), (
                second.baseline_word_count,
                second.current_word_count,
                second.word_delta,
                second.is_added_chapter,
            ))
            self.assertEqual((0, 1350, 1350, True), (
                expansion.baseline_word_count,
                expansion.current_word_count,
                expansion.word_delta,
                expansion.is_added_chapter,
            ))
            self.assertEqual(expansion, service.get_chapter(expansion.id))

            project = service.get_project(project_id)
            assert project is not None
            exported_word_count = sum(chapter.current_word_count for chapter in chapters)
            word_delta = sum(chapter.word_delta for chapter in chapters)
            self.assertEqual(exported_word_count - project.total_words, word_delta)
            self.assertEqual(3500, exported_word_count)
            self.assertEqual(1500, word_delta)


if __name__ == "__main__":
    unittest.main()
