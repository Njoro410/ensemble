"""Shared launch planning for the CLI and the GTK control panel."""

from __future__ import annotations

import os
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import Config, Provider, RoleAssignment
from .secrets import resolve_secret


class LaunchError(Exception):
    """Raised when an orchestrator session cannot be planned."""


@dataclass
class LaunchPlan:
    assignment: RoleAssignment
    provider: Provider
    secret: str
    source: str
    env: dict[str, str]
    auth_var: str


def build_launch_plan(
    config: Config, base_env: dict[str, str] | None = None
) -> LaunchPlan:
    assignment = config.roles["orchestrator"]
    provider = config.providers[assignment.provider]
    environment = dict(base_env if base_env is not None else os.environ)

    secret, source = resolve_secret(provider)
    if not secret:
        ambient = environment.get("ANTHROPIC_AUTH_TOKEN") or environment.get(
            "ANTHROPIC_API_KEY"
        )
        if ambient:
            secret, source = ambient, "ambient"
    if not secret:
        raise LaunchError(
            f"No API key for orchestrator provider {provider.id!r}. Run "
            f"'ensemble key set {provider.id}' or export ${provider.env_var}."
        )

    if provider.base_url:
        environment["ANTHROPIC_BASE_URL"] = provider.base_url
    if provider.auth_style == "x-api-key":
        environment["ANTHROPIC_API_KEY"] = secret
        environment.pop("ANTHROPIC_AUTH_TOKEN", None)
        auth_var = "ANTHROPIC_API_KEY"
    else:
        environment["ANTHROPIC_AUTH_TOKEN"] = secret
        environment.pop("ANTHROPIC_API_KEY", None)
        auth_var = "ANTHROPIC_AUTH_TOKEN"

    model = assignment.model
    environment["ANTHROPIC_MODEL"] = model
    environment["ANTHROPIC_DEFAULT_OPUS_MODEL"] = model
    environment["ANTHROPIC_DEFAULT_SONNET_MODEL"] = model
    environment["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = (
        assignment.small_model or model
    )
    return LaunchPlan(
        assignment=assignment,
        provider=provider,
        secret=secret,
        source=source,
        env=environment,
        auth_var=auth_var,
    )


def redacted_preview(plan: LaunchPlan) -> list[str]:
    lines: list[str] = []
    for name in (
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    ):
        if name in plan.env:
            lines.append(f"{name}={plan.env[name]}")
    lines.append(f"{plan.auth_var}=<redacted>")
    lines.append(f"key source: {plan.source}")
    return lines


def terminal_command(
    repo: Path,
    terminal: str,
    python_executable: str | None = None,
) -> list[str]:
    """Build a terminal command that runs `ensemble launch` without secrets."""
    python = python_executable or sys.executable
    inner = (
        f"exec {shlex.quote(python)} -m ensemble.cli launch --repo "
        f"{shlex.quote(str(repo))}"
    )
    name = Path(terminal).name
    if name in {"gnome-terminal", "kgx", "tilix"}:
        return [
            terminal,
            "--working-directory",
            str(repo),
            "--",
            "bash",
            "-lc",
            inner,
        ]
    if name == "xfce4-terminal":
        return [
            terminal,
            "--working-directory",
            str(repo),
            "-e",
            f"bash -lc {shlex.quote(inner)}",
        ]
    return [terminal, "-e", f"bash -lc {shlex.quote(inner)}"]
