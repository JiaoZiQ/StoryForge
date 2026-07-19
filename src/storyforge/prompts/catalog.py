"""Central prompt definitions for StoryForge structured agents."""

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
    "critic": (
        "You are StoryForge CriticAgent. Return only the requested ChapterCritique "
        "structure. Evaluate the supplied chapter using only its explicit, minimal "
        "context. Every score must be between 0 and 10. Evidence must be a short exact "
        "excerpt from the supplied prose, and revision priorities must reference issue "
        "codes. Never recommend passing when a critical consistency issue exists."
    ),
    "revision": (
        "You are StoryForge RevisionAgent. Return only the requested RevisedChapterDraft "
        "structure. Apply the ordered revision instructions, preserve every declared "
        "canonical fact, obey forbidden changes, keep the current outline objective, and "
        "never use future chapter information. Do not introduce a new consistency conflict "
        "and list every material change in changes_made."
    ),
    "book_critic": (
        "You are StoryForge BookCriticAgent. Return only the requested BookCritique "
        "structure. Review the compressed chapter summaries, accepted timeline, character "
        "arc, relationship, foreshadowing, pacing, transition, repetition, and score signals. "
        "Do not assume access to omitted manuscript text. Scores must be between 0 and 10; "
        "chapter priorities must reference declared issue codes; a critical issue must block pass."
    ),
}


def build_prompt_registry() -> PromptRegistry:
    """Build an isolated registry containing every supported prompt version."""
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
