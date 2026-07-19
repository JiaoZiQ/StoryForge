# Job progress over SSE

BookRun has the same durable event and replay contract at
`/api/v1/book-runs/{book_run_id}/events/stream`. Events contain safe progress, node, chapter,
snapshot, and status identifiers, not prose. Terminal states close the stream; CLI and Web
fall back to polling after a transport failure.

`GET /api/v1/jobs/{job_id}/events/stream` is a one-way Server-Sent Events stream.
PostgreSQL JobEvent rows are the replay authority. The server first returns rows
after `Last-Event-ID`, then uses Redis Pub/Sub only as a wake-up hint and rechecks
the database. A missing notification cannot lose progress.

Events expose IDs, status, stable message code, safe message, step, progress,
attempt, worker ID, and timestamp. They never include payloads, prompts, chapter
bodies, provider credentials, Authorization headers, database URLs, or tracebacks.
Heartbeats are SSE comments. Terminal status closes the stream, client disconnect
releases resources, and a global semaphore bounds connections; saturation returns
the shared HTTP 429 error with `Retry-After`.

The Next.js `/backend` proxy streams the upstream body without buffering. Browser
`EventSource` performs reconnect and sends its last event ID; the Job page also
polls at low frequency while SSE is unavailable and labels the visible mode as
`realtime`, `polling`, or `stopped`. Event IDs are database primary keys, so query
deduplication prevents duplicate timeline items.

There is currently no authentication. Deploy the gateway only on a trusted network
or add an authenticating reverse proxy; project ownership cannot be enforced until
the planned authorization milestone.
