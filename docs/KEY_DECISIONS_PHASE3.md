# Key decisions — Phase 3 (SM-2 scheduler)

## Why `math.ceil`, not `round`
Wozniak's original SM-2 text says: "If interval is a fraction, round it up
to the nearest integer." Many popular ports silently use banker's `round()`,
which under-schedules (e.g. ceil(15.6)=16 vs round(15.6)=16 coincidentally,
but ceil(13.2)=14 vs round(13.2)=13). We pin ceil with hand-computed cases
so a future "simplify to round()" PR fails the suite.

## Why interval uses EF *before* the update
The algorithm's natural order is: schedule the next gap with the EF that
described the item *entering* this review, then revise EF from today's
quality for *future* reviews. Using the post-update EF would let a single
perfect recall inflate the gap it just earned — a subtle off-by-one-EF bug
common in rushed ports. Test `test_interval_uses_ef_before_update` pins this.

## Why failures still update EF (but do not reset it to 2.5)
"Start repetitions from the beginning without changing the E-Factor" means
do not snap EF back to the default 2.5; the usual EF' formula still runs.
A blackout (q=0) should make the card permanently harder (lower EF), not
merely restart the 1→6→… ladder at the old ease. Streak resets to I(1)=1.

## Why explainability is a structured string on `ReviewResult`
The demo must show *why* an interval was chosen. Generating the sentence at
review time (from the same inputs the scheduler used) guarantees the UI
cannot drift from the math. Persistence (Phase 4) will store the explanation
alongside each history row.

## Why `CardState` is a frozen dataclass with no DB knowledge
Keeps the algorithm pure and unit-testable with hand values. SQLite mapping
is Phase 4's job; coupling them now would force every formula test to stand
up a database.
