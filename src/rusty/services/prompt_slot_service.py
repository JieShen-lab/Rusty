from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rusty.db import default_database_path, session


PROMPT_SLOT_KEYS = {
    "global_system",
    "chapter_summary",
    "plot_adjust",
    "expansion",
    "plot_rewrite",
    "writing",
}


@dataclass(frozen=True)
class PromptSlot:
    slot_key: str
    content: str
    updated_at: str


class PromptSlotService:
    """Read and update Rusty's six fixed prompt slots."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()

    def list_slots(self) -> list[PromptSlot]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                "SELECT slot_key, content, updated_at FROM prompt_slots ORDER BY rowid"
            ).fetchall()
        return [self._slot(row) for row in rows]

    def get_slot(self, slot_key: str) -> PromptSlot:
        self._validate_slot_key(slot_key)
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT slot_key, content, updated_at FROM prompt_slots WHERE slot_key = ?",
                (slot_key,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Prompt slot not found: {slot_key}")
        return self._slot(row)

    def update_slot(self, slot_key: str, content: str) -> PromptSlot:
        self._validate_slot_key(slot_key)
        normalized = content.strip()
        if not normalized:
            raise ValueError("Prompt content cannot be empty.")
        with session(self.database_path) as connection:
            cursor = connection.execute(
                "UPDATE prompt_slots SET content = ?, updated_at = CURRENT_TIMESTAMP WHERE slot_key = ?",
                (normalized, slot_key),
            )
            if cursor.rowcount == 0:
                raise FileNotFoundError(f"Prompt slot not found: {slot_key}")
        return self.get_slot(slot_key)

    def get_global_system_prompt(self) -> str:
        """Return Rusty's single active global system prompt used by every model request."""
        content = self.get_slot("global_system").content.strip()
        if not content:
            raise ValueError("系统提示词不能为空；所有 AI 请求都必须携带系统提示词。")
        return content

    @staticmethod
    def _validate_slot_key(slot_key: str) -> None:
        if slot_key not in PROMPT_SLOT_KEYS:
            raise ValueError(f"Unsupported prompt slot: {slot_key}")

    @staticmethod
    def _slot(row) -> PromptSlot:
        return PromptSlot(
            slot_key=str(row["slot_key"]),
            content=str(row["content"]),
            updated_at=str(row["updated_at"]),
        )
