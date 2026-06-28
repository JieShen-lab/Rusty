from .connection import connect, session

__all__ = ["CURRENT_SCHEMA_VERSION", "connect", "initialize_database", "session"]


def __getattr__(name: str):
    if name in {"CURRENT_SCHEMA_VERSION", "initialize_database"}:
        from . import schema

        return getattr(schema, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
