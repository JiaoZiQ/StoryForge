# Usage, pricing, and budgets

Every provider attempt records token counts and provenance (`provider_reported`,
`local_estimate`, `mock`, or `unknown`). Pricing uses Python `Decimal` and an
immutable snapshot containing provider/model, per-million rates, currency, version,
and effective date. Estimated cost and provider-billed cost are different fields;
StoryForge does not claim that an estimate is an invoice.

Project budgets store soft/hard lifetime limits, estimated/billed spend, and an
estimated reservation. Preflight reserves before network access, settlement
releases the reservation and records actual estimated usage, and failures release
it. Hard limits block; soft limits warn. Workflow ceilings separately bound calls,
tokens, and cost. Unknown prices are blocked unless an operator explicitly enables
them.

PostgreSQL uses row locks during budget mutation/reservation. SQLite remains a
single-process development fallback and cannot provide equivalent distributed
concurrency guarantees. API and CLI serialize monetary values as decimal strings.
