"""Structured, governed whole-book literary critic."""

from storyforge.agents.base import AgentResult, StructuredAgent
from storyforge.book.models import BookCriticContext, BookCritique
from storyforge.exceptions import EvaluationError


class BookCriticAgent(StructuredAgent):
    """Review compressed global signals without receiving a complete manuscript."""

    prompt_name = "book_critic"

    def critique(self, context: BookCriticContext) -> AgentResult[BookCritique]:
        if not context.chapter_summaries:
            raise EvaluationError("A book without chapter summaries cannot be critiqued")
        return self._invoke(context, BookCritique)
