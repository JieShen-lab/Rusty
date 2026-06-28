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
        self.assertEqual("Workbench", window.workbench_nav.text())
        self.assertEqual("Chapter Preview", window.preview_nav.text())
        self.assertEqual("Models", window.models_nav.text())
        self.assertEqual("Prompts", window.prompts_nav.text())
        self.assertEqual("AI Pipeline", window.ai_nav.text())
        self.assertEqual("New Project", window.new_project_button.text())
        self.assertEqual("Export EPUB", window.export_epub_button.text())
        self.assertEqual("Save", window.model_save_button.text())
        self.assertEqual("Save", window.template_save_button.text())
        self.assertEqual("Run Project Pipeline", window.ai_run_project_button.text())
        self.assertEqual("Save Project AI Settings", window.ai_save_settings_button.text())
        self.assertEqual(0, window.project_table.rowCount())


if __name__ == "__main__":
    unittest.main()
