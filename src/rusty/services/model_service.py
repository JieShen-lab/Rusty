from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from rusty.db import session
from rusty.secrets import SecretStore, default_secret_store
from rusty.db import default_database_path


@dataclass(frozen=True)
class ModelConfig:
    id: int
    display_name: str
    provider: str
    base_url: str
    model_name: str
    temperature: float
    max_tokens: int | None
    timeout_seconds: int
    is_default: bool
    has_api_key: bool


@dataclass(frozen=True)
class ModelTestResult:
    ok: bool
    message: str
    elapsed_ms: int | None = None


class ModelService:
    def __init__(
        self,
        database_path: str | Path | None = None,
        secret_store: SecretStore | None = None,
    ) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.secret_store = secret_store or default_secret_store()

    def create_model(
        self,
        display_name: str,
        provider: str,
        base_url: str,
        model_name: str,
        api_key: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout_seconds: int = 60,
        is_default: bool = False,
    ) -> int:
        with session(self.database_path) as connection:
            if is_default:
                connection.execute("UPDATE ai_models SET is_default = 0 WHERE deleted_at IS NULL")
            cursor = connection.execute(
                """
                INSERT INTO ai_models (
                    display_name,
                    provider,
                    base_url,
                    model_name,
                    temperature,
                    max_tokens,
                    timeout_seconds,
                    is_default
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    display_name,
                    provider,
                    base_url,
                    model_name,
                    temperature,
                    max_tokens,
                    timeout_seconds,
                    1 if is_default else 0,
                ),
            )
            model_id = int(cursor.lastrowid)
            if api_key:
                ref = self.secret_store.set_secret(self._api_key_name(model_id), api_key)
                connection.execute("UPDATE ai_models SET api_key_secret_ref = ? WHERE id = ?", (ref, model_id))
        return model_id

    def update_model(
        self,
        model_id: int,
        display_name: str,
        provider: str,
        base_url: str,
        model_name: str,
        api_key: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout_seconds: int = 60,
        is_default: bool = False,
    ) -> None:
        with session(self.database_path) as connection:
            if is_default:
                connection.execute("UPDATE ai_models SET is_default = 0 WHERE deleted_at IS NULL")

            existing = connection.execute(
                "SELECT api_key_secret_ref FROM ai_models WHERE id = ? AND deleted_at IS NULL",
                (model_id,),
            ).fetchone()
            if existing is None:
                raise ValueError(f"Model not found: {model_id}")

            secret_ref = existing["api_key_secret_ref"]
            if api_key:
                new_secret_ref = self.secret_store.set_secret(self._api_key_name(model_id), api_key)
                if secret_ref and secret_ref != new_secret_ref:
                    self.secret_store.delete_secret(secret_ref)
                secret_ref = new_secret_ref

            connection.execute(
                """
                UPDATE ai_models
                SET
                    display_name = ?,
                    provider = ?,
                    base_url = ?,
                    model_name = ?,
                    api_key_secret_ref = ?,
                    temperature = ?,
                    max_tokens = ?,
                    timeout_seconds = ?,
                    is_default = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (
                    display_name,
                    provider,
                    base_url,
                    model_name,
                    secret_ref,
                    temperature,
                    max_tokens,
                    timeout_seconds,
                    1 if is_default else 0,
                    model_id,
                ),
            )

    def delete_model(self, model_id: int) -> None:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT api_key_secret_ref FROM ai_models WHERE id = ?",
                (model_id,),
            ).fetchone()
            if row is not None:
                secret_ref = row["api_key_secret_ref"]
                if secret_ref:
                    self.secret_store.delete_secret(secret_ref)
            connection.execute(
                "UPDATE ai_models SET deleted_at = CURRENT_TIMESTAMP, is_default = 0 WHERE id = ?",
                (model_id,),
            )

    def list_models(self) -> list[ModelConfig]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    display_name,
                    provider,
                    base_url,
                    model_name,
                    api_key_secret_ref,
                    temperature,
                    max_tokens,
                    timeout_seconds,
                    is_default
                FROM ai_models
                WHERE deleted_at IS NULL
                ORDER BY is_default DESC, updated_at DESC, id DESC
                """
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def get_model(self, model_id: int) -> ModelConfig | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    display_name,
                    provider,
                    base_url,
                    model_name,
                    api_key_secret_ref,
                    temperature,
                    max_tokens,
                    timeout_seconds,
                    is_default
                FROM ai_models
                WHERE id = ? AND deleted_at IS NULL
                """,
                (model_id,),
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def get_default_model(self) -> ModelConfig | None:
        models = self.list_models()
        return models[0] if models else None

    def resolve_model_config(
        self,
        model_id: int | None = None,
        *,
        project_id: int | None = None,
    ) -> ModelConfig:
        """Resolve one model consistently for connection tests and generation tasks."""
        selected_id = model_id
        if selected_id is None and project_id is not None:
            from rusty.services.project_service import ProjectService

            settings = ProjectService(self.database_path).get_project_settings(project_id)
            selected_id = settings.model_id if settings is not None else None
        model = self.get_model(selected_id) if selected_id is not None else self.get_default_model()
        if model is None:
            raise ValueError("No model configured.")
        return model

    def get_api_key(self, model_id: int) -> str | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT api_key_secret_ref FROM ai_models WHERE id = ? AND deleted_at IS NULL",
                (model_id,),
            ).fetchone()
        if row is None:
            return None
        return self.secret_store.get_secret(row["api_key_secret_ref"])

    def _from_row(self, row) -> ModelConfig:
        secret_ref = row["api_key_secret_ref"]
        try:
            has_api_key = bool(secret_ref and self.secret_store.get_secret(secret_ref))
        except Exception:  # noqa: BLE001
            has_api_key = False
        return ModelConfig(
            id=row["id"],
            display_name=row["display_name"],
            provider=row["provider"],
            base_url=row["base_url"],
            model_name=row["model_name"],
            temperature=row["temperature"],
            max_tokens=row["max_tokens"],
            timeout_seconds=row["timeout_seconds"],
            is_default=bool(row["is_default"]),
            has_api_key=has_api_key,
        )

    def _api_key_name(self, model_id: int) -> str:
        database_identity = str(self.database_path.resolve()).casefold()
        database_fingerprint = hashlib.sha256(database_identity.encode("utf-8")).hexdigest()[:20]
        return f"database:{database_fingerprint}:model:{model_id}:api_key"
