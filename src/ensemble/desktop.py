"""Install a .desktop entry and icon for the GTK control panel."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

DESKTOP_NAME = "ensemble.desktop"
ICON_NAME = "ensemble.svg"


class DesktopError(Exception):
    """Raised when the desktop entry cannot be installed."""


def data_home() -> Path:
    override = os.environ.get("XDG_DATA_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "share"


def desktop_path() -> Path:
    return data_home() / "applications" / DESKTOP_NAME


def icon_path() -> Path:
    return data_home() / "icons" / "hicolor" / "scalable" / "apps" / ICON_NAME


def _desktop_quote(value: str) -> str:
    if not value:
        return '""'
    special = set(' \t\n"\'\\><~|&;$*?#()`')
    if not (set(value) & special):
        return value
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
    )
    return f'"{escaped}"'


def _exec_line() -> str:
    argv0 = Path(sys.argv[0]).resolve()
    sibling = argv0.parent / "ensemble"
    if sibling.exists():
        return f"{_desktop_quote(str(sibling))} gui"
    found = shutil.which("ensemble")
    if found:
        return f"{_desktop_quote(found)} gui"
    return f"{_desktop_quote(sys.executable)} -m ensemble.cli gui"


def desktop_content() -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=Ensemble\n"
        "Comment=Multi-provider agent orchestration control panel\n"
        f"Exec={_exec_line()}\n"
        "Icon=ensemble\n"
        "Terminal=false\n"
        "Categories=Development;\n"
        "Keywords=AI;agents;Claude;opencode;providers;\n"
        "StartupNotify=true\n"
        "StartupWMClass=Ensemble\n"
    )


def icon_content() -> str:
    return resources.files("ensemble").joinpath("data/ensemble.svg").read_text(
        encoding="utf-8"
    )


def install_desktop(force: bool = False) -> tuple[Path, Path, bool]:
    entry = desktop_path()
    icon = icon_path()
    content = desktop_content()
    icon_data = icon_content()
    if entry.exists() and not force:
        try:
            existing = entry.read_text(encoding="utf-8")
        except OSError:
            existing = ""
        if existing != content:
            raise DesktopError(
                f"{entry} already exists with different content; "
                "re-run with --force to replace it"
            )

    changed = False
    for path, text in ((entry, content), (icon, icon_data)):
        if path.exists():
            try:
                if path.read_text(encoding="utf-8") == text:
                    continue
            except OSError:
                pass
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
        changed = True

    if changed:
        updater = shutil.which("update-desktop-database")
        if updater:
            try:
                subprocess.run(
                    [updater, str(entry.parent)],
                    capture_output=True,
                    timeout=10,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
    return entry, icon, changed


def uninstall_desktop() -> list[Path]:
    removed: list[Path] = []
    for path in (desktop_path(), icon_path()):
        try:
            path.unlink()
            removed.append(path)
        except FileNotFoundError:
            pass
    if removed:
        updater = shutil.which("update-desktop-database")
        if updater:
            try:
                subprocess.run(
                    [updater, str(desktop_path().parent)],
                    capture_output=True,
                    timeout=10,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
    return removed
