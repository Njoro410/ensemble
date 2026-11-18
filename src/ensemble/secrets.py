"""OS keyring access. Secrets never touch config files or argv."""

from __future__ import annotations

import os

from .config import Provider


class SecretError(Exception):
    """Raised when a secret cannot be stored or read."""


SERVICE = "ensemble"


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
            # A locked or unavailable keyring should not prevent env fallback.
            pass

    from_env = os.environ.get(provider.env_var)
    if from_env:
        return from_env, f"env:{provider.env_var}"
    return None, "missing"


def set_secret(provider: Provider, secret: str) -> None:
    if not secret:
        raise SecretError("Refusing to store an empty secret")
    if _keyring_disabled():
        raise SecretError(
            "The OS keyring is disabled by ENSEMBLE_DISABLE_KEYRING=1. "
            f"Export {provider.env_var} instead."
        )
    try:
        keyring = _keyring()
        keyring.set_password(SERVICE, provider.id, secret)
    except Exception as exc:
        raise SecretError(
            f"Could not store the key in the OS keyring ({exc}). "
            "Unlock the keyring, or export "
            f"{provider.env_var} instead."
        ) from exc


def delete_secret(provider_id: str) -> None:
    if _keyring_disabled():
        raise SecretError("The OS keyring is disabled")
    try:
        keyring = _keyring()
        keyring.delete_password(SERVICE, provider_id)
    except Exception as exc:
        raise SecretError(f"Could not delete the key from the keyring: {exc}") from exc


def import_from_env(provider: Provider) -> str:
    value = os.environ.get(provider.env_var)
    if not value:
        raise SecretError(
            f"${provider.env_var} is not set in this shell; nothing to import"
        )
    set_secret(provider, value)
    return provider.env_var
