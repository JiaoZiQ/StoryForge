# Asynchronous jobs

Milestone 12 adds `RUN_BOOK` and `RESUME_BOOK` top Jobs. A BookRun links child chapter
workflow Jobs with deterministic idempotency keys. PostgreSQL remains authoritative and a
top-worker lease recovery resumes from the persisted node/child map without duplicating
versions, evaluations, snapshots, provider calls, or cost.

Milestone 11 moves long-running planning, chapter generation/evaluation, workflows,
and memory reindexing behind durable Jobs. PostgreSQL is the authority for Job,
JobEvent, OutboxMessage, workflow, version, fact, usage, and cost state. Redis is a
rebuildable transport and notification layer; it never becomes the only copy of a
user-visible result.

## Lifecycle and delivery

Creation writes the Job, initial JobEvent, and OutboxMessage in one database
transaction. A dispatcher claims outbox rows (`FOR UPDATE SKIP LOCKED` on
PostgreSQL), publishes only the Job ID to Dramatiq/Redis, and marks the row
published. Delivery is at least once. Database uniqueness and handler idempotency
make duplicate delivery harmless; StoryForge does not claim exactly-once delivery.

Workers conditionally acquire a database lease, heartbeat it, execute a registered
handler through an Application Service, and persist bounded result metadata. An
expired lease is retried with `available_at`; exhausted infrastructure attempts go
to the dead-letter state. Redis-loss recovery reopens the published enqueue intent
for stale queued Jobs from PostgreSQL.

Cancellation and pause are cooperative. They are observed at safe workflow/node
boundaries, do not forcibly terminate a provider HTTP call, preserve accepted
history, and never promote unaccepted candidate facts. Resume reuses the same Job
and creates a new outbox delivery attempt without repeating completed idempotent
effects.

## Admission and safety

The registry accepts only controlled `JobType` values and statically mapped
handlers. Payloads are JSON-only and reject credentials, keys, database URLs, and
chapter content. Global/project pending limits and the one-active-Job-per-chapter
constraint protect capacity; hard rejection returns HTTP 429 with `Retry-After`.
Priority is bounded and no cross-project fairness guarantee is currently made.

Development may retain explicit synchronous endpoints for debugging. Production
configuration requires queue mode, Redis-backed distributed rate limiting, and a
shared circuit breaker. The current trusted-network deployment has no user
authentication, tenant authorization, or per-project SSE ownership enforcement.

See [queue.md](queue.md), [sse.md](sse.md), and
[ADR 0010](decisions/0010-asynchronous-jobs-and-transactional-outbox.md).
