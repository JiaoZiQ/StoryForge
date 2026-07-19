# Targeted whole-book revision

BookRevisionPlanner sorts critical timeline and knowledge leaks first, followed by ending,
major foreshadowing, character arc, transition, plot/pacing, and repetition issues. It
selects only the configured maximum chapters, produces deterministic dependency order,
preserve-fact constraints, affected later chapters, rerun checks, and call/token/cost
estimates. Insufficient budget narrows or blocks the plan rather than selecting unlimited
work.

Each selected chapter uses the existing immutable chapter workflow: a new ChapterVersion
is written, facts are re-extracted and evaluated, versions are compared, and only an
accepted winner promotes facts, memory, graph, and state. Earlier changes mark later
chapters `recheck_required` or `revision_required`; they are never silently assumed valid.
The BookRun then creates a new snapshot and reruns global analysis.

Global rounds are bounded. A worse revision cannot replace the best snapshot. At the
round, budget, or retry ceiling, the best snapshot is retained as `needs_review` and no
unaccepted candidate fact becomes visible.
