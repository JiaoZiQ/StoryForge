# ADR 0010: Dramatiq/Redis jobs with PostgreSQL authority

Status: accepted for Milestone 11.

Use Dramatiq/Redis for at-least-once transport carrying only Job IDs. PostgreSQL owns
state, events, leases, idempotency, results, heartbeats, and outbox; LangGraph remains
the workflow engine. Actor retry is disabled so retry layers do not multiply. Lease
claims and domain unique keys make redelivery safe. Celery, Kafka, and a Redis result
backend are excluded because PostgreSQL is authoritative.

## Alternatives

- Celery is mature but its result backend, retry, beat, and canvas surface is larger
  than this milestone needs. It would also invite a second workflow abstraction next
  to LangGraph.
- RQ is simple but provides fewer explicit middleware/time-limit and message-policy
  seams for the required audit boundary.
- A custom PostgreSQL queue would reduce dependencies but would require StoryForge
  to build wake-up, worker lifecycle, acknowledgement, and queue tooling itself.
- Kafka is optimized for durable event streams and consumer groups; StoryForge needs
  bounded work dispatch, not long-retained ordered streaming.

Dramatiq 2 supports Python 3.12, independent worker processes, Redis transport,
bounded actor time limits, and deterministic in-memory substitution. Dramatiq message
retries are disabled (`max_retries=0`). Provider retry remains the short transient
call layer; durable Job retry handles classified infrastructure/process failure using
database `available_at` and a maximum attempt count. Validation, budget blocks, and
user cancellation are not automatically retried.

## State and delivery decisions

Job creation and outbox intent are one PostgreSQL transaction. Dispatchers claim in
bounded batches using `FOR UPDATE SKIP LOCKED`; a crash after publish can redeliver.
Workers therefore conditionally acquire one database lease and every business side
effect retains its existing database idempotency key/unique constraint. This is
at-least-once delivery with idempotent effects, not exactly-once execution.

Redis stores queue messages, short-lived SSE wake-ups, rate-limit counters, circuit
state, and rebuildable cache only. It never uniquely owns Job/WorkflowRun,
ChapterVersion, Evaluation, Fact, ProviderCall, cost, budget, or user-visible event
history. Stale queued Jobs reopen their published outbox intent after Redis loss.
Production fails closed if required Redis governance is unavailable; explicit
development inline mode may use process-local controls.

Workers heartbeat a renewable PostgreSQL lease. Expiry schedules bounded recovery;
attempt exhaustion enters the DLQ. SIGTERM is handled by Dramatiq graceful shutdown,
and the database lease covers forced termination. Each registered Job type has an
explicit message time limit.

Cancellation and pause are cooperative at safe Application Service/LangGraph node
boundaries. Cancellation does not claim to abort an in-flight provider request and
never rolls back accepted history or promotes candidates. Pause releases ownership;
resume uses the same Job plus a new outbox attempt and relies on workflow/provider
idempotency to avoid duplicate versions, evaluations, calls, or cost.

PostgreSQL JobEvent is the replay/audit stream. Redis Pub/Sub only wakes SSE readers.
SSE was selected over WebSocket because progress is one-way; `Last-Event-ID` replays
from PostgreSQL before live notifications. Connection limits and heartbeats are
bounded. The trusted-network limitation is explicit until authentication exists.

Distributed provider RPM/TPM/concurrency and circuit state use namespaced Redis keys
so all workers share admission and open/half-open decisions. Budget and provider
idempotency remain PostgreSQL-authoritative. Production cannot silently select inline
execution.
