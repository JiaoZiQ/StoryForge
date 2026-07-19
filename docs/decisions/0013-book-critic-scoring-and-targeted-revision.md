# ADR 0013: Compressed BookCritic, blocking score, and targeted revision

## Status

Accepted for Milestone 12.

## Decision

Send BookCritic a bounded typed digest—book/chapter summaries, global metrics, conflict
codes, score trend, and at most eight excerpts—through the governed Provider Router. Never
send the entire manuscript by default.

Book scoring combines chapter average/minimum and global dimensions, but critical issues,
a weak ending, a broken key arc, or inadequate important-foreshadowing payoff block pass.
Plan targeted revision deterministically, cap chapters per round, order dependencies, and
record preserve constraints and estimates. If an early chapter changes, mark affected
later chapters for recheck/revision before a new snapshot can be accepted. Limit global
rounds and retain the best snapshot.

## Consequences

The critic supplements rule evidence rather than choosing unlimited work. Token cost and
privacy exposure are bounded. Some whole-manuscript stylistic nuance remains a human-review
limitation.
