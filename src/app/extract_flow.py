"""Pure decision logic for the upload/extract flow (NO Streamlit imports).

This lives in its own module, separate from ``streamlit_app`` (which imports
``streamlit`` at module load), precisely so the safety-critical branch that
guards paid model calls can be imported and unit-tested in a headless
environment. Keep this module dependency-free.
"""
from __future__ import annotations


def should_extract(
    pending: bool, confirmed: bool, n_chunks: int, soft_limit: int
) -> bool:
    """Go/no-go decision for extraction.

    Rules:
    * ``pending`` (the fingerprint handshake is armed) is required. Without it
      nothing runs, so a stray rerun can never trigger extraction.
    * Small docs (``n_chunks <= soft_limit``) run as soon as they are armed.
    * Large docs additionally require explicit ``confirmed`` consent.

    Encoding the rule here (rather than as ``if not st.button(): return``
    scattered through the UI) is what makes it testable and stops the old
    button+checkbox trap from silently coming back.
    """
    if not pending:
        return False
    if n_chunks <= soft_limit:
        return True
    return confirmed
