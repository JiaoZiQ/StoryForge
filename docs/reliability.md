# Provider reliability

## M12 whole-book replay

The top scheduler is an idempotent PostgreSQL state machine over M11 Jobs and M5 chapter
checkpoints. Its child Job map, accepted chapter state, snapshot content hash, evaluation
version, and provider idempotency scope make worker crash recovery replay-safe. Redis loss
is recovered from Outbox and Job state.

## M11 distributed guarantees

At-least-once delivery is made effect-safe through leases, unique keys, and domain
constraints. Expired leases retry with bounds and exhaust into DLQ. Queue deployments
use Redis-backed provider rate and circuit state.

Reliability controls are finite and observable:

- exponential backoff with bounded attempts and injectable timing in tests;
- explicit transient/non-transient classification;
- process-local RPM, TPM, and concurrency admission;
- provider/model circuit breaker with closed/open/half-open states;
- total call deadline and declared fallback order;
- durable idempotency claim plus database uniqueness for provider attempts.

Timeout, server and upstream rate-limit failures may retry/fallback. Authentication,
refusal, privacy and budget failures do not. Circuit fast-fail is audited. Default
tests never sleep or access a network. Queue deployments select Redis-backed
RPM/TPM/concurrency admission and circuit state, so workers share those controls.
Inline SQLite development retains the deterministic process-local implementations.

Workflow checkpoints/domain artifacts own structured outputs. If a fresh process
replays a completed provider idempotency key, the gateway refuses another billable
call and requires reuse of that persisted domain artifact rather than storing the
provider body in the audit table.
