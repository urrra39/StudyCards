"""Dynamic model discovery for the UI's model dropdown.

When a user pastes an API key, we query the provider's live model listing so
the dropdown reflects *their* key's actual access (org restrictions, new
releases) instead of a hardcoded snapshot. Every failure path - bad key,
offline, SDK missing - degrades to a curated fallback list rather than
raising, because model discovery is a UX nicety and must never crash the app.

Both fetchers accept an injectable pre-built client so tests can pass a stub
and never touch the network or require an SDK install.

Catalog last verified: 2026-07-24 against the Anthropic and OpenAI model
docs. The live listing is always authoritative; the curated lists below only
matter before a key is entered or when listing fails.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Curated fallbacks. Order = recommendation order, and the FIRST entry is the
# app's effective default because Streamlit preselects index 0.
#
# Default choice rationale: extraction is a high-volume chunked workload -
# one call per ~4000 characters - so the mid-tier model is the right default
# rather than the most expensive frontier model. Users can pick up.
# --------------------------------------------------------------------------
DEFAULT_ANTHROPIC_MODELS: List[str] = [
    "claude-sonnet-5",    # default: near Opus 4.8 quality at Sonnet pricing
    "claude-opus-5",      # flagship, near-frontier at optimized cost
    "claude-fable-5",     # most capable frontier model
    "claude-opus-4-8",    # long-horizon agentic coding, 1M context
    "claude-opus-4-7",
    "claude-sonnet-4-6",
]

DEFAULT_OPENAI_MODELS: List[str] = [
    "gpt-5.6-terra",      # default: balances intelligence and cost
    "gpt-5.6-sol",        # frontier model for complex professional work
    "gpt-5.6-luna",       # cost-optimized, high volume
    "gpt-5.5",
    "gpt-5.5-pro",
    "gpt-5.4",
    "gpt-5.4-pro",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
]

# Deliberately NOT in the fallback list: claude-mythos-5. It is released to a
# limited set of organizations, so offering it to every user would mostly
# produce permission errors. If a key does have access, the live listing
# surfaces it automatically - which is exactly what live discovery is for.

# Models retired from the APIs. The previous defaults (claude-3-*) were all
# retired by mid-2026, which meant a fresh clone with no key configured
# offered a dropdown of models that return 404. We surface this rather than
# letting the user discover it as an opaque provider error.
_RETIRED_MODEL_PATTERN = re.compile(
    r"""^(
        claude-(1|2|instant|3)              # Claude 1/2/3 families
        | claude-(sonnet|opus)-4(?:-[01])?$  # Sonnet 4, Opus 4, Opus 4.0/4.1
        | gpt-3(?!\.5-turbo)
        | text-davinci
        | code-davinci
    )""",
    re.IGNORECASE | re.VERBOSE,
)
# Note on the Claude-4 branch: the trailing ``$`` binds only to that alternative
# (each alternative is anchored on its own), so ``claude-sonnet-4`` and
# ``claude-opus-4`` match, as do ``-4-0``/``-4-1``. Current models keep their
# minor suffix (``claude-sonnet-4-6``, ``claude-opus-4-7/4-8``) and are NOT
# matched because ``-[01]`` only admits the retired 4.0/4.1 revisions.


def is_retired_model(model_id: str) -> bool:
    """True for model IDs known to be withdrawn from the provider APIs."""
    return bool(_RETIRED_MODEL_PATTERN.match(model_id.strip()))


# OpenAI's /models endpoint mixes chat models with embeddings, TTS, image and
# moderation models. Allow chat/reasoning families, then subtract non-chat
# variants that share those prefixes (e.g. gpt-4o-audio-preview).
# "gpt-5" covers the whole gpt-5.x line including gpt-5.6-sol/terra/luna;
# "gpt-4" already covers "gpt-4o"/"gpt-4.1".
_OPENAI_CHAT_PREFIXES = ("gpt-3.5-turbo", "gpt-4", "gpt-5", "o1", "o3", "o4", "chatgpt")
_OPENAI_EXCLUDE_PATTERN = re.compile(
    r"(audio|realtime|transcribe|tts|search|instruct|embedding|moderation|image|dall-e|whisper)",
    re.IGNORECASE,
)

# Anthropic's listing is chat-only, but it also returns non-conversational
# entries on some orgs; keep anything in the claude-* family.
_ANTHROPIC_PREFIX = "claude-"


@dataclass
class ModelList:
    """Discovery result: the models plus where they came from.

    ``source`` is 'live' or 'fallback' - the UI shows a small caption when the
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
    if _OPENAI_EXCLUDE_PATTERN.search(lowered):
        return False
    return not is_retired_model(lowered)


def _order_by_preference(models: List[str], curated: List[str]) -> List[str]:
    """Recommendation order for a live listing.

    The dropdown's first entry is the app's effective default, so it must be a
    sensible general-purpose model rather than whatever happened to sort last
    alphabetically. Curated favourites lead, in curated order, when the key
    actually has them; everything else follows sorted for stable output.
    """
    available = set(models)
    preferred = [m for m in curated if m in available]
    seen = set(preferred)
    rest = sorted(m for m in models if m not in seen)
    return preferred + rest


def _ordered_openai(models: List[str]) -> List[str]:
    return _order_by_preference(models, DEFAULT_OPENAI_MODELS)


def _ordered_anthropic(models: List[str]) -> List[str]:
    return _order_by_preference(models, DEFAULT_ANTHROPIC_MODELS)


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
        chat_models = [m for m in listed if _is_openai_chat_model(m)]
        if not chat_models:
            logger.warning("OpenAI listing contained no usable chat models; using fallbacks")
            return ModelList(models=list(DEFAULT_OPENAI_MODELS), source="fallback")
        return ModelList(models=_ordered_openai(chat_models), source="live")
    except Exception as exc:  # noqa: BLE001 - any failure degrades to fallback by design
        logger.warning("OpenAI model listing failed (%s); using fallbacks", exc)
        return ModelList(models=list(DEFAULT_OPENAI_MODELS), source="fallback", error=str(exc))


def fetch_anthropic_models(api_key: str, client: Optional[Any] = None) -> ModelList:
    """List models available to this Anthropic key via the /v1/models endpoint.

    Retired snapshots are filtered out: Anthropic keeps returning nothing for
    them, but a stale local list could still offer one.
    """
    if not api_key and client is None:
        return ModelList(models=list(DEFAULT_ANTHROPIC_MODELS), source="fallback")
    try:
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
        listed = [
            m.id
            for m in client.models.list()
            if str(m.id).lower().startswith(_ANTHROPIC_PREFIX) and not is_retired_model(str(m.id))
        ]
        if not listed:
            logger.warning("Anthropic listing contained no usable models; using fallbacks")
            return ModelList(models=list(DEFAULT_ANTHROPIC_MODELS), source="fallback")
        return ModelList(models=_ordered_anthropic(listed), source="live")
    except Exception as exc:  # noqa: BLE001 - any failure degrades to fallback by design
        logger.warning("Anthropic model listing failed (%s); using fallbacks", exc)
        return ModelList(models=list(DEFAULT_ANTHROPIC_MODELS), source="fallback", error=str(exc))


def discover_models(provider: str, api_key: str, client: Optional[Any] = None) -> ModelList:
    """Provider-keyed dispatcher used by the UI."""
    if provider == "openai":
        return fetch_openai_models(api_key, client=client)
    if provider == "anthropic":
        return fetch_anthropic_models(api_key, client=client)
    raise ValueError(f"Unknown provider: {provider!r}")
