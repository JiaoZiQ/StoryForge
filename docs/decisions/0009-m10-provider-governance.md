# ADR 0009: Central provider governance

Status: accepted for Milestone 10.

## Decision

All LLM and embedding calls pass through a task-aware governed gateway. Provider
capabilities and prices are registry data; secrets stay in process settings. Routes
are predefined profiles. Privacy is an explicit project policy enforced before
egress. Usage/cost/audit is persisted per attempt, while provider request and
response bodies are not persisted.

We use Decimal versioned pricing snapshots, preflight project reservations and
workflow ceilings. Unknown pricing blocks by default. Retry and fallback are
bounded and error-class aware; rate limits and circuit state are process-local.
Budget/privacy/auth/refusal never fall back. Every attempt is content-free and
auditable.

Idempotency stores a durable claim and reference to the successful ProviderCall,
not the structured response. Workflow checkpoints and domain artifacts own output;
a fresh replay must reuse those artifacts and cannot create another paid call.
PostgreSQL row locking provides budget concurrency; SQLite is a development-only
single-process approximation.

## Consequences

API/CLI/Web expose safe registry, usage, budget and settings projections without
credentials. Provider health is a non-network configuration view; real smoke tests
are explicit, tiny and disabled by default. Current rate/circuit controls do not
coordinate multiple replicas, pricing is operator-maintained rather than guessed,
and redaction is not a general DLP engine. Distributed queues, authorization and
multi-tenant billing remain outside Milestone 10.
