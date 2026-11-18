"""OS keyring access. Secrets never touch config files or argv."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .config import Provider, config_dir


class SecretError(Exception):
    """Raised when a secret cannot be stored or read."""


SERVICE = "ensemble"


def secrets_file_path() -> Path:
    return config_dir() / "secrets.json"


def _load_file_secrets() -> dict[str, str]:
    path = secrets_file_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in data.items()
        if isinstance(value, str)
    }


def _write_file_secrets(data: dict[str, str]) -> None:
    path = secrets_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _store_file_secret(provider_id: str, secret: str) -> None:
    data = _load_file_secrets()
    data[provider_id] = secret
    _write_file_secrets(data)


def _delete_file_secret(provider_id: str) -> None:
    data = _load_file_secrets()
    if provider_id not in data:
        return
    del data[provider_id]
    if data:
        _write_file_secrets(data)
    else:
        try:
            secrets_file_path().unlink()
        except OSError:
            pass


def _keyring_disabled() -> bool:
    return os.environ.get("ENSEMBLE_DISABLE_KEYRING") == "1"


def _keyring():
    try:
        import keyring
    except Exception as exc:  # pragma: no cover - declared dependency
        raise SecretError(
            "The 'keyring' package is not installed. Run: pip install keyring"
        ) from exc
    return keyring


def keyring_description() -> str:
    if _keyring_disabled():
        return "disabled by ENSEMBLE_DISABLE_KEYRING=1"
    try:
        keyring = _keyring()
        backend = keyring.get_keyring()
        return f"{backend.__class__.__module__}.{backend.__class__.__name__}"
    except Exception as exc:
        return f"unavailable ({exc})"


def keyring_available() -> bool:
    if _keyring_disabled():
        return False
    try:
        keyring = _keyring()
        backend = keyring.get_keyring()
        return getattr(backend, "priority", 0) > 0
    except Exception:
        return False


def resolve_secret(provider: Provider) -> tuple[str | None, str]:
    """Return (secret, source). Source is 'keyring', 'env:VAR', or 'missing'."""
    if not _keyring_disabled():
        try:
            keyring = _keyring()
            stored = keyring.get_password(SERVICE, provider.id)
            if stored:
                return stored, "keyring"
        except Exception:
            # A locked or unavailable keyring should not prevent fallback.
            pass

    file_secrets = _load_file_secrets()
    protected = file_secrets.get(provider.id)
    if protected:
        return protected, "protected-file"

    from_env = os.environ.get(provider.env_var)
    if from_env:
        return from_env, f"env:{provider.env_var}"
    return None, "missing"


def set_secret(
    provider: Provider, secret: str, allow_file: bool = False
) -> None:
    if not secret:
        raise SecretError("Refusing to store an empty secret")
    keyring_error: Exception | None = None
    if not _keyring_disabled():
        try:
            keyring = _keyring()
            keyring.set_password(SERVICE, provider.id, secret)
            _delete_file_secret(provider.id)
            return
        except Exception as exc:
            keyring_error = exc
    if allow_file:
        _store_file_secret(provider.id, secret)
        return
    reason = f" ({keyring_error})" if keyring_error else " (disabled)"
    raise SecretError(
        "Could not store the key in the OS keyring"
        + reason
        + f". Export {provider.env_var}, or pass --allow-file to store it in "
        "a protected 0600 file."
    )


def delete_secret(provider_id: str) -> None:
    if not _keyring_disabled():
        try:
            keyring = _keyring()
            keyring.delete_password(SERVICE, provider_id)
        except Exception:
            pass
    _delete_file_secret(provider_id)


def import_from_env(provider: Provider, allow_file: bool = False) -> str:
    value = os.environ.get(provider.env_var)
    if not value:
        raise SecretError(
            f"${provider.env_var} is not set in this shell; nothing to import"
        )
    set_secret(provider, value, allow_file=allow_file)
    return provider.env_var
