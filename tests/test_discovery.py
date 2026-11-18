from __future__ import annotations

import http.server
import json
import threading

import pytest

from ensemble.discovery import (
    DiscoveryError,
    discover_provider,
    extract_model_ids,
    fetch_models,
)
from ensemble.presets import provider_from_preset


def test_extract_openai_shape():
    payload = {"data": [{"id": "model-a"}, {"id": "model-b"}]}
    assert extract_model_ids(payload) == ["model-a", "model-b"]


def test_extract_model_list_shape():
    payload = {"models": ["a", {"name": "b"}]}
    assert extract_model_ids(payload) == ["a", "b"]


def test_extract_empty_payload():
    assert extract_model_ids({"data": []}) == []
    assert extract_model_ids("nope") == []


def test_fetch_models_rejects_empty_base_url():
    with pytest.raises(DiscoveryError):
        fetch_models("", "openai")


def test_fetch_models_uses_custom_url_and_bearer():
    payload = {"data": [{"id": "z-model"}, {"id": "a-model"}]}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.headers.get("Authorization") == "Bearer test-key"
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/models"
        assert fetch_models(
            "", "openai", "test-key", models_url=url
        ) == ["a-model", "z-model"]
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_discover_provider_verifies_key_and_uses_models_url(monkeypatch):
    provider = provider_from_preset("openrouter")
    calls = []

    def fake_verify(url, key, auth_style="bearer", timeout=15.0):
        calls.append(("verify", url, key, auth_style))

    def fake_fetch(
        base_url,
        protocol,
        api_key=None,
        timeout=15.0,
        models_url=None,
        auth_style=None,
    ):
        calls.append(("models", models_url, protocol, api_key, auth_style))
        return ["model-a"]

    monkeypatch.setattr("ensemble.discovery.verify_key", fake_verify)
    monkeypatch.setattr("ensemble.discovery.fetch_models", fake_fetch)

    assert discover_provider(provider, "key-123") == ["model-a"]
    assert calls[0] == ("verify", provider.verify_url, "key-123", "bearer")
    assert calls[1] == (
        "models",
        provider.models_url,
        "openai",
        "key-123",
        "bearer",
    )


def test_discover_provider_requires_key():
    with pytest.raises(DiscoveryError):
        discover_provider(provider_from_preset("deepseek"), "")


def test_discover_provider_applies_model_alias_suffix(monkeypatch):
    provider = provider_from_preset("opencode-go")
    monkeypatch.setattr(
        "ensemble.discovery.fetch_models",
        lambda *args, **kwargs: ["m1", "m2"],
    )
    assert discover_provider(provider, "key") == ["m1-go", "m2-go"]
