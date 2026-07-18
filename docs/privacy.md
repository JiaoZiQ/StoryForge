# Provider privacy and redaction

Privacy is enforced before any external call:

- `offline`: external LLM and embedding egress is blocked.
- `strict`: only task-required context is sent and high-confidence credentials,
  database passwords, email addresses and phone numbers are redacted.
- `standard`: task-required typed context is allowed without strict personal-data
  redaction.

Changing policy never weakens the accepted/future/candidate repository filters.
Provider audit rows contain hashes and metadata only. Logs/API/CLI/Web projections
exclude keys, base URLs, full prompts, full chapter text, response bodies,
tracebacks and embedding arrays. Redaction is conservative and not a complete DLP
system; operators remain responsible for deployment policy and secret management.

Real-provider smoke testing is disabled by default and sends a fixed minimal JSON
probe rather than project or story content. Never commit `.env` or expose keys to
browser `NEXT_PUBLIC_*` variables.
