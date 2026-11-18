from __future__ import annotations

from ensemble.config import Provider, RoleAssignment, default_config
from ensemble.roles import (
    PEER_ROLE_IDS,
    ROLE_ORDER,
    ROLE_SPECS,
    seed_assignments,
)


def test_role_catalog_has_thirteen_roles():
    assert len(ROLE_ORDER) == 13
    assert len(ROLE_SPECS) == 13
    assert len(PEER_ROLE_IDS) == 12
    assert "orchestrator" in ROLE_SPECS
    assert ROLE_SPECS["orchestrator"].agent == ""
    for role in PEER_ROLE_IDS:
        assert ROLE_SPECS[role].agent.startswith("ensemble-")


def test_seed_assignments_prefers_opencode_and_anthropic_orchestrator():
    config = default_config()
    config.providers["opencode-go"] = Provider(
        id="opencode-go",
        label="OpenCode Go",
        protocol="openai",
        env_var="OPENCODE_API_KEY",
        base_url="https://opencode.ai/inference/go/openai/v1",
        kind="custom",
        models=[
            "gemini-4-argon-go",
            "grok-4.7-go",
            "mimo-v2.6-flash-go",
        ],
    )
    config.providers["openrouter-anthropic"] = Provider(
        id="openrouter-anthropic",
        label="OpenRouter (Anthropic)",
        protocol="anthropic",
        env_var="OPENROUTER_API_KEY",
        base_url="https://openrouter.ai/api",
        kind="custom",
        key_ref="openrouter",
        models=["anthropic/claude-haiku-5.5"],
    )
    results = seed_assignments(config, force=True)
    assert config.roles["orchestrator"] == RoleAssignment(
        "openrouter-anthropic", "anthropic/claude-haiku-5.5"
    )
    assert config.roles["planner"].provider == "opencode-go"
    assert config.roles["planner"].model == "gemini-4-argon-go"
    assert config.roles["reviewer"].model == "grok-4.7-go"
    assert any(status == "assigned" for _r, _p, _m, status in results)
