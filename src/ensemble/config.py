"""Configuration schema, defaults, and validation for Ensemble."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REQUIRED_ROLES = ("orchestrator", "reviewer", "test_runner")
PROTOCOLS = ("anthropic", "openai")
KINDS = ("custom", "builtin")
AUTH_STYLES = ("bearer", "x-api-key")
PROVIDER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

OPENROUTER_MODELS = [
    "tencent/hy4",
    "tencent/hy4-flash",
    "xiaomi/mimo-v2.6-flash",
    "xiaomi/mimo-v2.5-pro",
]
DEEPSEEK_MODELS = ["deepseek-flash", "deepseek-v4-pro"]


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""


def config_dir() -> Path:
    override = os.environ.get("ENSEMBLE_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "ensemble"


def config_path() -> Path:
    return config_dir() / "config.json"


@dataclass
class Provider:
    id: str
    label: str
    protocol: str
    env_var: str
    base_url: str = ""
    kind: str = "custom"
    package: str = ""
    auth_style: str = "bearer"
    models: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "protocol": self.protocol,
            "env_var": self.env_var,
            "base_url": self.base_url,
            "kind": self.kind,
            "package": self.package,
            "auth_style": self.auth_style,
            "models": list(self.models),
        }

    @classmethod
    def from_dict(cls, provider_id: str, data: dict[str, Any]) -> "Provider":
        default_kind = "builtin" if provider_id == "openrouter" else "custom"
        return cls(
            id=provider_id,
            label=str(data.get("label") or provider_id),
            protocol=str(data.get("protocol") or "openai"),
            env_var=str(data.get("env_var") or "")
            or f"{provider_id.upper().replace('-', '_')}_API_KEY",
            base_url=str(data.get("base_url") or ""),
            kind=str(data.get("kind") or default_kind),
            package=str(data.get("package") or ""),
            auth_style=str(data.get("auth_style") or "bearer"),
            models=[str(model) for model in (data.get("models") or [])],
        )


@dataclass
class RoleAssignment:
    provider: str
    model: str
    small_model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
        }
        if self.small_model:
            payload["small_model"] = self.small_model
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RoleAssignment":
        return cls(
            provider=str(data.get("provider") or ""),
            model=str(data.get("model") or ""),
            small_model=(
                str(data["small_model"]) if data.get("small_model") else None
            ),
        )


@dataclass
class Prefs:
    default_repo: str | None = None
    terminal: str = "gnome-terminal"
    timeout_seconds: int = 180
    max_files: int = 20
    max_brief_bytes: int = 102_400
    budget_usd: float = 0.50

    def to_dict(self) -> dict[str, Any]:
        return {
            "default_repo": self.default_repo,
            "terminal": self.terminal,
            "timeout_seconds": self.timeout_seconds,
            "max_files": self.max_files,
            "max_brief_bytes": self.max_brief_bytes,
            "budget_usd": self.budget_usd,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Prefs":
        return cls(
            default_repo=(str(data["default_repo"]) if data.get("default_repo") else None),
            terminal=str(data.get("terminal") or "gnome-terminal"),
            timeout_seconds=int(data.get("timeout_seconds", 180)),
            max_files=int(data.get("max_files", 20)),
            max_brief_bytes=int(data.get("max_brief_bytes", 102_400)),
            budget_usd=float(data.get("budget_usd", 0.50)),
        )


@dataclass
class Config:
    version: int = 1
    providers: dict[str, Provider] = field(default_factory=dict)
    roles: dict[str, RoleAssignment] = field(default_factory=dict)
    prefs: Prefs = field(default_factory=Prefs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "providers": {
                provider_id: provider.to_dict()
                for provider_id, provider in self.providers.items()
            },
            "roles": {
                role: assignment.to_dict()
                for role, assignment in self.roles.items()
            },
            "prefs": self.prefs.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        providers = {
            provider_id: Provider.from_dict(provider_id, provider_data)
            for provider_id, provider_data in (data.get("providers") or {}).items()
        }
        roles = {
            role: RoleAssignment.from_dict(role_data)
            for role, role_data in (data.get("roles") or {}).items()
        }
        return cls(
            version=int(data.get("version", 1)),
            providers=providers,
            roles=roles,
            prefs=Prefs.from_dict(data.get("prefs") or {}),
        )

    def validate(self) -> None:
        if self.version != 1:
            raise ConfigError(f"Unsupported config version: {self.version}")
        if not self.providers:
            raise ConfigError("At least one provider is required")

        for provider_id, provider in self.providers.items():
            if not PROVIDER_ID_RE.match(provider_id):
                raise ConfigError(
                    f"Provider id {provider_id!r} must match {PROVIDER_ID_RE.pattern}"
                )
            if provider.protocol not in PROTOCOLS:
                raise ConfigError(
                    f"Provider {provider_id!r} has unknown protocol "
                    f"{provider.protocol!r} (expected one of {PROTOCOLS})"
                )
            if provider.kind not in KINDS:
                raise ConfigError(
                    f"Provider {provider_id!r} has unknown kind {provider.kind!r}"
                )
            if provider.auth_style not in AUTH_STYLES:
                raise ConfigError(
                    f"Provider {provider_id!r} has unknown auth style "
                    f"{provider.auth_style!r}"
                )
            if not provider.env_var:
                raise ConfigError(f"Provider {provider_id!r} needs an env_var name")
            if provider.kind == "custom" and not provider.base_url:
                raise ConfigError(
                    f"Custom provider {provider_id!r} needs base_url"
                )
            if any(not model.strip() for model in provider.models):
                raise ConfigError(f"Provider {provider_id!r} has an empty model id")
            if len(set(provider.models)) != len(provider.models):
                raise ConfigError(f"Provider {provider_id!r} has duplicate models")

        for role in REQUIRED_ROLES:
            if role not in self.roles:
                raise ConfigError(f"Missing required role: {role!r}")
            assignment = self.roles[role]
            if assignment.provider not in self.providers:
                raise ConfigError(
                    f"Role {role!r} references unknown provider "
                    f"{assignment.provider!r}"
                )
            if not assignment.model.strip():
                raise ConfigError(f"Role {role!r} needs a model id")

        orchestrator = self.roles["orchestrator"]
        orchestrator_provider = self.providers[orchestrator.provider]
        if orchestrator_provider.protocol != "anthropic":
            raise ConfigError(
                "The orchestrator role requires an Anthropic-compatible provider "
                f"(got protocol {orchestrator_provider.protocol!r})"
            )

        if self.prefs.timeout_seconds <= 0:
            raise ConfigError("prefs.timeout_seconds must be positive")
        if self.prefs.max_files <= 0:
            raise ConfigError("prefs.max_files must be positive")
        if self.prefs.max_brief_bytes <= 0:
            raise ConfigError("prefs.max_brief_bytes must be positive")
        if self.prefs.budget_usd < 0:
            raise ConfigError("prefs.budget_usd cannot be negative")


def default_config() -> Config:
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip().rstrip("/")
    model = os.environ.get("ANTHROPIC_MODEL", "").strip()

    deepseek_models = list(DEEPSEEK_MODELS)
    if model and model not in deepseek_models:
        deepseek_models.insert(0, model)
    orchestrator_model = model or deepseek_models[0]

    providers = {
        "deepseek": Provider(
            id="deepseek",
            label="DeepSeek",
            protocol="anthropic",
            env_var="DEEPSEEK_API_KEY",
            base_url=base_url or "https://api.deepseek.com",
            kind="custom",
            auth_style="bearer",
            models=deepseek_models,
        ),
        "openrouter": Provider(
            id="openrouter",
            label="OpenRouter",
            protocol="openai",
            env_var="OPENROUTER_API_KEY",
            base_url="https://openrouter.ai/api/v1",
            kind="builtin",
            auth_style="bearer",
            models=list(OPENROUTER_MODELS),
        ),
    }
    roles = {
        "orchestrator": RoleAssignment("deepseek", orchestrator_model),
        "reviewer": RoleAssignment("openrouter", "tencent/hy4"),
        "test_runner": RoleAssignment("openrouter", "xiaomi/mimo-v2.6-flash"),
    }
    return Config(providers=providers, roles=roles)


def load_config(path: Path | None = None) -> Config:
    target = path or config_path()
    if not target.exists():
        raise ConfigError(
            f"No config at {target}. Run 'ensemble init' first."
        )
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Could not read {target}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Config at {target} must be a JSON object")
    config = Config.from_dict(data)
    config.validate()
    return config


def save_config(config: Config, path: Path | None = None) -> Path:
    config.validate()
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(
        json.dumps(config.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    return target
