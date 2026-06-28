from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise SystemExit(
            "PySide6 is not installed. Install project dependencies with "
            "`python -m pip install -e .` before launching the app."
        ) from exc

    from rusty.ui import RustyMainWindow

    app = QApplication(sys.argv)
    window = RustyMainWindow()
    window.show()
    return app.exec()
