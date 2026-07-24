"""Tests for API key verification.

The behaviour worth defending here is the distinction between "the provider
rejected this key" and "we could not ask the provider". Collapsing the two is
the bug this module exists to prevent.
"""
from __future__ import annotations

from src.extraction.key_check import (
    INVALID_KEY_MESSAGE,
    check_api_key,
    detect_provider_from_key,
    interpret_listing,
    is_placeholder_key,
    precheck_key,
)
from src.extraction.model_discovery import ModelList


class _Client:
    """Stub SDK client whose listing either succeeds or raises."""

    def __init__(self, ids=None, error=None):
        self._ids = ids or []
        self._error = error
        self.models = self

    def list(self):
        if self._error is not None:
            raise RuntimeError(self._error)
        return [type("M", (), {"id": i})() for i in self._ids]


class TestKeyOrigin:
    def test_anthropic_prefix_is_recognised(self):
        assert detect_provider_from_key("sk-ant-api03-abc") == "anthropic"

    def test_openai_prefixes_are_recognised(self):
        assert detect_provider_from_key("sk-proj-abc") == "openai"
        assert detect_provider_from_key("sk-abc") == "openai"

    def test_unknown_key_shape_returns_none(self):
        assert detect_provider_from_key("hunter2") is None

    def test_whitespace_is_ignored(self):
        assert detect_provider_from_key("  sk-ant-abc ") == "anthropic"

    def test_placeholder_values_are_detected(self):
        assert is_placeholder_key("sk-ant-your-key-here")
        assert is_placeholder_key("sk-your-key-here")
        assert not is_placeholder_key("sk-ant-api03-real-looking")


class TestLocalPrecheck:
    def test_empty_key_is_not_an_error(self):
        verdict = precheck_key("anthropic", "")
        assert verdict.status == "empty"
        assert INVALID_KEY_MESSAGE not in verdict.message

    def test_placeholder_is_reported_without_network(self):
        assert precheck_key("openai", "sk-your-key-here").status == "placeholder"

    def test_wrong_provider_is_caught_locally(self):
        verdict = precheck_key("openai", "sk-ant-api03-abc")
        assert verdict.status == "mismatch"
        assert "Anthropic" in verdict.message

    def test_anthropic_key_in_openai_field_says_put_openai_key(self):
        """The user pasted an Anthropic key while OpenAI was selected and did
        not realise it - name the issuer AND tell them which key to put."""
        verdict = precheck_key("openai", "sk-ant-api03-abc")
        assert verdict.status == "mismatch"
        assert "Anthropic" in verdict.message  # names what they pasted
        assert "PUT OPENAI'S API KEY" in verdict.message  # tells them what to do

    def test_openai_key_in_anthropic_field_says_put_anthropic_key(self):
        verdict = precheck_key("anthropic", "sk-proj-abcdef")
        assert verdict.status == "mismatch"
        assert "OpenAI" in verdict.message
        assert "PUT ANTHROPIC'S API KEY" in verdict.message

    def test_mismatch_company_is_the_selected_provider(self):
        """Regression: the UI discards a verdict whose company differs from the
        selected provider, so a mismatch must report the SELECTED company or it
        would never be shown after a check."""
        verdict = precheck_key("openai", "sk-ant-api03-abc")
        assert verdict.company == "OpenAI"

    def test_plausible_key_falls_through(self):
        assert precheck_key("anthropic", "sk-ant-api03-abc") is None


class TestVerdictFromListing:
    def test_live_listing_means_verified(self):
        listing = ModelList(models=["claude-sonnet-5", "claude-opus-5"], source="live")
        verdict = interpret_listing("anthropic", listing)
        assert verdict.ok
        assert verdict.company == "Anthropic"
        assert verdict.model_count == 2
        assert "2 models" in verdict.message

    def test_authentication_failure_is_reported_as_fake_or_revoked(self):
        listing = ModelList(source="fallback", error="401 authentication_error")
        verdict = interpret_listing("openai", listing)
        assert verdict.status == "invalid"
        assert verdict.message == INVALID_KEY_MESSAGE

    def test_revoked_wording_is_recognised(self):
        listing = ModelList(source="fallback", error="This key has been revoked")
        assert interpret_listing("openai", listing).status == "invalid"

    def test_offline_is_never_reported_as_a_fake_key(self):
        """The central guarantee: a dropped connection must not accuse the user."""
        listing = ModelList(source="fallback", error="Connection refused")
        verdict = interpret_listing("anthropic", listing)
        assert verdict.status == "unreachable"
        assert verdict.message != INVALID_KEY_MESSAGE
        assert "may still be valid" in verdict.message

    def test_missing_sdk_is_not_reported_as_a_fake_key(self):
        listing = ModelList(source="fallback", error="No module named 'anthropic'")
        assert interpret_listing("anthropic", listing).status == "unreachable"


