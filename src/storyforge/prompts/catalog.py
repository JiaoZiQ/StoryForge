"""Central prompt definitions for planner, writer, and fact extractor agents."""

from storyforge.llm import PromptMessageTemplate, PromptRegistry, PromptTemplate

PROMPT_VERSION = "v1"

_SYSTEM_PROMPTS = {
    "planner": (
        "You are StoryForge PlannerAgent. Return only the requested NovelPlan structure. "
        "Create exactly the requested number of sequential chapters, use only declared "
        "characters and locations, and keep setup/payoff chapters within bounds."
    ),
    "writer": (
        "You are StoryForge WriterAgent. Return only the requested ChapterDraft structure. "
        "Follow the current outline and canonical context, avoid forbidden reveals, and do "
        "not invent knowledge from future chapters or author-only secrets."
    ),
    "fact_extractor": (
        "You are StoryForge FactExtractorAgent. Return only the requested extraction "
        "structure. Extract canonical facts and state changes supported by exact quotes in "
        "the supplied prose; never infer facts from future plans."
    ),
}


def build_prompt_registry() -> PromptRegistry:
    """Build an isolated registry containing every supported M3 prompt version."""
    registry = PromptRegistry()
    for agent_name, system_text in _SYSTEM_PROMPTS.items():
        registry.register(
            PromptTemplate(
                name=f"{agent_name}.system",
                version=PROMPT_VERSION,
                messages=(PromptMessageTemplate(role="system", template=system_text),),
            ),
            make_default=True,
        )
        registry.register(
            PromptTemplate(
                name=f"{agent_name}.user",
                version=PROMPT_VERSION,
                messages=(
                    PromptMessageTemplate(
                        role="user",
                        template="Validate and process this typed JSON payload:\n{payload}",
                    ),
                ),
            ),
            make_default=True,
        )
    return registry
