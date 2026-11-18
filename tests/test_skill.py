from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env(claude_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT / "src") + (
        os.pathsep + existing if existing else ""
    )
    env["CLAUDE_CONFIG_DIR"] = str(claude_home)
    env["ENSEMBLE_DISABLE_KEYRING"] = "1"
    return env


def run_cli(claude_home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "ensemble.cli", *args],
        capture_output=True,
        text=True,
        env=_env(claude_home),
    )


def test_skill_install_and_idempotent(tmp_path):
    claude_home = tmp_path / "claude"
    destination = claude_home / "skills" / "ensemble" / "SKILL.md"

    first = run_cli(claude_home, "skill", "install")
    assert first.returncode == 0, first.stderr
    assert destination.exists()
    text = destination.read_text(encoding="utf-8")
    assert text.startswith("---\nname: ensemble")
    assert "{{ENSEMBLE_BIN}}" not in text
    assert "{{ENSEMBLE_PEER}}" not in text
    assert "edit`/`shell` denied" in text
    assert "Mode: goal" in text
    assert "roles catalog" in text

    second = run_cli(claude_home, "skill", "install")
    assert second.returncode == 0, second.stderr
    assert "Already up to date" in second.stdout


def test_skill_install_requires_force_for_local_changes(tmp_path):
    claude_home = tmp_path / "claude"
    destination = claude_home / "skills" / "ensemble" / "SKILL.md"
    destination.parent.mkdir(parents=True)
    destination.write_text("locally edited", encoding="utf-8")

    blocked = run_cli(claude_home, "skill", "install")
    assert blocked.returncode == 2
    assert "--force" in blocked.stderr
    assert destination.read_text(encoding="utf-8") == "locally edited"

    forced = run_cli(claude_home, "skill", "install", "--force")
    assert forced.returncode == 0, forced.stderr
    assert destination.read_text(encoding="utf-8").startswith("---\nname: ensemble")
