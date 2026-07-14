"""Revision agent implementation."""

from storyforge.agents.base import AgentResult, StructuredAgent
from storyforge.revision.models import RevisedChapterDraft, RevisionAgentRequest


class RevisionAgent(StructuredAgent):
    """Rewrite one immutable version from a bounded structured brief."""

    prompt_name = "revision"

    def revise(self, request: RevisionAgentRequest) -> AgentResult[RevisedChapterDraft]:
        """Return a validated replacement draft without touching persistence."""
        if not request.original_content.strip():
            raise ValueError("RevisionAgent requires non-empty source content")
        result = self._invoke(request, RevisedChapterDraft)
        if not result.output.changes_made:
            raise ValueError("RevisionAgent must report changes_made")
        revised = result.output.content.casefold()
        for fact in request.brief.must_preserve_facts:
            parts = [item.strip().casefold() for item in fact.split("|") if item.strip()]
            anchors = (parts[0], parts[-1]) if len(parts) >= 2 else tuple(parts)
            if any(anchor not in revised for anchor in anchors):
                raise ValueError("RevisionAgent removed a must-preserve fact anchor")
        original = request.original_content.casefold()
        for forbidden in request.brief.forbidden_changes:
            marker = forbidden.strip().casefold()
            if marker and marker in revised and marker not in original:
                raise ValueError("RevisionAgent introduced a forbidden change")
        return result
