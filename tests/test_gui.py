from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _env(config_home: Path, claude_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT / "src") + (
        os.pathsep + existing if existing else ""
    )
    env["ENSEMBLE_CONFIG_DIR"] = str(config_home)
    env["CLAUDE_CONFIG_DIR"] = str(claude_home)
    env["ENSEMBLE_DISABLE_KEYRING"] = "1"
    env["DEEPSEEK_API_KEY"] = "synthetic-key"
    return env


def test_gui_module_imports():
    pytest.importorskip("gi")
    from ensemble import gui

    assert callable(gui.main)
    assert callable(gui.smoke_test)


def test_gui_smoke_under_xvfb(tmp_path):
    if not shutil.which("xvfb-run"):
        pytest.skip("xvfb-run not available")
    pytest.importorskip("gi")

    config_home = tmp_path / "config"
    claude_home = tmp_path / "claude"
    env = _env(config_home, claude_home)

    init = subprocess.run(
        [sys.executable, "-m", "ensemble.cli", "init"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert init.returncode == 0, init.stderr

    result = subprocess.run(
        [
            shutil.which("xvfb-run"),
            "-a",
            sys.executable,
            "-m",
            "ensemble.cli",
            "gui",
            "--smoke-test",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    assert "GUI smoke test completed" in result.stdout


def test_gui_apply_writes_config_and_skill(tmp_path):
    if not shutil.which("xvfb-run"):
        pytest.skip("xvfb-run not available")
    pytest.importorskip("gi")

    config_home = tmp_path / "config"
    claude_home = tmp_path / "claude"
    env = _env(config_home, claude_home)

    init = subprocess.run(
        [sys.executable, "-m", "ensemble.cli", "init"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert init.returncode == 0, init.stderr

    script = (
        "import gi\n"
        "gi.require_version('Gtk', '3.0')\n"
        "from gi.repository import Gtk\n"
        "from ensemble.gui import MainWindow\n"
        "Gtk.init([])\n"
        "window = MainWindow(None)\n"
        "ok = window.apply_all()\n"
        "print('APPLY_OK' if ok else 'APPLY_FAILED')\n"
        "window.destroy()\n"
    )
    result = subprocess.run(
        [shutil.which("xvfb-run"), "-a", sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    assert "APPLY_OK" in result.stdout
    assert (config_home / "opencode.json").exists()
    assert (claude_home / "skills" / "ensemble" / "SKILL.md").exists()
