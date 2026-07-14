"""Milestone 6 offline demonstration composed only from public application services."""

from __future__ import annotations

from storyforge.database import SessionFactory
from storyforge.enums import FactStatus, WorkflowRunStatus
from storyforge.exceptions import InvalidStateError
from storyforge.repositories import DemoAuditRepository
from storyforge.schemas.api import (
    DemoEvaluationSummary,
    DemoM6Response,
    GeneratePlanRequest,
    ProjectCreateRequest,
    StartWorkflowRequest,
)
from storyforge.settings import Settings

from .chapters import ChapterApplicationService
from .evaluations import EvaluationApplicationService
from .factory import DomainServiceFactory
from .planning import PlanningApplicationService
from .projects import ProjectApplicationService
from .workflows import WorkflowApplicationService


class DemoApplicationService:
    """Run and verify the full offline M6 application boundary."""

    def __init__(self, session_factory: SessionFactory, settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._factory = DomainServiceFactory(session_factory, settings)
        self._projects = ProjectApplicationService(session_factory)
        self._planning = PlanningApplicationService(session_factory, self._factory)
        self._chapters = ChapterApplicationService(session_factory, self._factory, settings)
        self._evaluations = EvaluationApplicationService(session_factory, self._factory)
        self._workflows = WorkflowApplicationService(session_factory, self._factory, settings)

    def run(self) -> DemoM6Response:
        project = self._projects.create(
            ProjectCreateRequest(
                title="Milestone 6 offline interface",
                genre="mystery",
                premise="An archivist investigates a sealed tidal records network.",
                target_chapters=3,
                target_words_per_chapter=300,
                language="en",
                tone="restrained",
                audience="adult",
                additional_requirements="Keep evidence auditable.",
            )
        )
        plan = self._planning.generate(project.id, GeneratePlanRequest())
        workflow = self._workflows.start(
            project.id,
            1,
            StartWorkflowRequest(max_revision_attempts=2),
        )
        if workflow.status is not WorkflowRunStatus.COMPLETED:
            raise InvalidStateError("demo-m6 revision scenario did not complete successfully")
        if workflow.revision_attempt < 1 or workflow.accepted_version is None:
            raise InvalidStateError("demo-m6 did not preserve and accept a revised version")

        project_summary = self._projects.list(page=1, page_size=20).items[0]
        chapters = self._chapters.list_chapters(project.id, page=1, page_size=20)
        if len(chapters.items) != 3:
            raise InvalidStateError("demo-m6 chapter listing is incomplete")
        chapter = self._chapters.get(project.id, 1)
        versions = self._chapters.list_versions(project.id, 1, page=1, page_size=20)
        if len(versions.items) < 2:
            raise InvalidStateError("demo-m6 revision history is incomplete")
        self._chapters.diff(
            project.id,
            1,
            versions.items[0].id,
            old_version_id=versions.items[1].id,
        )
        evaluations = self._evaluations.list_evaluations(project.id, 1, page=1, page_size=20)
        latest = self._evaluations.get_evaluation(project.id, 1, evaluations.items[0].id)
        conflicts = self._evaluations.list_conflicts(project.id, page=1, page_size=100)
        accepted_facts = self._evaluations.list_facts(project.id, page=1, page_size=100)
        future_facts = self._evaluations.list_facts(
            project.id,
            page=1,
            page_size=100,
            valid_at_chapter=1,
        )
        events = self._workflows.list_events(workflow.workflow_run_id, page=1, page_size=100)
        with self._session_factory() as session:
            audit = DemoAuditRepository(session)
            duplicate_versions = audit.duplicate_version_count(project.id)
            duplicate_evaluations = audit.duplicate_evaluation_count(project.id)
            duplicate_conflicts = audit.duplicate_conflict_count(project.id)
            duplicate_facts = audit.duplicate_fact_count(project.id)
        if any((duplicate_versions, duplicate_evaluations, duplicate_conflicts, duplicate_facts)):
            raise InvalidStateError("demo-m6 detected duplicate durable side effects")
        if any(item.status is not FactStatus.ACCEPTED for item in accepted_facts.items):
            raise InvalidStateError("demo-m6 public fact query exposed candidate memory")
        if future_facts.items:
            raise InvalidStateError("demo-m6 future-safe fact query leaked current/future facts")

        return DemoM6Response(
            project=project_summary,
            plan_characters=len(plan.characters),
            plan_locations=len(plan.locations),
            plan_chapters=len(plan.chapter_plans),
            plan_foreshadowing=len(plan.foreshadowing),
            chapter=chapter,
            versions=len(versions.items),
            accepted_version=workflow.accepted_version,
            final_score=latest.final_score,
            evaluation=DemoEvaluationSummary(
                id=latest.id,
                evaluation_version=latest.evaluation_version,
                chapter_version_id=latest.chapter_version_id,
                status=latest.status,
                mechanical_score=latest.mechanical_score,
                critic_score=latest.critic_score,
                consistency_score=latest.consistency_score,
                final_score=latest.final_score,
                passed=latest.passed,
                recommended_action=latest.recommended_action,
                created_at=latest.created_at,
                issue_count=len(latest.issues),
                conflict_count=len(conflicts.items),
            ),
            workflow=workflow,
            workflow_events=len(events.items),
            accepted_facts=len(accepted_facts.items),
            candidate_facts_visible=0,
            future_facts_visible=len(future_facts.items),
            duplicate_versions=duplicate_versions,
            duplicate_evaluations=duplicate_evaluations,
            duplicate_conflicts=duplicate_conflicts,
            duplicate_facts=duplicate_facts,
        )
