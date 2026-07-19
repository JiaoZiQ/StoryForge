"""Deterministic English fixtures for the offline Milestone 5 workflow demo."""

from storyforge.demo import build_demo_critique
from storyforge.evaluation.models import ChapterCritique
from storyforge.llm import MockLLMProvider, PromptRequest
from storyforge.revision import RevisedChapterDraft
from storyforge.schemas.generation import (
    ChapterDraft,
    CharacterStateUpdate,
    ExtractedFact,
    FactExtractionResult,
    StyleSelfCheck,
)
from storyforge.schemas.planning import (
    ChapterPlan,
    CharacterPlan,
    LocationPlan,
    NovelPlan,
    StoryRulePlan,
)

_DRAFT_CONTENT = """
Before sunrise, Mara crossed the abandoned quay with the archive map folded inside her coat. Salt rattled against the warehouse windows, and every lamp along the seawall pointed toward the dark tide archive. She counted the doors twice before choosing the narrow entrance beside the broken crane.

Mara enters the tide archive while the harbor clock marks six uneven strokes. Inside, shelves lean toward one another above careful rows of waterlogged ledgers. She photographs the floor, checks the dust for recent tracks, and leaves a chalk mark where the corridor divides.

At the first desk she finds a register whose final page has been removed. The remaining fibers are fresh, unlike the swollen paper around them. A pencilled inventory number directs her to a cabinet built into the northern wall, where a weak vibration travels through the lock.

"Stay by the door and call the harbor office if the lower alarm turns red," Mara tells Ivo. "Do not follow me into the records tunnel, even if you hear the pumps start. We need a witness outside more than we need another pair of hands below."

The cabinet opens only after Mara aligns three brass rings with the tide marks scratched into its frame. A bundle of receipts lies inside, wrapped around a small key darkened by age. Mara lifted the brass key and compared its teeth with the drawing on her map.

Mara finds the brass key beneath a receipt signed by her missing mentor. The discovery changes the investigation because the signature is dated two years after his reported death. She records the date, the ink color, and the cabinet number before touching anything else.

When the pumps begin, cold water threads across the tiles instead of rising from the drains. Mara follows its path to a sealed service hatch, but she refuses to open it without equipment. The brass key fits the hatch, confirming a route without forcing her to take it.

She returns upstairs as daylight reaches the dusty windows. Ivo has kept the entrance clear and logged every sound from below. Mara seals the key in an evidence sleeve, copies the torn register number, and schedules a witnessed return for the evening tide.

Outside, the harbor clock is silent. Mara notices one wet footprint beside her own dry tracks, leading away from the building toward the occupied customs pier. She does not follow; she photographs it, marks the direction, and calls the office before the print can fade.
""".strip()

_REVISED_CONTENT = """
Rain had stopped before Mara reached the abandoned quay, leaving the warehouse roofs bright with salt. She kept the archive map inside a clear evidence sleeve and asked Ivo to photograph the unbroken dust at the entrance before either of them crossed it.

Mara enters the tide archive at six, when the harbor clock misses its final stroke. The missing sound gives her a reference point for the pump vibration under the floor. She marks the time, the weather, and the position of every open door.

At the first desk, a register ends with a page cut cleanly from its binding. Mara compares the pale fibers with the swollen paper around them and concludes that the removal is recent. The remaining inventory code leads directly to a cabinet in the northern wall.

"Wait where the radio works," she tells Ivo. "If the lower alarm turns red, call the harbor office and read them the cabinet number. Do not come after me; a clear record of what happens here matters more than speed."

Three brass rings surround the cabinet lock. Mara aligns them with the measured tide marks instead of guessing, then photographs the opened compartment. Receipts surround a small key, and each receipt carries the same shipping seal found on the missing register page.

Mara lifted the brass key with gloved fingers. Mara finds the brass key beneath a receipt signed by her missing mentor, dated two years after his reported death. The signature turns the search from an accident inquiry into evidence of a deliberate disappearance.

She records the date, ink, seal, and cabinet number before testing the key against the service hatch. It fits, but she does not open the hatch. The outline of fresh moisture around its frame proves that someone used the lower route during the current tide.

The pumps start with a slow metallic knock. Water runs across the tiles toward the hatch rather than away from it, revealing the direction of the hidden line. Mara samples the water, seals the key, and returns to Ivo without disturbing the tunnel.

By daylight, they have two independent logs and a complete evidence list. A single wet footprint crosses their dry tracks toward the customs pier. Mara photographs its direction and calls the harbor office, choosing a witnessed return over a reckless pursuit.
""".strip()


