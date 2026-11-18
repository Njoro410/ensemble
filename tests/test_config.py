from __future__ import annotations

import pytest

from ensemble.config import (
    ConfigError,
    Provider,
    RoleAssignment,
    default_config,
    load_config,
    save_config,
)


def test_default_config_is_valid(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    config = default_config()
    config.validate()
    assert config.roles["orchestrator"].provider == "deepseek"
    assert config.roles["reviewer"].model == "tencent/hy4"
    assert config.providers["openrouter"].kind == "builtin"


def test_orchestrator_must_be_anthropic_compatible():
    config = default_config()
    config.roles["orchestrator"] = RoleAssignment("openrouter", "tencent/hy4")
    with pytest.raises(ConfigError, match="Anthropic-compatible"):
        config.validate()


def test_unknown_role_provider_is_rejected():
    config = default_config()
    config.roles["reviewer"] = RoleAssignment("nope", "some-model")
    with pytest.raises(ConfigError, match="unknown provider"):
        config.validate()


def test_custom_provider_requires_base_url():
    config = default_config()
    config.providers["acme"] = Provider(
        id="acme",
        label="Acme",
        protocol="openai",
        env_var="ACME_API_KEY",
    )
    with pytest.raises(ConfigError, match="base_url"):
        config.validate()


def test_roundtrip_and_permissions(tmp_path, monkeypatch):
    monkeypatch.setenv("ENSEMBLE_CONFIG_DIR", str(tmp_path / "cfg"))
    config = default_config()
    path = save_config(config)
    loaded = load_config()
    assert loaded.to_dict() == config.to_dict()
    assert path.exists()
    assert (path.stat().st_mode & 0o777) == 0o600
