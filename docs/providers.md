# Provider registry and gateway

Milestone 10 centralizes LLM and embedding calls behind a validated registry and
governed gateway. A capability declares provider/model identity, type, context and
output limits, structured-output or embedding support, enabled state, external
egress, and versioned pricing. Registry data never contains credentials or a
sensitive endpoint.

Agents keep the existing typed `LLMProvider` contract. The composition root wraps
the raw Mock or OpenAI-compatible provider. Embedding indexing and vector-query
paths are wrapped separately but emit the same `ProviderCall` audit projection.
Unknown, disabled, type-incompatible, or structurally incapable models fail before
the provider is invoked.

Default built-ins are deterministic Mock chat primary/fallback and Mock hash
embedding. External models are opt-in through server settings. Custom registry and
pricing JSON files are startup-validated; a pricing file cannot reference a model
that is absent from the registry.

Provider health is deliberately non-billable: it reports configuration, capability,
pricing availability and process-local circuit state. Use the explicitly gated
smoke CLI for a real network/authentication check.
