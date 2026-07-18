# Provider reliability

Reliability controls are finite and observable:

- exponential backoff with bounded attempts and injectable timing in tests;
- explicit transient/non-transient classification;
- process-local RPM, TPM, and concurrency admission;
- provider/model circuit breaker with closed/open/half-open states;
- total call deadline and declared fallback order;
- durable idempotency claim plus database uniqueness for provider attempts.

Timeout, server and upstream rate-limit failures may retry/fallback. Authentication,
refusal, privacy and budget failures do not. Circuit fast-fail is audited. Default
tests never sleep or access a network. Current limits and circuit state are local to
one API process; distributed coordination is a documented future limitation.

Workflow checkpoints/domain artifacts own structured outputs. If a fresh process
replays a completed provider idempotency key, the gateway refuses another billable
call and requires reuse of that persisted domain artifact rather than storing the
provider body in the audit table.
