from __future__ import annotations

import os
from pathlib import Path


def default_database_path() -> Path:
    """Return the per-user SQLite location used by the desktop applications."""

    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "Rusty" / "rusty.db"
