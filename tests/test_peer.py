from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ensemble.config import default_config, load_config, save_config
from ensemble.opencode_config import write_opencode_config

ROOT = Path(__file__).resolve().parents[1]

STUB = r'''#!/usr/bin/env python3
import json, os, sys, time

args = sys.argv[1:]
log_path = os.environ.get("STUB_LOG")
if log_path:
    key_var = os.environ.get("STUB_KEY_VAR", "")
    payload = {
        "argv": args,
        "key_present": bool(os.environ.get(key_var)),
        "key_value": os.environ.get(key_var),
        "opencode_config": os.environ.get("OPENCODE_CONFIG"),
    }
    with open(log_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)

if os.environ.get("STUB_MUTATE"):
    with open("peer-created.txt", "w", encoding="utf-8") as handle:
        handle.write("changed")

if os.environ.get("STUB_SLEEP"):
    time.sleep(float(os.environ["STUB_SLEEP"]))

if os.environ.get("STUB_FAIL"):
    print("upstream exploded", file=sys.stderr)
    sys.exit(1)

events = [
    {
        "type": "step_start",
        "sessionID": "ses_stub",
        "part": {},
    },
    {
        "type": "text",
        "sessionID": "ses_stub",
        "part": {"type": "text", "text": "STUB REVIEW"},
    },
    {
        "type": "step_finish",
        "sessionID": "ses_stub",
        "part": {
            "cost": 0.0012,
            "tokens": {
                "input": 10,
                "output": 5,
                "reasoning": 0,
                "cache": {"read": 2, "write": 0},
            },
        },
    },
]
for event in events:
    print(json.dumps(event))
'''


@pytest.fixture
def harness(tmp_path, monkeypatch):
    config_home = tmp_path / "config"
    monkeypatch.setenv("ENSEMBLE_CONFIG_DIR", str(config_home))
    config = default_config()
    save_config(config)
    write_opencode_config(config)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "opencode"
    stub.write_text(STUB, encoding="utf-8")
    stub.chmod(0o755)
    monkeypatch.setenv("ENSEMBLE_OPENCODE_BIN", str(stub))
    monkeypatch.setenv("ENSEMBLE_DISABLE_KEYRING", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("STUB_KEY_VAR", "OPENROUTER_API_KEY")

    stub_log = tmp_path / "stub.json"
    monkeypatch.setenv("STUB_LOG", str(stub_log))

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("print('hi')\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    brief = tmp_path / "brief.md"
    brief.write_text("# Task\nReview the change.\n", encoding="utf-8")

    return SimpleNamespace(
        config_home=config_home,
        config=config,
        repo=repo,
        brief=brief,
        run_dir=tmp_path / "run",
        stub_log=stub_log,
        tmp_path=tmp_path,
    )


def _env() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT / "src") + (
        os.pathsep + existing if existing else ""
    )
    return env


def run_peer(harness, *extra: str, role: str = "reviewer") -> subprocess.CompletedProcess:
    command = [
        sys.executable,
        "-m",
        "ensemble.peer",
        "ask",
        "--role",
        role,
        "--cwd",
        str(harness.repo),
        "--brief",
        str(harness.brief),
        "--run-dir",
        str(harness.run_dir),
        "--file",
        str(harness.repo / "app.py"),
        *extra,
    ]
    return subprocess.run(
        command, capture_output=True, text=True, env=_env()
    )


def test_peer_success_writes_artifacts_and_injects_key(harness):
    result = run_peer(harness)
    assert result.returncode == 0, result.stderr
    assert "STUB REVIEW" in result.stdout

    prompt = (harness.run_dir / "01-reviewer.prompt.md").read_text(encoding="utf-8")
    assert "Review the change." in prompt
    assert "Do not modify files" in prompt

    reply = (harness.run_dir / "01-reviewer.md").read_text(encoding="utf-8")
    assert reply.strip() == "STUB REVIEW"

    raw = (harness.run_dir / "01-reviewer.raw.jsonl").read_text(encoding="utf-8")
    assert "step_finish" in raw

    meta = json.loads(
        (harness.run_dir / "01-reviewer.meta.json").read_text(encoding="utf-8")
    )
    assert meta["provider"] == "openrouter"
    assert meta["model"] == "tencent/hy4"
    assert meta["agent"] == "ensemble-reviewer"
    assert meta["exit_code"] == 0
    assert meta["cost_usd"] == pytest.approx(0.0012)
    assert meta["tokens"]["input"] == 10
    assert meta["tokens"]["cache_read"] == 2

    log = json.loads(harness.stub_log.read_text(encoding="utf-8"))
    assert "--standalone" in log["argv"]
    assert "openrouter/tencent/hy4" in log["argv"]
    assert "ensemble-reviewer" in log["argv"]
    assert "json" in log["argv"]
    assert log["key_present"] is True
    assert log["key_value"] == "test-key"
    assert log["opencode_config"].endswith("opencode.json")
    assert not (harness.repo / "peer-created.txt").exists()


def test_tree_guard_aborts_when_peer_mutates_repo(harness, monkeypatch):
    monkeypatch.setenv("STUB_MUTATE", "1")
    result = run_peer(harness)
    assert result.returncode == 4
    assert "Working tree changed" in result.stderr
    guard = harness.run_dir / "01-reviewer.tree-guard.txt"
    assert guard.exists()
    assert "peer-created.txt" in guard.read_text(encoding="utf-8")
    # Never auto-revert: the evidence is left in place.
    assert (harness.repo / "peer-created.txt").exists()


def test_timeout_kills_peer(harness, monkeypatch):
    config = load_config()
    config.prefs.timeout_seconds = 1
    save_config(config)
    monkeypatch.setenv("STUB_SLEEP", "5")
    result = run_peer(harness)
    assert result.returncode == 6
    assert "timed out" in result.stderr


def test_budget_blocks_next_turn(harness):
    harness.run_dir.mkdir(parents=True)
    (harness.run_dir / "00-old.meta.json").write_text(
        json.dumps({"cost_usd": 0.75}), encoding="utf-8"
    )
    result = run_peer(harness)
    assert result.returncode == 5
    assert "Budget reached" in result.stderr
    assert not harness.stub_log.exists()


def test_missing_key_fails_clearly(harness, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    result = run_peer(harness)
    assert result.returncode == 2
    assert "OPENROUTER_API_KEY" in result.stderr


def test_dry_run_redacts_key_and_writes_nothing(harness):
    result = run_peer(harness, "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "opencode" in result.stdout
    assert "<redacted>" in result.stdout
    assert "test-key" not in result.stdout
    assert not harness.stub_log.exists()
    assert not harness.run_dir.exists()


def test_peer_failure_reports_stderr(harness, monkeypatch):
    monkeypatch.setenv("STUB_FAIL", "1")
    result = run_peer(harness)
    assert result.returncode == 3
    assert "upstream exploded" in result.stderr


def test_unknown_role_is_config_error(harness):
    result = run_peer(harness, role="narrator")
    assert result.returncode == 2
    assert "Unknown role" in result.stderr


def test_relative_file_path_resolves_against_cwd(harness):
    command = [
        sys.executable,
        "-m",
        "ensemble.peer",
        "ask",
        "--role",
        "reviewer",
        "--cwd",
        str(harness.repo),
        "--brief",
        str(harness.brief),
        "--run-dir",
        str(harness.run_dir),
        "--file",
        "app.py",
        "--quiet",
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, env=_env()
    )
    assert result.returncode == 0, result.stderr
    assert (harness.run_dir / "01-reviewer.md").exists()