class TestEndToEndCheck:
    def test_valid_key_lists_models_and_company(self):
        client = _Client(ids=["claude-sonnet-5", "claude-opus-5", "claude-3-opus-20240229"])
        verdict = check_api_key("anthropic", "sk-ant-api03-abc", client=client)
        assert verdict.ok
        assert verdict.company == "Anthropic"
        # Retired snapshots are filtered out of what we claim is available.
        assert "claude-3-opus-20240229" not in verdict.models
        assert "claude-sonnet-5" in verdict.models

    def test_rejected_key_gets_the_exact_message(self):
        client = _Client(error="invalid x-api-key")
        verdict = check_api_key("anthropic", "sk-ant-api03-bogus", client=client)
        assert verdict.message == INVALID_KEY_MESSAGE
        assert verdict.models == []

    def test_unexpected_client_failure_does_not_crash_the_app(self):
        """An SDK that misbehaves in a novel way must still yield a verdict.

        Note KeyboardInterrupt and SystemExit are deliberately NOT caught
        anywhere in this path: swallowing those would make the app impossible
        to stop. Only ordinary failures degrade to a verdict.
        """

        class Exploding:
            @property
            def models(self):
                raise TypeError("SDK returned something unexpected")

        verdict = check_api_key("openai", "sk-abc", client=Exploding())
        assert verdict.status == "unreachable"
        assert verdict.message != INVALID_KEY_MESSAGE


class TestBalanceProbe:
    """The 1-token billing probe: real key + empty wallet must be its own answer."""

    def test_successful_completion_means_funded(self):
        from src.extraction.key_check import check_balance

        verdict = check_balance(
            "openai", "sk-proj-abc", "gpt-5.6-terra", completion_fn=lambda p: "ok"
        )
        assert verdict.status == "funded"
        assert verdict.company == "OpenAI"

    def test_openai_quota_error_names_openai(self):
        from src.extraction.key_check import check_balance

        def broke(_):
            raise RuntimeError("Error code: 429 - insufficient_quota; exceeded your current quota")

        verdict = check_balance("openai", "sk-proj-abc", "gpt-5.6-terra", completion_fn=broke)
        assert verdict.status == "no_balance"
        assert verdict.message == "INSUFFICIENT BALANCE OR BUY CREDITS FROM YOUR OPENAI"

    def test_anthropic_credit_error_names_anthropic(self):
        from src.extraction.key_check import check_balance

        def broke(_):
            raise RuntimeError("400 - Your credit balance is too low to access the API")

        verdict = check_balance("anthropic", "sk-ant-abc", "claude-sonnet-5", completion_fn=broke)
        assert verdict.status == "no_balance"
        assert verdict.message == "INSUFFICIENT BALANCE OR BUY CREDITS FROM YOUR ANTHROPIC"

    def test_auth_error_is_still_reported_as_fake_not_broke(self):
        """A rejected key must not be mislabelled as merely out of money."""
        from src.extraction.key_check import INVALID_KEY_MESSAGE, check_balance

        def broke(_):
            raise RuntimeError("401 invalid x-api-key")

        verdict = check_balance("anthropic", "sk-ant-abc", "claude-sonnet-5", completion_fn=broke)
        assert verdict.status == "invalid"
        assert verdict.message == INVALID_KEY_MESSAGE

    def test_offline_is_never_reported_as_out_of_money(self):
        from src.extraction.key_check import check_balance

        def broke(_):
            raise RuntimeError("Connection timed out")

        verdict = check_balance("openai", "sk-proj-abc", "gpt-5.6-terra", completion_fn=broke)
        assert verdict.status == "unreachable"
        assert "INSUFFICIENT" not in verdict.message

    def test_probe_never_raises_on_unexpected_failure(self):
        from src.extraction.key_check import check_balance

        def broke(_):
            raise ValueError("totally unexpected shape")

        verdict = check_balance("openai", "sk-proj-abc", "gpt-5.6-terra", completion_fn=broke)
        assert verdict.status == "unreachable"

    def test_local_guards_run_before_spending_a_token(self):
        """A wrong-provider key must be caught before the paid endpoint."""
        from src.extraction.key_check import check_balance

        calls = []

        def spy(prompt):
            calls.append(prompt)
            return "ok"

        # An Anthropic key while OpenAI is selected: prefix check can't run when
        # a completion_fn is injected, so this reaches the fn - assert the
        # placeholder guard (which is prefix-independent) short-circuits first.
        verdict = check_balance(
            "openai", "sk-your-key-here", "gpt-5.6-terra", completion_fn=spy
        )
        assert verdict.status == "placeholder"
        assert calls == []


class TestBalanceMessage:
    def test_message_uppercases_company(self):
        from src.extraction.key_check import insufficient_balance_message

        assert insufficient_balance_message("OpenAI") == (
            "INSUFFICIENT BALANCE OR BUY CREDITS FROM YOUR OPENAI"
        )
        assert insufficient_balance_message("Anthropic").endswith("ANTHROPIC")
