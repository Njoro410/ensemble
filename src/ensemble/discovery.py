"""Discover model IDs from provider /models endpoints."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .config import Provider


class DiscoveryError(Exception):
    """Raised when a provider's model catalog cannot be fetched."""


def _models_url(base_url: str, protocol: str) -> str:
    base = base_url.rstrip("/")
    if not base:
        return ""
    if protocol == "anthropic":
        return f"{base}/v1/models"
    return f"{base}/models"


def _auth_headers(
    api_key: str | None, auth_style: str, protocol: str
) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if protocol == "anthropic":
        headers["anthropic-version"] = "2023-06-01"
    if api_key:
        if auth_style == "x-api-key":
            headers["x-api-key"] = api_key
        else:
            headers["Authorization"] = f"Bearer {api_key}"
    return headers


def extract_model_ids(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        items = payload.get("data")
        if items is None:
            items = payload.get("models")
    else:
        items = payload
    if not isinstance(items, list):
        return []
    ids: set[str] = set()
    for item in items:
        if isinstance(item, str):
            model_id = item
        elif isinstance(item, dict):
            value = item.get("id") or item.get("name")
            model_id = value if isinstance(value, str) else ""
        else:
            model_id = ""
        if model_id:
            ids.add(model_id)
    return sorted(ids)


def fetch_models(
    base_url: str,
    protocol: str,
    api_key: str | None = None,
    timeout: float = 15.0,
    models_url: str | None = None,
    auth_style: str | None = None,
) -> list[str]:
    style = auth_style or ("x-api-key" if protocol == "anthropic" else "bearer")
    url = models_url or _models_url(base_url, protocol)
    if not url:
        raise DiscoveryError("Base URL is empty")
    headers = _auth_headers(api_key, style, protocol)

    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise DiscoveryError(f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise DiscoveryError(str(exc)) from exc

    ids = extract_model_ids(payload)
    if not ids:
        raise DiscoveryError("The response contained no model IDs")
    return ids


def verify_key(
    url: str,
    api_key: str,
    auth_style: str = "bearer",
    timeout: float = 15.0,
) -> None:
    if not api_key:
        raise DiscoveryError("An API key is required")
    request = urllib.request.Request(
        url, headers=_auth_headers(api_key, auth_style, "openai"), method="GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            return
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise DiscoveryError(
            f"Key check failed: HTTP {exc.code}: {detail}"
        ) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise DiscoveryError(f"Key check failed: {exc}") from exc


def discover_provider(provider: Provider, api_key: str) -> list[str]:
    if not api_key:
        raise DiscoveryError("An API key is required to discover models")
    if provider.verify_url:
        verify_key(provider.verify_url, api_key, provider.auth_style)
    return fetch_models(
        provider.base_url,
        provider.protocol,
        api_key,
        models_url=provider.models_url or None,
        auth_style=provider.auth_style,
    )
