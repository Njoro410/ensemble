"""Built-in provider presets with documented discovery endpoints."""

from __future__ import annotations

from dataclasses import dataclass

from .config import Provider


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    protocol: str
    base_url: str
    env_var: str
    key_ref: str
    model_alias_suffix: str
    include_in_opencode: bool
    kind: str
    auth_style: str
    headers: dict[str, str]
    models_url: str
    verify_url: str
    docs_url: str
    description: str


PRESETS: dict[str, Preset] = {
    "openrouter": Preset(
        id="openrouter",
        label="OpenRouter",
        protocol="openai",
        base_url="https://openrouter.ai/api/v1",
        env_var="OPENROUTER_API_KEY",
        key_ref="",
        model_alias_suffix="",
        include_in_opencode=True,
        kind="builtin",
        auth_style="bearer",
        headers={},
        models_url="https://openrouter.ai/api/v1/models",
        verify_url="https://openrouter.ai/api/v1/auth/key",
        docs_url="https://openrouter.ai/docs/api-reference/overview",
        description="Unified catalog; native opencode provider.",
    ),
    "openrouter-anthropic": Preset(
        id="openrouter-anthropic",
        label="OpenRouter (Anthropic)",
        protocol="anthropic",
        base_url="https://openrouter.ai/api",
        env_var="OPENROUTER_API_KEY",
        key_ref="openrouter",
        model_alias_suffix="",
        include_in_opencode=True,
        kind="custom",
        auth_style="bearer",
        headers={},
        models_url="https://openrouter.ai/api/v1/models",
        verify_url="https://openrouter.ai/api/v1/auth/key",
        docs_url="https://openrouter.ai/docs/api-reference/overview",
        description="Anthropic Messages surface for Claude Code; shares the OpenRouter key.",
    ),
    "opencode-go": Preset(
        id="opencode-go",
        label="OpenCode Go",
        protocol="openai",
        base_url="https://opencode.ai/inference/go/openai/v1",
        env_var="OPENCODE_API_KEY",
        key_ref="",
        model_alias_suffix="-go",
        include_in_opencode=True,
        kind="custom",
        auth_style="bearer",
        headers={"x-opencode-session": "ensemble"},
        models_url="https://opencode.ai/inference/go/openai/v1/models",
        verify_url="",
        docs_url="https://opencode.ai/docs/console/harnesses/",
        description="Console/Go gateway; requires x-opencode-session.",
    ),
    "opencode-anthropic": Preset(
        id="opencode-anthropic",
        label="OpenCode Go (Anthropic)",
        protocol="anthropic",
        base_url="https://opencode.ai/inference/go/anthropic",
        env_var="OPENCODE_API_KEY",
        key_ref="opencode-go",
        model_alias_suffix="",
        include_in_opencode=False,
        kind="custom",
        auth_style="bearer",
        headers={"x-opencode-session": "ensemble"},
        models_url="https://opencode.ai/inference/go/openai/v1/models",
        verify_url="",
        docs_url="https://opencode.ai/docs/console/harnesses/",
        description="Anthropic Messages surface for the Claude Code orchestrator.",
    ),
    "deepseek": Preset(
        id="deepseek",
        label="DeepSeek",
        protocol="anthropic",
        base_url="https://api.deepseek.com/anthropic",
        env_var="DEEPSEEK_API_KEY",
        key_ref="",
        model_alias_suffix="",
        include_in_opencode=True,
        kind="custom",
        auth_style="bearer",
        headers={},
        models_url="https://api.deepseek.com/models",
        verify_url="",
        docs_url="https://api-docs.deepseek.com/api/list-models/",
        description="V4.1 Flash and V4 Pro; drives Claude Code via Anthropic API.",
    ),
}


def provider_from_preset(
    preset_id: str, models: list[str] | None = None
) -> Provider:
    preset = PRESETS[preset_id]
    return Provider(
        id=preset.id,
        label=preset.label,
        protocol=preset.protocol,
        env_var=preset.env_var,
        base_url=preset.base_url,
        kind=preset.kind,
        auth_style=preset.auth_style,
        key_ref=preset.key_ref,
        model_alias_suffix=preset.model_alias_suffix,
        include_in_opencode=preset.include_in_opencode,
        headers=dict(preset.headers),
        models_url=preset.models_url,
        verify_url=preset.verify_url,
        models=list(models or []),
    )
