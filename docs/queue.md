# Queue, dispatcher, and workers

StoryForge uses Dramatiq 2 with Redis 7.4 as the transport. Celery and RQ were
considered; Dramatiq provides the required worker model with a smaller operational
surface. A custom database queue was rejected because it would duplicate broker
operations. Kafka is not used: ordered event streaming and long retention are not
requirements for this milestone.

Compose runs `redis`, `dispatcher`, and two `worker` replicas from the backend
image. All application containers run as UID 10001 on an internal network. Redis
has a healthcheck and a namespaced key prefix. PostgreSQL migrations and Redis
health gate dispatcher/worker startup.

The dispatcher polls in bounded batches and sleeps only between empty batches. It
uses durable outbox claims, bounded retry, and safe error summaries. Workers accept
only Job IDs, acquire a conditional PostgreSQL lease, heartbeat before expiry, and
re-check ownership before writing an outcome. Dramatiq transport retries are
disabled; StoryForge owns delayed Job retry so provider retry and Job retry cannot
multiply without bounds.

Each Dramatiq subprocess also registers before its first Job and emits an idle
keepalive at `STORYFORGE_WORKER_HEARTBEAT_SECONDS`. This keepalive updates only
worker liveness, so it cannot overwrite a concurrent BUSY/current-Job projection.
The API projects records older than `STORYFORGE_WORKER_OFFLINE_AFTER_SECONDS` as
`offline`; a stopped container is therefore not reported as a live worker forever.

Redis contains queue messages, rate-limit/circuit state, and short-lived Pub/Sub
notifications. PostgreSQL contains every durable business state and replayable
event. After Redis flush/restart the dispatcher re-delivers stale queued work from
published outbox intent; duplicate messages are expected and safe. Redis persistence
is enabled in the development Compose file for easier restart testing, but recovery
does not depend on it.

```powershell
docker compose ps
docker compose exec -T api storyforge worker status --output json
docker compose exec -T api storyforge job list --output json
docker compose exec -T api storyforge job dead-letter --output json
```

Graceful worker shutdown is delegated to Dramatiq: SIGTERM stops new intake and
allows the configured worker process to finish its current message within the
bounded actor time limit. Expired database leases are the crash/forced-shutdown
recovery mechanism.
