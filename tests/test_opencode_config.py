from __future__ import annotations

from ensemble.config import default_config
from ensemble.opencode_config import build_opencode_config


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


def test_generated_config_contains_no_secret_values(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "super-secret-value")
    payload = str(build_opencode_config(default_config()))
    assert "super-secret-value" not in payload
    assert "DEEPSEEK_API_KEY" in payload
