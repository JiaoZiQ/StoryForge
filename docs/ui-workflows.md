# Provider governance UI workflows

The global **Providers** page shows public capabilities, pricing availability,
configuration health and circuit state. Project navigation adds **Usage & Cost**,
**Budget**, and **Model Settings**. Workflow detail shows aggregate provider calls,
tokens, estimated cost, fallbacks and rate limits alongside its existing timeline.

Budget forms submit only limits/currency/period/enabled; spent values are read-only.
Model settings use predefined selects and never accept a key, endpoint, or arbitrary
model. Loading, error and empty states use the shared accessible UI components.
Browser calls remain same-origin through the Next.js server proxy, and OpenAPI types
plus Zod response validation cover all governance responses.

## Asynchronous long actions

Plan generation, chapter generation, full workflow, and memory reindex buttons
submit a durable Job and navigate to its detail page. The browser no longer owns
the lifetime of a long backend request. Job detail opens one EventSource, replays
database events after reconnect, keeps bounded polling as a visible fallback, and
stops both at terminal state. It then invalidates related project, chapter, and
usage queries. Cancel and pause are cooperative; retry/discard are available only
for dead-lettered Jobs. Job result and errors are bounded safe summaries.
