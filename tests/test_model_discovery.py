"""Tests for dynamic model discovery — all provider clients are stubs."""
from __future__ import annotations

from types import SimpleNamespace
from typing import List

from src.extraction.model_discovery import (
    DEFAULT_ANTHROPIC_MODELS,
    DEFAULT_OPENAI_MODELS,
    _is_openai_chat_model,
    discover_models,
    fetch_anthropic_models,
    fetch_openai_models,
)


class FakeModelsPage:
    """Minimal stand-in for openai/anthropic ``client.models.list()`` results."""

    def __init__(self, ids: List[str]):
        self._ids = ids

    def __iter__(self):
        return iter(SimpleNamespace(id=mid) for mid in self._ids)


class FakeClient:
    def __init__(self, ids: List[str], *, fail: bool = False):
        self._ids = ids
        self._fail = fail
        self.models = self

    def list(self):
        if self._fail:
            raise RuntimeError("network down")
        return FakeModelsPage(self._ids)


class TestOpenAIFilter:
    def test_keeps_chat_and_reasoning_families(self):
        assert _is_openai_chat_model("gpt-4o")
        assert _is_openai_chat_model("gpt-4o-mini")
        assert _is_openai_chat_model("o1")
        assert _is_openai_chat_model("o3-mini")
        assert _is_openai_chat_model("gpt-3.5-turbo")

    def test_excludes_non_chat_variants(self):
        assert not _is_openai_chat_model("text-embedding-3-large")
        assert not _is_openai_chat_model("whisper-1")
        assert not _is_openai_chat_model("dall-e-3")
        assert not _is_openai_chat_model("gpt-4o-audio-preview")
        assert not _is_openai_chat_model("gpt-4o-realtime-preview")


class TestFetchOpenAI:
    def test_empty_key_returns_fallback(self):
        result = fetch_openai_models("")
        assert result.source == "fallback"
        assert result.models == DEFAULT_OPENAI_MODELS

    def test_live_list_filters_to_chat_models(self):
        client = FakeClient(
            [
                "gpt-4o",
                "text-embedding-3-small",
                "o1",
                "whisper-1",
                "gpt-4o-mini",
                "dall-e-3",
            ]
        )
        result = fetch_openai_models("sk-test", client=client)
        assert result.source == "live"
        assert "gpt-4o" in result.models
        assert "o1" in result.models
        assert "gpt-4o-mini" in result.models
        assert "whisper-1" not in result.models
        assert "text-embedding-3-small" not in result.models

    def test_provider_failure_degrades_to_fallback(self):
        result = fetch_openai_models("sk-test", client=FakeClient([], fail=True))
        assert result.source == "fallback"
        assert result.models == DEFAULT_OPENAI_MODELS
        assert result.error is not None

    def test_empty_chat_set_falls_back(self):
        # Listing succeeds but every model is embeddings/TTS → still fallback.
        result = fetch_openai_models(
            "sk-test", client=FakeClient(["text-embedding-3-large", "whisper-1"])
        )
        assert result.source == "fallback"
        assert result.models == DEFAULT_OPENAI_MODELS


class TestFetchAnthropic:
    def test_empty_key_returns_fallback(self):
        result = fetch_anthropic_models("")
        assert result.source == "fallback"
        assert result.models == DEFAULT_ANTHROPIC_MODELS

    def test_live_list_prepends_latest_aliases(self):
        client = FakeClient(
            [
                "claude-3-5-sonnet-20241022",
                "claude-3-opus-20240229",
                "claude-3-5-haiku-20241022",
            ]
        )
        result = fetch_anthropic_models("sk-ant-test", client=client)
        assert result.source == "live"
        # Curated -latest aliases lead so the dropdown default tracks new snapshots.
        assert result.models[0].endswith("-latest")
        assert "claude-3-5-sonnet-20241022" in result.models
        assert "claude-3-opus-20240229" in result.models

    def test_provider_failure_degrades_to_fallback(self):
        result = fetch_anthropic_models("sk-ant", client=FakeClient([], fail=True))
        assert result.source == "fallback"
        assert result.models == DEFAULT_ANTHROPIC_MODELS


class TestDiscoverModels:
    def test_dispatches_by_provider(self):
        oa = discover_models("openai", "")
        an = discover_models("anthropic", "")
        assert oa.models == DEFAULT_OPENAI_MODELS
        assert an.models == DEFAULT_ANTHROPIC_MODELS

    def test_unknown_provider_raises(self):
        import pytest

        with pytest.raises(ValueError, match="Unknown provider"):
            discover_models("cohere", "key")
