# Model routing

Routing is by controlled `TaskType` plus project `ModelProfile`, never by an
arbitrary client model string. Tasks include planning, drafting, fact extraction,
critique, revision, version comparison, document embedding and query embedding.

- `offline` selects local Mock models and blocks external egress.
- `economy`, `balanced`, and `quality` are predefined registry-backed profiles.
- Embedding routes use the independently configured embedding capability.
- Route validation checks model type and structured-output support.

Fallback order is explicit and cycle-free. Privacy/budget/auth/refusal failures are
terminal; bounded transient failures may retry and then move to the next declared
fallback. Profile changes are rejected while a project has an active workflow so a
single run has stable routing semantics.