def build_m5_plan(target_chapters: int = 3) -> NovelPlan:
    """Return a compact future-safe plan for one workflow demonstration project."""
    chapters = [
        ChapterPlan(
            chapter_number=number,
            title=f"Tide Archive {number}",
            objective=(
                "Recover and document the brass archive key."
                if number == 1
                else f"Continue the archive investigation without revealing chapter {number + 1}."
            ),
            summary=f"Mara advances the archive investigation in chapter {number}.",
            key_events=(
                ["Mara enters the tide archive", "Mara finds the brass key"]
                if number == 1
                else [f"Mara completes investigation stage {number}"]
            ),
            participating_characters=["Mara"],
            locations=["Tide Archive"],
            ending_hook="A new physical clue points toward the customs pier.",
        )
        for number in range(1, target_chapters + 1)
    ]
    return NovelPlan(
        logline="An archivist traces a disappearance through a tidal records network.",
        themes=["memory", "evidence"],
        world_summary="A coastal city preserves shipping history in mechanical tide archives.",
        central_conflict="Mara must prove deliberate concealment without damaging the evidence.",
        ending_direction="The archive record is restored and the disappearance is exposed.",
        style_guide="Use restrained third-person prose and observable evidence.",
        characters=[
            CharacterPlan(
                name="Mara",
                role="protagonist",
                description="A methodical maritime archivist.",
                goals=["Recover the missing archive record"],
                personality=["careful", "persistent"],
                speech_style="Precise and economical.",
                initial_state="Investigating the sealed tide archive.",
            )
        ],
        locations=[
            LocationPlan(
                name="Tide Archive",
                description="A disused records building connected to tidal pumps.",
                rules=["The lower tunnel opens only during the evening tide."],
            )
        ],
        story_rules=[
            StoryRulePlan(
                category="archive",
                statement="Evidence must be logged before it is moved.",
            )
        ],
        chapter_plans=chapters,
    )


def build_m5_provider(scenario: str, target_chapters: int = 3) -> MockLLMProvider:
    """Build deterministic responses for pass, improve, and no-improvement paths."""
    plan = build_m5_plan(target_chapters)
    if scenario == "improve":
        plan.characters[0].initial_state = "dead"
    draft = ChapterDraft(
        title="The Tide Archive",
        content=_DRAFT_CONTENT,
        summary="Mara enters the archive and recovers a key linked to her missing mentor.",
        style_self_check=StyleSelfCheck(
            follows_outline=True,
            avoids_forbidden_reveals=True,
        ),
    )
    extraction = FactExtractionResult(
        facts=[
            ExtractedFact(
                subject="Mara",
                predicate="carries",
                object="brass key",
                fact_type="possession",
                confidence=0.99,
                source_quote="Mara lifted the brass key",
                valid_from_chapter=1,
            )
        ],
        character_updates=[
            CharacterStateUpdate(
                character_name="Mara",
                field="current_state",
                value="Recovered and logged the brass archive key.",
                confidence=0.98,
                source_quote="Mara lifted the brass key",
            )
        ],
    )
    provider = MockLLMProvider(
        {
            NovelPlan: plan,
            ChapterDraft: draft,
            FactExtractionResult: extraction,
        }
    )
    if scenario == "pass":
        critiques = [build_demo_critique("normal")]
        revised_content = _REVISED_CONTENT
    elif scenario == "improve":
        poor_critique = build_demo_critique("poor")
        normal_critique = build_demo_critique("normal")
        critiques = [poor_critique, normal_critique]
        revised_content = _REVISED_CONTENT
        conflicting_extraction = FactExtractionResult(
            facts=[
                ExtractedFact(
                    subject="Mara",
                    predicate="speaks",
                    object="warning",
                    fact_type="action",
                    confidence=0.99,
                    source_quote="Stay by the door",
                    valid_from_chapter=1,
                )
            ]
        )
        provider.register_responses(
            FactExtractionResult,
            [conflicting_extraction, extraction],
        )
        provider.register_response_selector(
            FactExtractionResult,
            lambda request: (
                extraction
                if _request_contains(request, "clear evidence sleeve")
                else conflicting_extraction
            ),
        )
        provider.register_response_selector(
            ChapterCritique,
            lambda request: (
                normal_critique
                if _request_contains(request, "clear evidence sleeve")
                else poor_critique
            ),
        )
    elif scenario == "stagnate":
        critiques = [build_demo_critique("poor")]
        revised_content = _DRAFT_CONTENT
    else:
        raise ValueError(f"Unknown M5 mock scenario: {scenario}")
    provider.register_responses(ChapterCritique, critiques)
    provider.register_response(
        RevisedChapterDraft,
        RevisedChapterDraft(
            title="The Tide Archive",
            content=revised_content,
            summary="Mara documents the archive key and preserves the investigation trail.",
            key_events=["Mara enters the tide archive", "Mara finds the brass key"],
            characters_present=["Mara", "Ivo"],
            locations_present=["Tide Archive"],
            changes_made=[
                "Applied the highest-priority revision brief while preserving the key evidence."
            ],
        ),
    )
    return provider


def m5_content_metrics() -> tuple[int, int]:
    """Expose deterministic content lengths for assertions without exposing prose in logs."""
    return len(_DRAFT_CONTENT), len(_REVISED_CONTENT)


def _request_contains(request: PromptRequest, marker: str) -> bool:
    return any(marker in message.content for message in request.messages)
