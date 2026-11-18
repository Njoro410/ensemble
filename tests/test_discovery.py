from __future__ import annotations

import pytest

from ensemble.discovery import DiscoveryError, extract_model_ids, fetch_models


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
