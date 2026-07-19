# ADR 0011: BookRun scheduling and immutable snapshots

## Status

Accepted for Milestone 12.

## Decision

Use a PostgreSQL-authoritative `BookRun` linked to a top Job. Accept prose sequentially by
default because chapter N+1 consumes chapter N facts, character state, foreshadowing, and
memory. `dependency_aware` may only parallelize bounded preparation with an acyclic graph;
it does not enable unconstrained chapter-body generation. This is why M12 does not run all
chapters in parallel.

Freeze reviews in `BookSnapshot` as a chapter-number to immutable ChapterVersion-ID map,
stable hash, and aggregates. Do not copy the manuscript. A later accepted version creates
a new snapshot and supersedes the old accepted snapshot without mutating it.

## Consequences

Runs recover from PostgreSQL even if Redis is lost. Reviews and later export are
reproducible. Acceptance throughput is lower than unconstrained generation, but future
information and state races are prevented.
