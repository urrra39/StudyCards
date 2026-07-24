# Key decisions — Phase 4 (SQLite persistence)

## Why dual write: `cards` current state + `review_history` immutable log
`cards` answers "what's due today?" in O(log n) via the due_date index.
`review_history` answers "why is this interval what it is?" and feeds the
Phase 5 evaluation / any future analytics. Every `record_review` updates
both in one transaction so they cannot diverge after a crash.

## Why the repository calls `scheduler.review` rather than re-implementing SM-2
A single source of truth for the formulas. Persistence tests that pin
intervals 1→6→16 after ratings 5,4,5 are *integration* pins against the
same hand math as Phase 3 — if either layer drifts, these fail.

## Why ISO-8601 text for dates
SQLite has no real date type. Text `YYYY-MM-DD` sorts correctly for
`due_date <= ?` range scans and round-trips cleanly through
`date.fromisoformat` without a custom adapter.

## Why one connection per operation
Streamlit reruns the script on every widget interaction; a long-lived
connection object in `st.session_state` is a footgun (thread affinity,
stale locks). Short-lived connections with `PRAGMA foreign_keys=ON` each
time are cheap for a local demo DB and correct under concurrent tabs.

## Why explanations are stored on every history row
Explainability must survive page reloads. Recomputing from
(before_state, quality) would also work, but storing the sentence freezes
the UX copy that the user actually saw — valuable if the formatter ever
changes.
