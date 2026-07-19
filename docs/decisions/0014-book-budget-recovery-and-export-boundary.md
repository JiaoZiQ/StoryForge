# ADR 0014: Book budget, recovery, idempotency, and export boundary

## Status

Accepted for Milestone 12.

## Decision

Share hard BookRun call/token/cost ceilings across child Jobs and reserve before provider
calls. Budget exhaustion pauses at a safe boundary and preserves the best snapshot. Resume
rechecks the enlarged budget.

Use the M11 Job/Outbox/lease model plus child chapter checkpoints. Persist the current node,
child Job map, immutable version/evaluation/fact keys, snapshot hash, and scoped provider
idempotency so top-worker or child-worker replay cannot duplicate side effects or charges.
Redis remains non-authoritative.

Do not add PDF, DOCX, or ePub export in M12. Export must later consume an accepted immutable
BookSnapshot and needs separate layout, font, metadata, and accessibility acceptance.

## Consequences

Recovery is slower than an in-memory orchestrator but auditable. Hard limits may require an
operator to resume. Export and publication workflows remain explicitly outside M12.
