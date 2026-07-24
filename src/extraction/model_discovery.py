"""Dynamic model discovery for the UI's model dropdown.

When a user pastes an API key, we query the provider's live model listing so
the dropdown reflects *their* key's actual access (org restrictions, new
releases) instead of a hardcoded snapshot. Every failure path — bad key,
offline, SDK missing — degrades to a curated fallback list rather than
raising, because model discovery is a UX nicety and must never crash the app.

Both fetchers accept an injectable pre-built client so tests can pass a stub
and never touch the network or require an SDK install.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

# Curated fallbacks: shown before a key is entered or when listing fails.
# Order = recommendation order (best default first).
DEFAULT_ANTHROPIC_MODELS: List[str] = [
    "claude-3-7-sonnet-latest",
    "claude-3-5-sonnet-latest",
    "claude-3-5-haiku-latest",
    "claude-3-opus-20240229",
]
DEFAULT_OPENAI_MODELS: List[str] = [
    "gpt-4o",
    "gpt-4o-mini",
    "o1",
    "o3-mini",
]

# OpenAI's /models endpoint mixes chat models with embeddings, TTS, image and
# moderation models. Allow chat/reasoning families, then subtract non-chat
# variants that share those prefixes (e.g. gpt-4o-audio-preview).
_OPENAI_CHAT_PREFIXES = ("gpt-4", "gpt-4o", "gpt-3.5-turbo", "o1", "o3", "o4", "chatgpt")
_OPENAI_EXCLUDE_PATTERN = re.compile(
    r"(audio|realtime|transcribe|tts|search|instruct|embedding|moderation|image|dall-e|whisper)",
    re.IGNORECASE,
)


@dataclass
class ModelList:
    """Discovery result: the models plus where they came from.

    ``source`` is 'live' or 'fallback' — the UI shows a small caption when the
    list is a fallback so users know it may be stale.
    """

    models: List[str] = field(default_factory=list)
    source: str = "fallback"
    error: Optional[str] = None


def _is_openai_chat_model(model_id: str) -> bool:
    """True for chat/reasoning models a flashcard extractor can actually use."""
    lowered = model_id.lower()
    if not lowered.startswith(_OPENAI_CHAT_PREFIXES):
        return False
    return not _OPENAI_EXCLUDE_PATTERN.search(lowered)


def fetch_openai_models(api_key: str, client: Optional[Any] = None) -> ModelList:
    """List chat-capable models available to this OpenAI key.

    Args:
        api_key: User's OpenAI key (ignored if ``client`` is provided).
        client: Injectable client exposing ``.models.list()`` (for tests).
    """
    if not api_key and client is None:
        return ModelList(models=list(DEFAULT_OPENAI_MODELS), source="fallback")
    try:
        if client is None:
            import openai

            client = openai.OpenAI(api_key=api_key)
        listed = [m.id for m in client.models.list()]
        chat_models = sorted((m for m in listed if _is_openai_chat_model(m)), reverse=True)
        if not chat_models:
            return ModelList(models=list(DEFAULT_OPENAI_MODELS), source="fallback")
        return ModelList(models=chat_models, source="live")
    except Exception as exc:  # noqa: BLE001 — any failure degrades to fallback by design
        return ModelList(models=list(DEFAULT_OPENAI_MODELS), source="fallback", error=str(exc))


def fetch_anthropic_models(api_key: str, client: Optional[Any] = None) -> ModelList:
    """List models available to this Anthropic key via the /v1/models endpoint.

    Anthropic's listing is already chat-only, so no family filtering is
    needed; we just prepend '-latest' aliases absent from the API listing.
    """
    if not api_key and client is None:
        return ModelList(models=list(DEFAULT_ANTHROPIC_MODELS), source="fallback")
    try:
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
        listed = [m.id for m in client.models.list()]
        if not listed:
            return ModelList(models=list(DEFAULT_ANTHROPIC_MODELS), source="fallback")
        # Keep curated -latest aliases on top: they track new snapshots
        # automatically, which is the right default for a demo app.
        aliases = [m for m in DEFAULT_ANTHROPIC_MODELS if m.endswith("-latest")]
        merged = aliases + [m for m in listed if m not in aliases]
        return ModelList(models=merged, source="live")
    except Exception as exc:  # noqa: BLE001 — any failure degrades to fallback by design
        return ModelList(models=list(DEFAULT_ANTHROPIC_MODELS), source="fallback", error=str(exc))


def discover_models(provider: str, api_key: str, client: Optional[Any] = None) -> ModelList:
    """Provider-keyed dispatcher used by the UI."""
    if provider == "openai":
        return fetch_openai_models(api_key, client=client)
    if provider == "anthropic":
        return fetch_anthropic_models(api_key, client=client)
    raise ValueError(f"Unknown provider: {provider!r}")
