from __future__ import annotations

from ensemble.config import default_config
from ensemble.opencode_config import build_opencode_config
from ensemble.presets import provider_from_preset
from ensemble.roles import PEER_ROLE_IDS


def test_all_peer_roles_get_read_only_agents():
    data = build_opencode_config(default_config())
    assert len(data["agents"]) == len(PEER_ROLE_IDS)
    for agent in data["agents"].values():
        assert agent["mode"] == "primary"
        assert {
            "action": "edit",
            "resource": "*",
            "effect": "deny",
        } in agent["permissions"]
        assert {
            "action": "shell",
            "resource": "*",
            "effect": "deny",
        } in agent["permissions"]


def test_agents_deny_edit_and_shell():
    data = build_opencode_config(default_config())
    for agent_id in ("ensemble-reviewer", "ensemble-test-runner"):
        agent = data["agents"][agent_id]
        assert agent["mode"] == "primary"
        assert {
            "action": "edit",
            "resource": "*",
            "effect": "deny",
        } in agent["permissions"]
        assert {
            "action": "shell",
            "resource": "*",
            "effect": "deny",
        } in agent["permissions"]


def test_custom_provider_shape_and_builtin_omitted():
    data = build_opencode_config(default_config())
    # Built-in providers keep opencode's native catalog.
    assert "openrouter" not in data["providers"]

    deepseek = data["providers"]["deepseek"]
    assert deepseek["env"] == ["DEEPSEEK_API_KEY"]
    assert deepseek["package"] == "@opencode/ai/providers/anthropic-compatible"
    assert deepseek["settings"]["baseURL"].startswith("https://")
    assert "deepseek-flash" in deepseek["models"]


def test_custom_provider_headers_are_emitted():
    config = default_config()
    config.providers["opencode-go"] = provider_from_preset(
        "opencode-go", models=["mimo-v2.6-flash-go"]
    )
    data = build_opencode_config(config)
    entry = data["providers"]["opencode-go"]
    assert entry["headers"] == {"x-opencode-session": "ensemble"}
    assert entry["settings"]["baseURL"].endswith("/openai/v1")
    assert "mimo-v2.6-flash-go" in entry["models"]


def test_orchestrator_only_provider_is_omitted():
    config = default_config()
    config.providers["opencode-anthropic"] = provider_from_preset(
        "opencode-anthropic", models=["claude-haiku-5-5"]
    )
    data = build_opencode_config(config)
    assert "opencode-anthropic" not in data["providers"]


def test_model_aliases_emit_model_id():
    config = default_config()
    config.providers["opencode-go"] = provider_from_preset(
        "opencode-go", models=["gemini-4-argon-go", "mimo-v2.6-flash-go"]
    )
    data = build_opencode_config(config)
    models = data["providers"]["opencode-go"]["models"]
    assert models["gemini-4-argon-go"] == {
        "name": "gemini-4-argon-go",
        "modelID": "gemini-4-argon",
    }
    assert models["mimo-v2.6-flash-go"]["modelID"] == "mimo-v2.6-flash"


def test_generated_config_contains_no_secret_values(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "super-secret-value")
    payload = str(build_opencode_config(default_config()))
    assert "super-secret-value" not in payload
    assert "DEEPSEEK_API_KEY" in payload
