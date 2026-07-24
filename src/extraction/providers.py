"""Thin provider adapters exposing a uniform CompletionFn interface.

Both adapters are (prompt: str) -> str callables, so the extraction pipeline
never imports a vendor SDK directly. SDK imports are deferred to __init__ so
merely importing this module (e.g. in tests) requires neither package.

Reliability: extraction fans out one network call per chunk, so a single
hung request would otherwise stall a whole document. Every client is built
with an explicit timeout and a bounded retry budget.
"""
from __future__ import annotations

from typing import Optional

DEFAULT_MAX_TOKENS = 2048
# A chunk completion is ~2k tokens; 60s is generous but still bounded.
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 2

# OpenAI reasoning families reject `max_tokens` and require
# `max_completion_tokens`. Matching on the family prefix (rather than an
# exhaustive model list) keeps new snapshots working without a code change.
_OPENAI_REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")


def _uses_max_completion_tokens(model: str) -> bool:
    """True for models that require `max_completion_tokens`."""
    return model.lower().startswith(_OPENAI_REASONING_PREFIXES)


class AnthropicCompletion:
    """CompletionFn backed by the Anthropic Messages API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        import anthropic  # deferred: keep module importable without the SDK

        self._client = anthropic.Anthropic(
            api_key=api_key, timeout=timeout, max_retries=max_retries
        )
        self.model = model
        self.max_tokens = max_tokens

    def __call__(self, prompt: str) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        # Concatenate text blocks; tool-use blocks (never requested) are skipped.
        return "".join(
            block.text for block in response.content if getattr(block, "text", None)
        )


class OpenAICompletion:
    """CompletionFn backed by the OpenAI Chat Completions API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        import openai  # deferred: keep module importable without the SDK

        self._client = openai.OpenAI(
            api_key=api_key, timeout=timeout, max_retries=max_retries
        )
        self.model = model
        self.max_tokens = max_tokens

    def __call__(self, prompt: str) -> str:
        token_kwarg = (
            {"max_completion_tokens": self.max_tokens}
            if _uses_max_completion_tokens(self.model)
            else {"max_tokens": self.max_tokens}
        )
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            **token_kwarg,
        )
        if not response.choices:
            return ""
        return response.choices[0].message.content or ""


def make_completion_fn(
    provider: str,
    api_key: str,
    model: str,
    max_tokens: Optional[int] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
):
    """Factory keyed by provider name ('anthropic' | 'openai')."""
    if not api_key:
        raise ValueError("An API key is required to build a completion function")

    kwargs = {"timeout": timeout, "max_retries": max_retries}
    # `is not None` (not truthiness): max_tokens=0 is invalid, not "use default".
    if max_tokens is not None:
        if max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {max_tokens}")
        kwargs["max_tokens"] = max_tokens

    if provider == "anthropic":
        return AnthropicCompletion(api_key, model, **kwargs)
    if provider == "openai":
        return OpenAICompletion(api_key, model, **kwargs)
    raise ValueError(f"Unknown provider: {provider!r}")
