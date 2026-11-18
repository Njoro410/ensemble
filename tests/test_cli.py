from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env(config_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT / "src") + (
        os.pathsep + existing if existing else ""
    )
    env["ENSEMBLE_CONFIG_DIR"] = str(config_home)
    env["ENSEMBLE_DISABLE_KEYRING"] = "1"
    return env


def run_cli(config_home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "ensemble.cli", *args],
        capture_output=True,
        text=True,
        env=_env(config_home),
    )


def test_init_apply_and_doctor(tmp_path):
    config_home = tmp_path / "config"
    result = run_cli(config_home, "init")
    assert result.returncode == 0, result.stderr
    config_file = config_home / "config.json"
    assert config_file.exists()
    mode = config_file.stat().st_mode & 0o777
    assert mode == 0o600

    result = run_cli(config_home, "opencode", "apply")
    assert result.returncode == 0, result.stderr
    generated = config_home / "opencode.json"
    assert generated.exists()
    data = json.loads(generated.read_text(encoding="utf-8"))
    assert "ensemble-reviewer" in data["agents"]
    assert "ensemble-test-runner" in data["agents"]

    result = run_cli(config_home, "doctor")
    assert result.returncode == 0, result.stderr
    assert "[ok] config valid" in result.stdout


def test_roles_set_rejects_openai_orchestrator(tmp_path):
    config_home = tmp_path / "config"
    assert run_cli(config_home, "init").returncode == 0
    result = run_cli(
        config_home,
        "roles",
        "set",
        "orchestrator",
        "openrouter",
        "tencent/hy4",
    )
    assert result.returncode == 2
    assert "Anthropic-compatible" in result.stderr


def test_roles_catalog_lists_all_roles(tmp_path):
    config_home = tmp_path / "config"
    assert run_cli(config_home, "init").returncode == 0
    result = run_cli(config_home, "roles", "catalog")
    assert result.returncode == 0, result.stderr
    assert "planner | Planner | core" in result.stdout
    assert "security_reviewer | Security Reviewer | specialized" in result.stdout
    assert "(unassigned)" in result.stdout


def test_providers_add_preset(tmp_path):
    config_home = tmp_path / "config"
    assert run_cli(config_home, "init").returncode == 0
    result = run_cli(config_home, "providers", "add", "--preset", "opencode-go")
    assert result.returncode == 0, result.stderr
    data = json.loads((config_home / "config.json").read_text(encoding="utf-8"))
    provider = data["providers"]["opencode-go"]
    assert provider["kind"] == "custom"
    assert provider["protocol"] == "openai"
    assert provider["headers"] == {"x-opencode-session": "ensemble"}
    assert provider["models_url"].startswith("https://opencode.ai/")


def test_presets_list(tmp_path):
    result = run_cli(tmp_path / "config", "presets", "list")
    assert result.returncode == 0, result.stderr
    assert "openrouter" in result.stdout
    assert "opencode" in result.stdout
    assert "deepseek" in result.stdout


def test_launch_dry_run_redacts_key(tmp_path, monkeypatch):
    config_home = tmp_path / "config"
    assert run_cli(config_home, "init").returncode == 0
    env = _env(config_home)
    env["DEEPSEEK_API_KEY"] = "synthetic-deepseek-key"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ensemble.cli",
            "launch",
            "--dry-run",
            "--repo",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "ANTHROPIC_BASE_URL=" in result.stdout
    assert "ANTHROPIC_AUTH_TOKEN=<redacted>" in result.stdout
    assert "synthetic-deepseek-key" not in result.stdout
