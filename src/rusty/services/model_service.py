from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rusty.db import initialize_database, session
from rusty.secrets import SecretStore, default_secret_store
from rusty.services.project_service import default_database_path


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
        with session(self.database_path) as connection:
            initialize_database(connection)

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
                ref = self.secret_store.set_secret(f"model:{model_id}:api_key", api_key)
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
                if secret_ref:
                    self.secret_store.delete_secret(secret_ref)
                secret_ref = self.secret_store.set_secret(f"model:{model_id}:api_key", api_key)

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
                self.secret_store.delete_secret(row["api_key_secret_ref"])
            connection.execute(
                "UPDATE ai_models SET deleted_at = CURRENT_TIMESTAMP, is_default = 0 WHERE id = ?",
                (model_id,),
            )

    def set_default(self, model_id: int) -> None:
        with session(self.database_path) as connection:
            connection.execute("UPDATE ai_models SET is_default = 0 WHERE deleted_at IS NULL")
            connection.execute(
                "UPDATE ai_models SET is_default = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND deleted_at IS NULL",
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

    def get_api_key(self, model_id: int) -> str | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT api_key_secret_ref FROM ai_models WHERE id = ? AND deleted_at IS NULL",
                (model_id,),
            ).fetchone()
        if row is None:
            return None
        return self.secret_store.get_secret(row["api_key_secret_ref"])

    def test_connection(self, model_id: int, ai_client=None) -> ModelTestResult:
        from rusty.services.ai_client import OpenAICompatibleClient

        model = self.get_model(model_id)
        if model is None:
            raise ValueError(f"Model not found: {model_id}")
        client = ai_client or OpenAICompatibleClient()
        try:
            response = client.chat(
                model,
                self.get_api_key(model_id),
                [
                    {
                        "role": "user",
                        "content": "Reply with OK to confirm this model connection works.",
                    }
                ],
            )
        except Exception as exc:  # noqa: BLE001
            return ModelTestResult(ok=False, message=str(exc), elapsed_ms=None)
        return ModelTestResult(ok=True, message=response.text.strip(), elapsed_ms=response.elapsed_ms)

    @staticmethod
    def _from_row(row) -> ModelConfig:
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
            has_api_key=bool(row["api_key_secret_ref"]),
        )
