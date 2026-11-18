from __future__ import annotations

import pytest

from ensemble.config import Provider
from ensemble.secrets import (
    SecretError,
    resolve_secret,
    secrets_file_path,
    set_secret,
)


def _provider() -> Provider:
    return Provider(
        id="acme",
        label="Acme",
        protocol="openai",
        env_var="ACME_API_KEY",
    )


def test_file_fallback_requires_explicit_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("ENSEMBLE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ENSEMBLE_DISABLE_KEYRING", "1")
    monkeypatch.delenv("ACME_API_KEY", raising=False)
    with pytest.raises(SecretError, match="allow-file"):
        set_secret(_provider(), "secret-value")


def test_file_fallback_roundtrip_and_permissions(tmp_path, monkeypatch):
    monkeypatch.setenv("ENSEMBLE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ENSEMBLE_DISABLE_KEYRING", "1")
    monkeypatch.delenv("ACME_API_KEY", raising=False)
    provider = _provider()
    set_secret(provider, "secret-value", allow_file=True)

    path = secrets_file_path()
    assert path.exists()
    assert (path.stat().st_mode & 0o777) == 0o600
    assert "secret-value" in path.read_text(encoding="utf-8")

    secret, source = resolve_secret(provider)
    assert secret == "secret-value"
    assert source == "protected-file"


def test_env_used_when_nothing_is_stored(tmp_path, monkeypatch):
    monkeypatch.setenv("ENSEMBLE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ENSEMBLE_DISABLE_KEYRING", "1")
    monkeypatch.setenv("ACME_API_KEY", "env-value")
    secret, source = resolve_secret(_provider())
    assert secret == "env-value"
    assert source == "env:ACME_API_KEY"
