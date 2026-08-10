from .connection import connect, session
from .paths import default_database_path

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "connect",
    "default_database_path",
    "initialize_database",
    "session",
]


def __getattr__(name: str):
    if name in {"CURRENT_SCHEMA_VERSION", "initialize_database"}:
        from . import schema

        return getattr(schema, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
