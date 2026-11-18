from __future__ import annotations

from pathlib import Path

import pytest

from ensemble.config import default_config
from ensemble.launch import (
    LaunchError,
    build_launch_plan,
    redacted_preview,
    terminal_command,
)


def test_build_plan_uses_env_key_and_redacts(monkeypatch):
    monkeypatch.setenv("ENSEMBLE_DISABLE_KEYRING", "1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-key")
    config = default_config()
    plan = build_launch_plan(config)
    assert plan.source == "env:DEEPSEEK_API_KEY"
    assert plan.env["ANTHROPIC_AUTH_TOKEN"] == "synthetic-key"
    assert plan.env["ANTHROPIC_MODEL"] == config.roles["orchestrator"].model
    preview = "\n".join(redacted_preview(plan))
    assert "synthetic-key" not in preview
    assert "<redacted>" in preview


def test_missing_key_raises(monkeypatch):
    monkeypatch.setenv("ENSEMBLE_DISABLE_KEYRING", "1")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LaunchError):
        build_launch_plan(default_config())


def test_terminal_command_contains_no_secret(tmp_path: Path):
    command = terminal_command(
        tmp_path, "gnome-terminal", python_executable="/usr/bin/python3"
    )
    joined = " ".join(command)
    assert command[0] == "gnome-terminal"
    assert "--working-directory" in command
    assert "ensemble.cli" in joined
    assert "launch" in joined
    assert "synthetic-key" not in joined
