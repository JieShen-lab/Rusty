from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication, QLabel, QMainWindow
    except ImportError as exc:
        raise SystemExit(
            "PySide6 is not installed. Install project dependencies with "
            "`python -m pip install -e .` before launching the app."
        ) from exc

    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("Rusty")
    window.resize(1200, 760)
    window.setCentralWidget(QLabel("Rusty MVP: project structure and database schema are ready."))
    window.show()
    return app.exec()

