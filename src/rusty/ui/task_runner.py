from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal


class TaskWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, task: Callable[[], Any]) -> None:
        super().__init__()
        self.task = task

    def run(self) -> None:
        try:
            self.succeeded.emit(self.task())
        except Exception as exc:  # noqa: BLE001 - UI boundary reports task failures.
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


@dataclass
class RunningTask:
    thread: QThread
    worker: TaskWorker


def start_background_task(
    task: Callable[[], Any],
    on_success: Callable[[Any], None],
    on_failure: Callable[[str], None],
    on_finished: Callable[[], None],
) -> RunningTask:
    thread = QThread()
    worker = TaskWorker(task)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.succeeded.connect(on_success)
    worker.failed.connect(on_failure)
    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    worker.finished.connect(on_finished)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return RunningTask(thread=thread, worker=worker)

