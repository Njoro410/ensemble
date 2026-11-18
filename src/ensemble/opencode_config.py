"""Generate an isolated opencode v2 config for read-only peer agents."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .backups import backup_file
from .config import Config, config_dir
from .roles import ROLE_AGENTS

OPENCODE_SCHEMA = "https://opencode.ai/config.json"

PROTOCOL_PACKAGES = {
    "openai": "@opencode/ai/providers/openai-compatible",
    "anthropic": "@opencode/ai/providers/anthropic-compatible",
}

READ_ONLY_PERMISSIONS = [
    {"action": "edit", "resource": "*", "effect": "deny"},
    {"action": "shell", "resource": "*", "effect": "deny"},
    {"action": "webfetch", "resource": "*", "effect": "deny"},
    {"action": "websearch", "resource": "*", "effect": "deny"},
]


class OpencodeConfigError(Exception):
    """Raised when the generated opencode config cannot be produced."""


def opencode_config_path() -> Path:
    return config_dir() / "opencode.json"


def build_opencode_config(config: Config) -> dict[str, Any]:
    providers: dict[str, Any] = {}
    for provider in config.providers.values():
        # Built-in providers (openrouter, anthropic, ...) keep opencode's
        # native catalog, variants, and auth handling. Only supply the key.
        if provider.kind == "builtin":
            continue
        if not provider.include_in_opencode:
            continue
        package = provider.package or PROTOCOL_PACKAGES[provider.protocol]
        entry: dict[str, Any] = {
            "name": provider.label,
            "env": [provider.env_var],
            "package": package,
            "settings": {"baseURL": provider.base_url},
        }
        if provider.headers:
            entry["headers"] = dict(provider.headers)
        if provider.models:
            suffix = provider.model_alias_suffix
            model_entries: dict[str, Any] = {}
            for model in provider.models:
                details: dict[str, Any] = {"name": model}
                if suffix and model.endswith(suffix):
                    upstream = model[: -len(suffix)]
                    if upstream:
                        details["modelID"] = upstream
                model_entries[model] = details
            entry["models"] = model_entries
        providers[provider.id] = entry

    agents: dict[str, Any] = {}
    for agent_id, system_prompt in ROLE_AGENTS.values():
        agents[agent_id] = {
            "description": (
                "Read-only ensemble collaborator. Denies edit and shell."
            ),
            "mode": "primary",
            "system": system_prompt,
            "permissions": [dict(rule) for rule in READ_ONLY_PERMISSIONS],
        }

    return {
        "$schema": OPENCODE_SCHEMA,
        "providers": providers,
        "agents": agents,
    }


def write_opencode_config(config: Config, path: Path | None = None) -> Path:
    target = path or opencode_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = build_opencode_config(config)
    text = json.dumps(payload, indent=2) + "\n"
    if target.exists():
        try:
            if target.read_text(encoding="utf-8") == text:
                return target
        except OSError:
            pass
        backup_file(target)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    return target
