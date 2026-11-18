"""Install the Claude Code skill for Ensemble."""

from __future__ import annotations

import os
import shutil
import sys
from importlib import resources
from pathlib import Path


class SkillError(Exception):
    """Raised when the skill cannot be installed."""


def claude_dir() -> Path:
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude"


def skill_path() -> Path:
    return claude_dir() / "skills" / "ensemble" / "SKILL.md"


def _bin_dir() -> Path | None:
    """Return the directory of the running console script, if detectable."""
    try:
        argv0 = Path(sys.argv[0]).resolve()
    except OSError:
        return None
    if (argv0.parent / "ensemble-peer").exists():
        return argv0.parent
    return None


def _resolve(name: str) -> str:
    bin_dir = _bin_dir()
    if bin_dir is not None:
        candidate = bin_dir / name
        if candidate.exists():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    return name


def render_skill() -> str:
    template = resources.files("ensemble").joinpath("skill_template.md").read_text(
        encoding="utf-8"
    )
    return (
        template.replace("{{ENSEMBLE_BIN}}", _resolve("ensemble"))
        .replace("{{ENSEMBLE_PEER}}", _resolve("ensemble-peer"))
    )


def install_skill(force: bool = False) -> tuple[Path, bool]:
    """Install SKILL.md. Returns (path, changed)."""
    destination = skill_path()
    content = render_skill()
    if destination.exists():
        existing = destination.read_text(encoding="utf-8")
        if existing == content:
            return destination, False
        if not force:
            raise SkillError(
                f"{destination} already exists with different content; "
                "re-run with --force to replace it"
            )
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(destination.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, destination)
    return destination, True
