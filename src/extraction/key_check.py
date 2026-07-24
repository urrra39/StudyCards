"""API key verification for the sidebar.

The model dropdown alone cannot tell a user whether their key works: model
discovery deliberately degrades to curated fallbacks on *every* failure, so a
revoked key and a dropped wifi connection look identical - a populated
dropdown either way. That is correct behaviour for the dropdown, and useless
as feedback.

This module answers what the dropdown cannot: is this key real, which company
issued it, and what does it actually unlock?

The central design decision is that "not valid" and "could not check" are
different answers and must never be collapsed into one. Telling someone their
key is fake because their connection dropped is a genuinely harmful message -
people revoke and regenerate working keys over it. So an authentication
rejection is reported as a fake or revoked key, while a transport failure is
reported honestly as an incomplete check.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

from src.extraction.model_discovery import ModelList, discover_models

# The exact wording the UI shows for a rejected key.
INVALID_KEY_MESSAGE = "THE API KEY IS NOT REAL OR REVOKED"


def insufficient_balance_message(company: str) -> str:
    """Exact wording shown when a key authenticates but has no credit."""
    return f"INSUFFICIENT BALANCE OR BUY CREDITS FROM YOUR {company.upper()}"


# Substrings identifying a *billing / quota* rejection - the key is real, the
# wallet is empty. Kept separate from the auth markers because the two demand
# opposite actions from the user: regenerate the key vs. add funds. Drawn from
# the error bodies both providers actually return (OpenAI: insufficient_quota /
# "exceeded your current quota"; Anthropic: "credit balance is too low").
_BALANCE_ERROR_MARKERS = (
    "insufficient_quota",
    "insufficient quota",
    "exceeded your current quota",
    "credit balance is too low",
    "credit balance",
    "insufficient balance",
    "insufficient credit",
    "billing_not_active",
    "check your plan and billing",
    "plan and billing details",
    "payment required",
    "402",
)

COMPANIES = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
}

# Key prefixes strongly indicate the issuing company, which lets us catch the
# most common setup mistake - an Anthropic key pasted while OpenAI is selected
# - locally, before spending a network round trip to learn the same thing.
_KEY_PREFIXES = (
    ("sk-ant-", "anthropic"),
    ("sk-proj-", "openai"),
    ("sk-", "openai"),
)

# Placeholder values shipped in .env.example: not a key to diagnose over the
# network, just an untouched sample file.
_PLACEHOLDER_PATTERN = re.compile(
    r"^sk-(ant-)?(your|xxx|placeholder|\.\.\.)", re.IGNORECASE
)

# Substrings identifying an *authentication* rejection rather than a transport
# problem. Matched against the SDK's error text, which is the only signal left
# once the SDK has wrapped the HTTP response in an exception.
_AUTH_ERROR_MARKERS = (
    "401",
    "403",
    "authentication_error",
    "invalid_api_key",
    "invalid api key",
    "invalid x-api-key",
    "incorrect api key",
    "unauthorized",
    "revoked",
    "permission_error",
)


@dataclass
class KeyCheck:
    """Verdict on a pasted API key.

    ``status`` is one of:
        empty       - nothing entered yet
        placeholder - the untouched .env.example value
        mismatch    - the key was issued by the other provider
        invalid     - the provider rejected it: fake, revoked or disabled
        unreachable - the check itself failed (offline, SDK missing, outage)
        valid       - the provider accepted it and returned a model listing
    """

    status: str = "empty"
    company: str = ""
    models: List[str] = field(default_factory=list)
    message: str = ""
    detail: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == "valid"

    @property
    def model_count(self) -> int:
        return len(self.models)


def detect_provider_from_key(api_key: str) -> Optional[str]:
    """Guess the issuing company from the key prefix, or None if unknown."""
    key = (api_key or "").strip()
    for prefix, provider in _KEY_PREFIXES:
        if key.startswith(prefix):
            return provider
    return None


def is_placeholder_key(api_key: str) -> bool:
    """True for the untouched sample values in .env.example."""
    return bool(_PLACEHOLDER_PATTERN.match((api_key or "").strip()))


def _looks_like_auth_failure(error: str) -> bool:
    lowered = (error or "").lower()
    return any(marker in lowered for marker in _AUTH_ERROR_MARKERS)


def _looks_like_balance_failure(error: str) -> bool:
    lowered = (error or "").lower()
    return any(marker in lowered for marker in _BALANCE_ERROR_MARKERS)


def precheck_key(
    provider: str, api_key: str, allow_prefix_check: bool = True
) -> Optional[KeyCheck]:
    """Local checks that need no network. Returns None if the key looks sane.

    Kept separate so the UI can run it against a key the moment it is pasted,
    and only fall through to the (cached) provider listing when there is
    actually something to ask the provider.
    """
    company = COMPANIES.get(provider, provider.title())
    key = (api_key or "").strip()

    if not key:
        return KeyCheck(status="empty", company=company, message="Enter a key to verify it.")

    if is_placeholder_key(key):
        return KeyCheck(
            status="placeholder",
            company=company,
            message="That is the sample value from .env.example, not a real key.",
        )

    issuer = detect_provider_from_key(key) if allow_prefix_check else None
    if issuer is not None and issuer != provider:
        issuing_company = COMPANIES.get(issuer, issuer.title())
        # company stays the SELECTED provider, not the issuer: the UI keys its
        # stale-result guard on the selected provider, and the instruction we
        # give ("PUT <selected>'S API KEY") is about the provider in use.
        return KeyCheck(
            status="mismatch",
            company=company,
            message=(
                f"This looks like an {issuing_company} key, but {company} is "
                f"selected. PUT {company.upper()}'S API KEY, or switch the "
                "provider above."
            ),
            detail=f"issuer={issuer}",
        )

    return None


def interpret_listing(provider: str, listing: ModelList) -> KeyCheck:
    """Turn an already-fetched model listing into a verdict.

    Split out from :func:`check_api_key` so the UI can reuse the listing it
    already fetched and cached for the dropdown, instead of calling the
    provider a second time purely to say "verified". The listing carries
    everything needed: a live source proves the key authenticated, and the
    recorded error text distinguishes rejection from an outage.
    """
    company = COMPANIES.get(provider, provider.title())

    if listing.source == "live":
        return KeyCheck(
            status="valid",
            company=company,
            models=list(listing.models),
            message=(
                f"Verified with {company} - "
                f"{len(listing.models)} models available to this key."
            ),
        )

    error = listing.error or ""
    if _looks_like_auth_failure(error):
        return KeyCheck(
            status="invalid",
            company=company,
            message=INVALID_KEY_MESSAGE,
            detail=error or None,
        )

    # The listing failed for a reason that is not authentication: offline, SDK
    # not installed, provider outage. Calling the key fake here would be a lie,
    # and an expensive one for the user.
    return KeyCheck(
        status="unreachable",
        company=company,
        message=(
            f"Could not reach {company} to verify this key. "
            "It may still be valid."
        ),
        detail=error or None,
    )


def check_api_key(provider: str, api_key: str, client: Optional[Any] = None) -> KeyCheck:
    """Verify a key against its provider and describe what it unlocks.

    Args:
        provider: 'anthropic' or 'openai' - the provider selected in the UI.
        api_key: The key to verify.
        client: Injectable SDK client (tests pass a stub; no network occurs).

    Returns:
        A KeyCheck. This never raises: a failing key check must not take the
        application down with it.
    """
    verdict = precheck_key(provider, api_key, allow_prefix_check=client is None)
    if verdict is not None:
        return verdict

    company = COMPANIES.get(provider, provider.title())
    key = (api_key or "").strip()
    try:
        listing = discover_models(provider, key, client=client)
    except Exception as exc:  # noqa: BLE001 - verification must never crash the app
        return KeyCheck(
            status="unreachable",
            company=company,
            message="Could not complete the check. The key may still be valid.",
            detail=str(exc),
        )

    return interpret_listing(provider, listing)


def check_balance(
    provider: str,
    api_key: str,
    model: str,
    completion_fn: Optional[Any] = None,
) -> KeyCheck:
    """Send the smallest possible request to confirm the key can actually pay.

    Listing models proves a key is *authentic*, but a key can be real and still
    have a zero balance - the model dropdown would look perfectly healthy while
    every extraction fails at request time. This spends exactly one output
    token on a one-word prompt so the account is charged the minimum the
    provider allows, and reads the outcome:

        funded      - the tiny completion succeeded; the key can pay
        no_balance  - authenticated but out of credit / quota
        invalid     - the key was rejected (fake, revoked, wrong provider)
        unreachable - the probe itself failed (offline, SDK missing, outage)

    Args:
        provider: 'anthropic' or 'openai'.
        api_key: The key to probe.
        model: The model to bill the one token against.
        completion_fn: Injectable callable(prompt) -> str (tests pass a stub;
            no network occurs). When omitted a real 1-token client is built.

    Returns:
        A KeyCheck. Never raises: a billing probe must not crash the app.
    """
    company = COMPANIES.get(provider, provider.title())

    # Reuse every cheap local guard first, so a placeholder or mismatched key
    # never reaches the paid endpoint.
    verdict = precheck_key(provider, api_key, allow_prefix_check=completion_fn is None)
    if verdict is not None:
        return verdict

    try:
        if completion_fn is None:
            # Imported here so the module stays importable without the SDKs.
            from src.extraction.providers import make_completion_fn

            completion_fn = make_completion_fn(
                provider, api_key, model, max_tokens=1
            )
        completion_fn("Hi")
    except Exception as exc:  # noqa: BLE001 - probe must never crash the app
        error = str(exc)
        if _looks_like_balance_failure(error):
            return KeyCheck(
                status="no_balance",
                company=company,
                message=insufficient_balance_message(company),
                detail=error,
            )
        if _looks_like_auth_failure(error):
            return KeyCheck(
                status="invalid",
                company=company,
                message=INVALID_KEY_MESSAGE,
                detail=error,
            )
        return KeyCheck(
            status="unreachable",
            company=company,
            message=(
                f"Could not reach {company} to test this key's balance. "
                "It may still be funded."
            ),
            detail=error,
        )

    return KeyCheck(
        status="funded",
        company=company,
        message=f"This {company} key is active and has available balance.",
    )
