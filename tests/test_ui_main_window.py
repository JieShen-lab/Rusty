from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class MainWindowTests(unittest.TestCase):
    def test_main_window_exposes_stage_two_flow(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            previous_local_appdata = os.environ.get("LOCALAPPDATA")
            os.environ["LOCALAPPDATA"] = directory
            try:
                from PySide6.QtWidgets import QApplication

                from rusty.ui import RustyMainWindow

                app = QApplication.instance() or QApplication([])
                window = RustyMainWindow()
            finally:
                if previous_local_appdata is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = previous_local_appdata

        self.assertEqual("Rusty", window.window.windowTitle())
        self.assertEqual(5, window.stack.count())
        self.assertEqual("工作台", window.workbench_nav.toolTip())
        self.assertEqual("项目工作区", window.preview_nav.toolTip())
        self.assertEqual("模型", window.models_nav.toolTip())
        self.assertEqual("提示词", window.prompts_nav.toolTip())
        self.assertEqual("AI 流水线", window.ai_nav.toolTip())
        self.assertEqual("+ 新建工程", window.new_project_button.text())
        self.assertEqual("删除", window.delete_project_button.text())
        self.assertEqual("导出 EPUB", window.export_epub_button.text())
        self.assertEqual("保存改写", window.save_rewrite_button.text())
        self.assertEqual("清空改写", window.clear_rewrite_button.text())
        self.assertEqual("保存", window.model_save_button.text())
        self.assertEqual("测试连接", window.model_test_button.text())
        self.assertEqual("保存", window.template_save_button.text())
        self.assertEqual("运行项目流水线", window.ai_run_project_button.text())
        self.assertEqual("保存项目 AI 设置", window.ai_save_settings_button.text())
        self.assertEqual(1, window.ai_concurrency_spin.value())
        self.assertEqual(0, window.ai_target_word_count_spin.value())
        self.assertEqual(0, window.ai_min_expansion_ratio_spin.value())
        self.assertEqual("重试阶段", window.ai_retry_stage_button.text())
        self.assertEqual("summary", window.ai_retry_stage_combo.itemData(0))
        self.assertEqual("scene_detection", window.ai_retry_stage_combo.itemData(1))
        self.assertEqual("rewrite", window.ai_retry_stage_combo.itemData(2))
        self.assertTrue(hasattr(window, "ai_diagnostics_text"))
        self.assertTrue(hasattr(window, "export_history_text"))
        self.assertTrue(hasattr(window, "rewrite_text"))
        self.assertTrue(hasattr(window, "run_background_task"))
        self.assertTrue(hasattr(window, "refresh_export_history"))
        self.assertTrue(hasattr(window, "retry_selected_chapter_stage"))
        self.assertTrue(hasattr(window, "delete_selected_project"))
        self.assertEqual("a b c", window.compact_text("a\n b\tc", 20))
        self.assertEqual("ab...", window.compact_text("abcdef", 5))
        self.assertEqual([], window.running_tasks)
        self.assertEqual(0, window.project_table.rowCount())
        self.assertEqual(9, window.project_table.columnCount())
        self.assertEqual("Progress", window.project_table.horizontalHeaderItem(6).text())


if __name__ == "__main__":
    unittest.main()
