"""Timestamped backups for generated configuration files."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_KEEP = 5


def backups_dir(path: Path) -> Path:
    return path.parent / "backups"


def backup_file(path: Path, keep: int = DEFAULT_KEEP) -> Path | None:
    """Copy an existing file into <dir>/backups and prune old copies."""
    if not path.is_file():
        return None
    directory = backups_dir(path)
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = directory / f"{path.name}.{stamp}.bak"
    shutil.copy2(path, target)
    os.chmod(target, 0o600)
    prune_backups(path, keep)
    return target


def prune_backups(path: Path, keep: int = DEFAULT_KEEP) -> None:
    if keep <= 0:
        return
    directory = backups_dir(path)
    if not directory.is_dir():
        return
    candidates = sorted(
        directory.glob(f"{path.name}.*.bak"),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    )
    for stale in candidates[keep:]:
        try:
            stale.unlink()
        except OSError:
            pass


def list_backups(path: Path) -> list[Path]:
    directory = backups_dir(path)
    if not directory.is_dir():
        return []
    return sorted(
        directory.glob(f"{path.name}.*.bak"),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    )
