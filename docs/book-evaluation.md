# Whole-book evaluation

Evaluation is based on an immutable BookSnapshot. Inputs are chapter average and minimum,
ending quality, timeline consistency, character arcs, important foreshadowing payoff,
pacing, transitions, repetition candidates, and a governed BookCritic result. Default
weights are validated to sum to one and all dimensions remain in 0–10.

A critical global issue blocks acceptance regardless of average score. The ending,
key-character arc, timeline, and important-foreshadowing payoff each have minimum gates.
High issues reduce confidence and can select targeted revision. Recommendations are
`accept`, `targeted_revision`, `human_review`, or `reject`.

The BookCritic receives the premise, book and chapter summaries, timeline codes, arc and
relationship summaries, foreshadowing and pacing metrics, score trend, and at most eight
bounded priority excerpts. It never receives the manuscript unconditionally. Prompts are
registry-versioned and calls pass privacy, budget, shared rate limit, circuit breaker,
idempotency, and usage audit layers. A critical issue cannot return a pass recommendation.
