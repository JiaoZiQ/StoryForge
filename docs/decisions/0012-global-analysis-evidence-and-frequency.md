# ADR 0012: Global analysis evidence, knowledge, and frequency

## Status

Accepted for Milestone 12.

## Decision

Derive timeline and character/relationship trajectories primarily from accepted Facts and
GraphRelations tied to snapshot versions. Represent character knowledge explicitly with a
fact, learned chapter, source event, confidence, and status; author secrets are not role
knowledge. Preserve relationship history with valid ranges instead of overwriting it.

Measure foreshadowing with setup/payoff order, distance, accepted evidence, repeated or
missing payoff, and importance-weighted payoff rate. Run accepted-only timeline,
character/knowledge/relationship, foreshadowing, pacing, transition, and repetition checks
every configured chapter interval and after completion. Critical periodic findings pause;
medium/low findings accumulate for global revision.

## Consequences

Checks are explainable and future-safe, but intentionally do not claim complete semantic
time or personality reasoning. Frequency trades early detection against compute and is
configurable.
