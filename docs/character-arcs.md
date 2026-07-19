# Character arcs and knowledge

CharacterArcPoint stores accepted chapter-by-chapter goals, emotion, physical state,
location, knowledge, relationships, conflicts, decisions, and evidence. Rules check state
continuity, unexplained goal/personality or ability changes, unsupported relationship
changes, injury continuity, absent protagonists, and incomplete arcs.

CharacterKnowledge explicitly links a character to an accepted Fact, learned chapter,
source event, confidence, and status (`known`, `forgotten`, `misled`, or `incorrect`).
Author-side secrets and future reveals do not become character knowledge. Knowledge
transfer requires an accepted event. ContextBuilder continues to select only facts valid
before the chapter being written.

RelationshipHistory stores trust, friendship, hostility, family, romance, alliance,
mentorship, and authority changes with chapter/version evidence and a validity range.
History is appended rather than overwritten, so unsupported reversals remain detectable.
