from __future__ import annotations

from ensemble.presets import PRESETS, provider_from_preset


def test_presets_have_documented_endpoints():
    assert set(PRESETS) == {
        "openrouter",
        "openrouter-anthropic",
        "opencode-go",
        "deepseek",
    }
    for preset in PRESETS.values():
        assert preset.models_url.startswith("https://")
        assert preset.docs_url.startswith("https://")
        assert preset.env_var.endswith("_API_KEY")


def test_openrouter_anthropic_preset_shares_key():
    preset = PRESETS["openrouter-anthropic"]
    provider = provider_from_preset("openrouter-anthropic")
    assert provider.protocol == "anthropic"
    assert provider.base_url == "https://openrouter.ai/api"
    assert provider.key_ref == "openrouter"
    assert provider.models_url == preset.models_url


def test_provider_from_preset_preserves_models_and_endpoints():
    provider = provider_from_preset("opencode-go", models=["m1", "m2"])
    assert provider.id == "opencode-go"
    assert provider.kind == "custom"
    assert provider.protocol == "openai"
    assert provider.headers == {"x-opencode-session": "ensemble"}
    assert provider.model_alias_suffix == "-go"
    assert provider.base_url.endswith("/openai/v1")
    assert provider.models_url == PRESETS["opencode-go"].models_url
    assert provider.verify_url == ""
    assert provider.models == ["m1", "m2"]

    deepseek = provider_from_preset("deepseek")
    assert deepseek.protocol == "anthropic"
    assert deepseek.auth_style == "bearer"
    assert deepseek.models_url == "https://api.deepseek.com/models"
