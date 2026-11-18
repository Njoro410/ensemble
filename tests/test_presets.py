from __future__ import annotations

from ensemble.presets import PRESETS, provider_from_preset


def test_presets_have_documented_endpoints():
    assert set(PRESETS) == {"openrouter", "opencode", "deepseek"}
    for preset in PRESETS.values():
        assert preset.models_url.startswith("https://")
        assert preset.docs_url.startswith("https://")
        assert preset.env_var.endswith("_API_KEY")


def test_provider_from_preset_preserves_models_and_endpoints():
    provider = provider_from_preset("opencode", models=["m1", "m2"])
    assert provider.id == "opencode"
    assert provider.kind == "builtin"
    assert provider.protocol == "openai"
    assert provider.models_url == PRESETS["opencode"].models_url
    assert provider.verify_url == ""
    assert provider.models == ["m1", "m2"]

    deepseek = provider_from_preset("deepseek")
    assert deepseek.protocol == "anthropic"
    assert deepseek.auth_style == "bearer"
    assert deepseek.models_url == "https://api.deepseek.com/models"
