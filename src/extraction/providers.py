"""Thin provider adapters exposing a uniform CompletionFn interface.

Both adapters are (prompt: str) -> str callables, so the extraction pipeline
never imports a vendor SDK directly. SDK imports are deferred to __init__ so
merely importing this module (e.g. in tests) requires neither package.
"""
from __future__ import annotations

from typing import Optional

DEFAULT_MAX_TOKENS = 2048


class AnthropicCompletion:
    """CompletionFn backed by the Anthropic Messages API."""

    def __init__(self, api_key: str, model: str, max_tokens: int = DEFAULT_MAX_TOKENS):
        import anthropic  # deferred: keep module importable without the SDK

        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def __call__(self, prompt: str) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        # Concatenate text blocks; tool-use blocks (never requested) are skipped.
        return "".join(block.text for block in response.content if hasattr(block, "text"))


class OpenAICompletion:
    """CompletionFn backed by the OpenAI Chat Completions API."""

    def __init__(self, api_key: str, model: str, max_tokens: int = DEFAULT_MAX_TOKENS):
        import openai  # deferred: keep module importable without the SDK

        self._client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def __call__(self, prompt: str) -> str:
        # o-series models reject `max_tokens` and require `max_completion_tokens`;
        # classic chat models (gpt-4o, …) still expect `max_tokens`.
        token_kwarg = (
            {"max_completion_tokens": self.max_tokens}
            if self.model.startswith(("o1", "o3", "o4"))
            else {"max_tokens": self.max_tokens}
        )
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            **token_kwarg,
        )
        return response.choices[0].message.content or ""


def make_completion_fn(
    provider: str, api_key: str, model: str, max_tokens: Optional[int] = None
):
    """Factory keyed by provider name ('anthropic' | 'openai')."""
    kwargs = {"max_tokens": max_tokens} if max_tokens else {}
    if provider == "anthropic":
        return AnthropicCompletion(api_key, model, **kwargs)
    if provider == "openai":
        return OpenAICompletion(api_key, model, **kwargs)
    raise ValueError(f"Unknown provider: {provider!r}")
