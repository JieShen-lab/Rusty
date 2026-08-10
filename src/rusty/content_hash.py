from __future__ import annotations

import hashlib


def hash_text(text: str) -> str:
    """Return Rusty's canonical SHA-256 digest for UTF-8 text content."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
