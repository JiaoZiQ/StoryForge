"""Planner agent implementation."""

from storyforge.agents.base import AgentResult, StructuredAgent
from storyforge.exceptions import PlanningValidationError
from storyforge.schemas.planning import NovelPlan, PlanningRequest, validate_plan_for_request


class PlannerAgent(StructuredAgent):
    """Transform one persisted project brief into a validated novel plan."""

    prompt_name = "planner"

    def plan(self, request: PlanningRequest) -> AgentResult[NovelPlan]:
        """Generate and validate a complete plan for the requested project."""
        result = self._invoke(request, NovelPlan)
        try:
            validate_plan_for_request(result.output, request)
        except ValueError as exc:
            raise PlanningValidationError(str(exc)) from exc
        return result
