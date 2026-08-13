from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db import initialize_database_file


def initialized_database(path: str | Path) -> Path:
    """Create or migrate a test database before constructing its service graph."""
    database_path = Path(path)
    initialize_database_file(database_path)
    return database_path
