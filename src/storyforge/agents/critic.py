"""Structured literary critique agent."""

from storyforge.agents.base import AgentResult, StructuredAgent
from storyforge.evaluation.models import ChapterCritique, CriticContext
from storyforge.exceptions import EvaluationError


class CriticAgent(StructuredAgent):
    """Produce a validated literary review without accessing persistence."""

    prompt_name = "critic"

    def critique(self, context: CriticContext) -> AgentResult[ChapterCritique]:
        """Evaluate one non-empty chapter through the shared LLM boundary."""
        if not context.content.strip():
            raise EvaluationError("A chapter without content cannot be critiqued")
        result = self._invoke(context, ChapterCritique)
        for issue in result.output.issues:
            if issue.evidence and issue.evidence not in context.content:
                raise EvaluationError("Critic evidence is not present in chapter content")
        return result
