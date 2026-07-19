# Book runs

`BookRun` is the durable identity of one whole-book attempt and is linked to one top-level
Job. PostgreSQL is authoritative for status, current node, child Job IDs, accepted chapter
count, best/final snapshot, usage, budget, and errors. Redis only transports Job IDs and
event wake-ups.

The default `sequential` mode accepts chapter N before chapter N+1 can use its facts,
memory, state, and graph. `dependency_aware` validates an acyclic dependency map and may
prepare bounded accepted-only metrics concurrently, but prose acceptance remains ordered.
Concurrency is capped at four and sequential mode requires one.

States are `pending`, `planning_validation`, `generating`, `paused`, `global_review`,
`global_revision`, `completed`, `completed_needs_review`, `cancel_requested`, `cancelled`,
`failed`, and `budget_blocked`. Transitions are centralized. One partial unique index
prevents concurrent active runs for the same project.

Every configured chapter interval runs accepted-only global rules. Critical timeline
findings pause the run; lesser findings are retained for the final global review. Resume
reuses the child Job/workflow map. Cancel stops new children and cannot promote a candidate
version. Progress reserves the final 25 percent for snapshot and global review.

Budgets bound estimated cost, total tokens, provider calls, chapter work, global review,
and global revision. A hard block occurs before a provider call and preserves the best
available snapshot. Increasing limits and resuming repeats the check without duplicating
usage.
