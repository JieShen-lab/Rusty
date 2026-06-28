from __future__ import annotations

from dataclasses import dataclass, field

SERVICE_NAME = "rusty-novel"


class SecretStore:
    def set_secret(self, key: str, value: str) -> str:
        raise NotImplementedError

    def get_secret(self, ref: str | None) -> str | None:
        raise NotImplementedError

    def delete_secret(self, ref: str | None) -> None:
        raise NotImplementedError


class KeyringSecretStore(SecretStore):
    def set_secret(self, key: str, value: str) -> str:
        import keyring

        keyring.set_password(SERVICE_NAME, key, value)
        return f"keyring:{SERVICE_NAME}:{key}"

    def get_secret(self, ref: str | None) -> str | None:
        if not ref:
            return None
        key = _key_from_ref(ref)
        if key is None:
            return None

        import keyring

        return keyring.get_password(SERVICE_NAME, key)

    def delete_secret(self, ref: str | None) -> None:
        if not ref:
            return
        key = _key_from_ref(ref)
        if key is None:
            return

        import keyring

        try:
            keyring.delete_password(SERVICE_NAME, key)
        except keyring.errors.PasswordDeleteError:
            return


@dataclass
class InMemorySecretStore(SecretStore):
    values: dict[str, str] = field(default_factory=dict)

    def set_secret(self, key: str, value: str) -> str:
        self.values[key] = value
        return f"memory:{key}"

    def get_secret(self, ref: str | None) -> str | None:
        if not ref:
            return None
        if ref.startswith("memory:"):
            return self.values.get(ref.removeprefix("memory:"))
        return None

    def delete_secret(self, ref: str | None) -> None:
        if ref and ref.startswith("memory:"):
            self.values.pop(ref.removeprefix("memory:"), None)


def default_secret_store() -> SecretStore:
    return KeyringSecretStore()


def _key_from_ref(ref: str) -> str | None:
    prefix = f"keyring:{SERVICE_NAME}:"
    if not ref.startswith(prefix):
        return None
    return ref.removeprefix(prefix)

