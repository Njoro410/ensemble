from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env(data_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT / "src") + (
        os.pathsep + existing if existing else ""
    )
    env["XDG_DATA_HOME"] = str(data_home)
    env["ENSEMBLE_DISABLE_KEYRING"] = "1"
    return env


def run_cli(data_home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "ensemble.cli", *args],
        capture_output=True,
        text=True,
        env=_env(data_home),
    )


def test_desktop_install_force_and_uninstall(tmp_path):
    data_home = tmp_path / "data"
    entry = data_home / "applications" / "ensemble.desktop"
    icon = (
        data_home / "icons" / "hicolor" / "scalable" / "apps" / "ensemble.svg"
    )

    first = run_cli(data_home, "desktop", "install")
    assert first.returncode == 0, first.stderr
    text = entry.read_text(encoding="utf-8")
    assert "Name=Ensemble" in text
    assert "Exec=" in text
    assert " gui" in text
    assert "Icon=ensemble" in text
    assert "StartupWMClass=Ensemble" in text
    assert icon.read_text(encoding="utf-8").startswith("<svg")

    second = run_cli(data_home, "desktop", "install")
    assert second.returncode == 0, second.stderr
    assert "Already up to date" in second.stdout

    entry.write_text("changed", encoding="utf-8")
    blocked = run_cli(data_home, "desktop", "install")
    assert blocked.returncode == 2
    assert "--force" in blocked.stderr

    forced = run_cli(data_home, "desktop", "install", "--force")
    assert forced.returncode == 0, forced.stderr

    removed = run_cli(data_home, "desktop", "uninstall")
    assert removed.returncode == 0, removed.stderr
    assert not entry.exists()
    assert not icon.exists()
