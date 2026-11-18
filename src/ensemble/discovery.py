"""Discover model IDs from provider /models endpoints."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class DiscoveryError(Exception):
    """Raised when a provider's model catalog cannot be fetched."""


def _models_url(base_url: str, protocol: str) -> str:
    base = base_url.rstrip("/")
    if protocol == "anthropic":
        return f"{base}/v1/models"
    return f"{base}/models"


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
) -> list[str]:
    if not base_url:
        raise DiscoveryError("Base URL is empty")
    headers = {"Accept": "application/json"}
    if protocol == "anthropic":
        if api_key:
            headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    elif api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(
        _models_url(base_url, protocol), headers=headers, method="GET"
    )
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
