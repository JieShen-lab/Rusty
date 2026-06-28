from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class TaskRunnerTests(unittest.TestCase):
    def test_background_task_reports_success(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWidgets import QApplication

        from rusty.ui.task_runner import start_background_task

        app = QApplication.instance() or QApplication([])
        results = []
        failures = []
        loop = QEventLoop()
        running_task = start_background_task(
            lambda: "done",
            lambda result: results.append(result),
            lambda message: failures.append(message),
            loop.quit,
        )
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
        running_task.thread.wait(1000)

        self.assertIsNotNone(app)
        self.assertIsNotNone(running_task)
        self.assertEqual(["done"], results)
        self.assertEqual([], failures)

    def test_background_task_reports_failure(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWidgets import QApplication

        from rusty.ui.task_runner import start_background_task

        app = QApplication.instance() or QApplication([])
        results = []
        failures = []
        loop = QEventLoop()

        def fail():
            raise RuntimeError("boom")

        running_task = start_background_task(
            fail,
            lambda result: results.append(result),
            lambda message: failures.append(message),
            loop.quit,
        )
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
        running_task.thread.wait(1000)

        self.assertIsNotNone(app)
        self.assertIsNotNone(running_task)
        self.assertEqual([], results)
        self.assertEqual(["boom"], failures)


if __name__ == "__main__":
    unittest.main()
