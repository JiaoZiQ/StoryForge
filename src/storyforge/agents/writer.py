"""Writer agent implementation."""

from storyforge.agents.base import AgentResult, StructuredAgent
from storyforge.schemas.context import ChapterContext
from storyforge.schemas.generation import ChapterDraft


class WriterAgent(StructuredAgent):
    """Generate one structured chapter draft from bounded canonical context."""

    prompt_name = "writer"

    def write(self, context: ChapterContext) -> AgentResult[ChapterDraft]:
        """Return a validated draft without performing persistence."""
        return self._invoke(context, ChapterDraft)
