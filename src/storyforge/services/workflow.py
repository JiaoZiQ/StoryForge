"""Durable LangGraph orchestration for chapter generation and revision."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, cast
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import Session

from storyforge.database import SessionFactory
from storyforge.enums import (
    ChapterStatus,
    ConflictSeverity,
    WorkflowEventType,
    WorkflowRunStatus,
)
from storyforge.evaluation.models import ChapterEvaluationRequest
from storyforge.exceptions import (
    BudgetBlockedError,
    EntityNotFoundError,
    InvalidStateError,
    JobCancellationRequested,
    JobPauseRequested,
    WorkflowAlreadyRunningError,
    WorkflowExecutionError,
    WorkflowNotResumableError,
)
from storyforge.models import Evaluation, WorkflowEvent, WorkflowRun
from storyforge.repositories import (
    ChapterRepository,
    ChapterVersionRepository,
    EvaluationRepository,
    ProjectRepository,
    WorkflowEventRepository,
    WorkflowRunRepository,
)
from storyforge.revision import RevisionBrief, VersionComparisonResult
from storyforge.services.evaluation_service import EvaluationService
from storyforge.services.versioning import ChapterVersionService
from storyforge.workflows.models import ChapterWorkflowRequest, WorkflowStatusResult
from storyforge.workflows.state import ChapterWorkflowState
from storyforge.workflows.transitions import redact_error, transition_workflow

type NodeAction = Callable[[], dict[str, object]]

_TERMINAL = {
    WorkflowRunStatus.COMPLETED,
    WorkflowRunStatus.COMPLETED_NEEDS_REVIEW,
    WorkflowRunStatus.CANCELLED,
    WorkflowRunStatus.FAILED,
    WorkflowRunStatus.SUCCEEDED,
    WorkflowRunStatus.NEEDS_HUMAN_REVIEW,
}
_PAUSABLE_NODES = {
    "initialize_workflow",
    "load_context",
    "generate_draft",
    "extract_facts",
    "evaluate_draft",
    "decide_after_evaluation",
    "build_revision_brief",
    "revise_draft",
    "extract_revision_facts",
    "evaluate_revision",
    "compare_versions",
    "decide_after_comparison",
    "reject_revision",
}


class ChapterWorkflowService:
    """Run, resume, inspect, and cancel a persistent chapter workflow."""

    def __init__(
        self,
        session_factory: SessionFactory,
        version_service: ChapterVersionService,
        evaluation_service: EvaluationService,
        checkpoint_path: str | Path,
        control_callback: Callable[[str], None] | None = None,
        progress_callback: Callable[[str, str], None] | None = None,
        initialized_callback: Callable[[Session, int], None] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._versions = version_service
        self._evaluation = evaluation_service
        self._checkpoint_path = Path(checkpoint_path).expanduser().resolve()
        self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self._control_callback = control_callback
        self._progress_callback = progress_callback
        self._initialized_callback = initialized_callback

    def run(self, request: ChapterWorkflowRequest) -> WorkflowStatusResult:
        """Start and synchronously advance a new durable graph."""
        if request.pause_after is not None and request.pause_after not in _PAUSABLE_NODES:
            raise ValueError(f"Unsupported pause node: {request.pause_after}")
        thread_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        state: ChapterWorkflowState = {
            "thread_id": thread_id,
            "project_id": request.project_id,
            "chapter_number": request.chapter_number,
            "operation": request.operation,
            "status": WorkflowRunStatus.PENDING.value,
            "revision_attempt": 0,
            "max_revision_attempts": request.max_revision_attempts,
            "node_history": [],
            "errors": [],
            "blocking_reasons": [],
            "started_at": now,
            "updated_at": now,
        }
        try:
            self._invoke(state, thread_id=thread_id, pause_after=request.pause_after)
        except JobPauseRequested:
            self._mark_control_pause(thread_id)
        except JobCancellationRequested:
            self._mark_control_cancel(thread_id)
        except (EntityNotFoundError, InvalidStateError, ValueError):
            raise
        except BudgetBlockedError as exc:
            if not self._mark_budget_blocked_by_thread(thread_id, exc):
                self._mark_failed_by_thread(thread_id, exc)
                raise WorkflowExecutionError("Chapter workflow exceeded its budget safely") from exc
        except Exception as exc:
            self._mark_failed_by_thread(thread_id, exc)
            raise WorkflowExecutionError("Chapter workflow failed safely") from exc
        return self._status_by_thread(thread_id)

    def resume(self, workflow_run_id: int) -> WorkflowStatusResult:
        """Resume exactly after the last successful checkpointed node."""
        with self._session_factory.begin() as session:
            run = WorkflowRunRepository(session).get(workflow_run_id)
            if run is None:
                raise EntityNotFoundError(f"Workflow run {workflow_run_id} was not found")
            if run.status is not WorkflowRunStatus.PAUSED:
                raise WorkflowNotResumableError("Only paused workflows can be resumed")
            transition_workflow(run, WorkflowRunStatus.RUNNING)
            run.updated_at = datetime.now(UTC)
            thread_id = run.thread_id
        try:
            self._invoke(None, thread_id=thread_id, pause_after=None)
        except JobPauseRequested:
            self._mark_control_pause(thread_id)
        except JobCancellationRequested:
            self._mark_control_cancel(thread_id)
        except BudgetBlockedError as exc:
            if not self._mark_budget_blocked_by_thread(thread_id, exc):
                self._mark_failed_by_thread(thread_id, exc)
                raise WorkflowExecutionError("Chapter workflow exceeded its budget safely") from exc
        except Exception as exc:
            self._mark_failed_by_thread(thread_id, exc)
            raise WorkflowExecutionError("Chapter workflow resume failed safely") from exc
        return self.get_status(workflow_run_id)

    def get_status(self, workflow_run_id: int) -> WorkflowStatusResult:
        """Return a small status projection without exposing checkpoint internals."""
        with self._session_factory() as session:
            run = WorkflowRunRepository(session).get(workflow_run_id)
            if run is None:
                raise EntityNotFoundError(f"Workflow run {workflow_run_id} was not found")
            return self._to_status(session, run)

    def cancel(self, workflow_run_id: int) -> WorkflowStatusResult:
        """Cooperatively cancel a pending, running, or paused workflow at a node boundary."""
        with self._session_factory.begin() as session:
            run = WorkflowRunRepository(session).get(workflow_run_id)
            if run is None:
                raise EntityNotFoundError(f"Workflow run {workflow_run_id} was not found")
            transition_workflow(run, WorkflowRunStatus.CANCELLED)
            run.current_node = "cancelled"
            run.finished_at = datetime.now(UTC)
            run.updated_at = datetime.now(UTC)
            chapter = ChapterRepository(session).get(run.chapter_id)
            if chapter is not None:
                chapter.status = (
                    ChapterStatus.ACCEPTED
                    if chapter.accepted_version_id is not None
                    else ChapterStatus.WORKFLOW_FAILED
                )
        return self.get_status(workflow_run_id)

    def history(self, workflow_run_id: int) -> list[WorkflowEvent]:
        """Return ordered, content-free audit events for one run."""
        with self._session_factory() as session:
            if WorkflowRunRepository(session).get(workflow_run_id) is None:
                raise EntityNotFoundError(f"Workflow run {workflow_run_id} was not found")
            events = WorkflowEventRepository(session).list_for_run(workflow_run_id)
            session.expunge_all()
            return events

    def _invoke(
        self,
        state: ChapterWorkflowState | None,
        *,
        thread_id: str,
        pause_after: str | None,
    ) -> None:
        interrupt_after = [pause_after] if pause_after is not None else None
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        with SqliteSaver.from_conn_string(str(self._checkpoint_path)) as checkpointer:
            graph = self._build_graph().compile(
                checkpointer=checkpointer,
                interrupt_after=interrupt_after,
            )
            graph.invoke(state, config)
            snapshot = graph.get_state(config)
            if snapshot.next:
                values = cast(dict[str, object], snapshot.values)
                raw_run_id = values["workflow_run_id"]
                if not isinstance(raw_run_id, int):
                    raise InvalidStateError("Checkpoint is missing workflow_run_id")
                run_id = raw_run_id
                self._mark_paused(run_id, str(values.get("current_node", "unknown")))

    def _build_graph(self) -> StateGraph[ChapterWorkflowState, None, ChapterWorkflowState, Any]:
        graph = StateGraph(ChapterWorkflowState)
        graph.add_node("initialize_workflow", self._initialize_workflow)
        graph.add_node("load_context", self._load_context)
        graph.add_node("generate_draft", self._generate_draft)
        graph.add_node("extract_facts", self._extract_facts)
        graph.add_node("evaluate_draft", self._evaluate_draft)
        graph.add_node("decide_after_evaluation", self._decide_after_evaluation)
        graph.add_node("build_revision_brief", self._build_revision_brief)
        graph.add_node("revise_draft", self._revise_draft)
        graph.add_node("extract_revision_facts", self._extract_revision_facts)
        graph.add_node("evaluate_revision", self._evaluate_revision)
        graph.add_node("compare_versions", self._compare_versions)
        graph.add_node("decide_after_comparison", self._decide_after_comparison)
        graph.add_node("reject_revision", self._reject_revision)
        graph.add_node("accept_version", self._accept_version)
        graph.add_node("mark_needs_human_review", self._mark_needs_human_review)
        graph.add_node("fail_workflow", self._fail_workflow)
        graph.add_edge(START, "initialize_workflow")
        graph.add_edge("initialize_workflow", "load_context")
        graph.add_edge("load_context", "generate_draft")
        graph.add_edge("generate_draft", "extract_facts")
        graph.add_edge("extract_facts", "evaluate_draft")
        graph.add_edge("evaluate_draft", "decide_after_evaluation")
        graph.add_conditional_edges(
            "decide_after_evaluation",
            self._route,
            {
                "accept": "accept_version",
                "revise": "build_revision_brief",
                "human_review": "mark_needs_human_review",
                "fail": "fail_workflow",
            },
        )
        graph.add_edge("build_revision_brief", "revise_draft")
        graph.add_edge("revise_draft", "extract_revision_facts")
        graph.add_edge("extract_revision_facts", "evaluate_revision")
        graph.add_edge("evaluate_revision", "compare_versions")
        graph.add_edge("compare_versions", "decide_after_comparison")
        graph.add_conditional_edges(
            "decide_after_comparison",
            self._route,
            {
                "accept": "accept_version",
                "retry": "reject_revision",
                "human_review": "mark_needs_human_review",
                "fail": "fail_workflow",
            },
        )
        graph.add_edge("reject_revision", "build_revision_brief")
        graph.add_edge("accept_version", END)
        graph.add_edge("mark_needs_human_review", END)
        graph.add_edge("fail_workflow", END)
        return graph

    def _initialize_workflow(self, state: ChapterWorkflowState) -> dict[str, object]:
        thread_id = state["thread_id"]
        with self._session_factory.begin() as session:
            repository = WorkflowRunRepository(session)
            existing = repository.get_by_thread_id(thread_id)
            if existing is not None:
                if self._initialized_callback is not None:
                    self._initialized_callback(session, existing.id)
                chapter = ChapterRepository(session).get(existing.chapter_id)
                if chapter is None:
                    raise EntityNotFoundError("Workflow chapter was not found")
                return self._run_state(existing, chapter.chapter_number)
            project = ProjectRepository(session).get(state["project_id"])
            chapter = ChapterRepository(session).get_by_number(
                state["project_id"], state["chapter_number"]
            )
            if project is None or chapter is None:
                raise EntityNotFoundError("Project chapter was not found")
            active = session.scalar(
                select(WorkflowRun).where(
                    WorkflowRun.chapter_id == chapter.id,
                    WorkflowRun.status.in_(
                        (
                            WorkflowRunStatus.PENDING,
                            WorkflowRunStatus.RUNNING,
                            WorkflowRunStatus.PAUSED,
                        )
                    ),
                )
            )
            if active is not None:
                raise WorkflowAlreadyRunningError(
                    "Another workflow is already active for this chapter"
                )
            run = repository.add(
                WorkflowRun(
                    project_id=project.id,
                    chapter_id=chapter.id,
                    current_node="initialize_workflow",
                    status=WorkflowRunStatus.PENDING,
                    workflow_type="chapter_revision",
                    operation=state["operation"],
                    thread_id=thread_id,
                    original_version_id=chapter.current_version_id,
                    current_version_id=chapter.current_version_id,
                    best_version_id=chapter.current_version_id,
                    accepted_version_id=chapter.accepted_version_id,
                    revision_attempt=0,
                    max_revision_attempts=state["max_revision_attempts"],
                    node_history=["initialize_workflow"],
                    blocking_reasons=[],
                    retry_count=0,
                )
            )
            transition_workflow(run, WorkflowRunStatus.RUNNING)
            if self._initialized_callback is not None:
                self._initialized_callback(session, run.id)
            chapter.status = ChapterStatus.WORKFLOW_RUNNING
            self._event(
                session,
                run.id,
                "initialize_workflow",
                WorkflowEventType.NODE_STARTED,
                0,
                "running",
            )
            self._event(
                session,
                run.id,
                "initialize_workflow",
                WorkflowEventType.NODE_COMPLETED,
                0,
                "completed",
            )
            return self._run_state(run, chapter.chapter_number)

    def _load_context(self, state: ChapterWorkflowState) -> dict[str, object]:
        def action() -> dict[str, object]:
            self._versions.load_context(state["project_id"], state["chapter_number"])
            return {}

        return self._node(state, "load_context", action)

    def _generate_draft(self, state: ChapterWorkflowState) -> dict[str, object]:
        def action() -> dict[str, object]:
            context = self._versions.load_context(state["project_id"], state["chapter_number"])
            artifact = self._versions.ensure_initial_version(
                project_id=state["project_id"],
                chapter_number=state["chapter_number"],
                workflow_run_id=state["workflow_run_id"],
                context=context,
            )
            if artifact.created:
                self._record_aux_event(
                    state["workflow_run_id"],
                    "generate_draft",
                    WorkflowEventType.VERSION_CREATED,
                    state["revision_attempt"],
                    version_id=artifact.version_id,
                )
            return {
                "original_version_id": state.get("original_version_id") or artifact.version_id,
                "current_version_id": artifact.version_id,
                "best_version_id": state.get("best_version_id") or artifact.version_id,
            }

        return self._node(state, "generate_draft", action)

    def _extract_facts(self, state: ChapterWorkflowState) -> dict[str, object]:
        def action() -> dict[str, object]:
            self._versions.extract_candidate_facts(
                project_id=state["project_id"],
                chapter_number=state["chapter_number"],
                version_id=_required_id(state, "current_version_id"),
                workflow_run_id=state["workflow_run_id"],
            )
            return {}

        return self._node(state, "extract_facts", action)

    def _evaluate_draft(self, state: ChapterWorkflowState) -> dict[str, object]:
        return self._evaluate_node(state, "evaluate_draft")

    def _evaluate_revision(self, state: ChapterWorkflowState) -> dict[str, object]:
        return self._evaluate_node(state, "evaluate_revision")

    def _evaluate_node(self, state: ChapterWorkflowState, node: str) -> dict[str, object]:
        def action() -> dict[str, object]:
            attempt = state["revision_attempt"]
            version_id = _required_id(state, "current_version_id")
            result = self._evaluation.evaluate(
                ChapterEvaluationRequest(
                    project_id=state["project_id"],
                    chapter_number=state["chapter_number"],
                    chapter_version_id=version_id,
                    workflow_run_id=state["workflow_run_id"],
                    idempotency_key=f"workflow:{state['workflow_run_id']}:{node}:{attempt}",
                )
            )
            payload = self._evaluation_payload(result.evaluation_id)
            with self._session_factory.begin() as session:
                run = WorkflowRunRepository(session).get(state["workflow_run_id"])
                if run is not None:
                    run.current_version_id = version_id
                    run.blocking_reasons = list(result.blocking_reasons)
                    if run.best_version_id is None:
                        run.best_version_id = version_id
            self._record_aux_event(
                state["workflow_run_id"],
                node,
                WorkflowEventType.EVALUATION_CREATED,
                attempt,
                version_id=version_id,
                evaluation_id=result.evaluation_id,
            )
            return {
                "current_evaluation_id": result.evaluation_id,
                "current_evaluation": payload,
                "blocking_reasons": result.blocking_reasons,
            }

        return self._node(state, node, action)

    def _decide_after_evaluation(self, state: ChapterWorkflowState) -> dict[str, object]:
        def action() -> dict[str, object]:
            evaluation = state["current_evaluation"]
            recommendation = evaluation.get("recommended_action")
            critical_conflicts = evaluation.get("critical_conflicts", 0)
            if state.get("errors"):
                route = "fail"
            elif state["operation"] == "targeted_revision" and state["revision_attempt"] == 0:
                route = "revise"
            elif bool(evaluation.get("passed")) and not state.get("blocking_reasons"):
                route = "accept"
            elif recommendation == "reject":
                route = "human_review"
            elif recommendation == "human_review" and critical_conflicts == 0:
                route = "human_review"
            elif state["revision_attempt"] < state["max_revision_attempts"]:
                route = "revise"
            else:
                route = "human_review"
            self._record_route(state, "decide_after_evaluation", route)
            return {"route": route}

        return self._node(state, "decide_after_evaluation", action)

    def _build_revision_brief(self, state: ChapterWorkflowState) -> dict[str, object]:
        def action() -> dict[str, object]:
            source_version_id = state.get("best_version_id") or state.get("current_version_id")
            if source_version_id is None:
                raise InvalidStateError("No source version is available for revision")
            evaluation_id = self._latest_evaluation_id(source_version_id)
            previous_improved = None
            if state.get("comparison"):
                raw_delta = state["comparison"].get("overall_delta", 0)
                previous_improved = isinstance(raw_delta, int | float) and raw_delta > 0
            brief = self._versions.build_revision_brief(
                workflow_run_id=state["workflow_run_id"],
                source_version_id=source_version_id,
                evaluation_id=evaluation_id,
                revision_attempt=state["revision_attempt"] + 1,
                previous_improved=previous_improved,
                include_source_version_facts=state["operation"] != "targeted_revision",
            )
            return {
                "current_version_id": source_version_id,
                "current_evaluation_id": evaluation_id,
                "revision_brief": brief.model_dump(mode="json"),
            }

        return self._node(state, "build_revision_brief", action)

    def _revise_draft(self, state: ChapterWorkflowState) -> dict[str, object]:
        def action() -> dict[str, object]:
            brief = RevisionBrief.model_validate(state["revision_brief"])
            source_version_id = _required_id(state, "current_version_id")
            context = self._versions.load_context(state["project_id"], state["chapter_number"])
            artifact = self._versions.revise(
                workflow_run_id=state["workflow_run_id"],
                source_version_id=source_version_id,
                brief=brief,
                context=context,
            )
            if artifact.created:
                self._record_aux_event(
                    state["workflow_run_id"],
                    "revise_draft",
                    WorkflowEventType.VERSION_CREATED,
                    brief.revision_attempt,
                    version_id=artifact.version_id,
                )
            return {
                "comparison_base_version_id": source_version_id,
                "current_version_id": artifact.version_id,
                "revision_attempt": brief.revision_attempt,
            }

        return self._node(state, "revise_draft", action)

    def _extract_revision_facts(self, state: ChapterWorkflowState) -> dict[str, object]:
        def action() -> dict[str, object]:
            self._versions.extract_candidate_facts(
                project_id=state["project_id"],
                chapter_number=state["chapter_number"],
                version_id=_required_id(state, "current_version_id"),
                workflow_run_id=state["workflow_run_id"],
            )
            return {}

        return self._node(state, "extract_revision_facts", action)

    def _compare_versions(self, state: ChapterWorkflowState) -> dict[str, object]:
        def action() -> dict[str, object]:
            result = self._versions.compare_versions(
                workflow_run_id=state["workflow_run_id"],
                old_version_id=_required_id(state, "comparison_base_version_id"),
                new_version_id=_required_id(state, "current_version_id"),
                revision_attempt=state["revision_attempt"],
                max_revision_attempts=state["max_revision_attempts"],
            )
            with self._session_factory() as session:
                run = WorkflowRunRepository(session).get(state["workflow_run_id"])
                best_id = run.best_version_id if run is not None else state.get("best_version_id")
            return {
                "comparison": result.model_dump(mode="json"),
                "best_version_id": best_id,
            }

        return self._node(state, "compare_versions", action)

    def _decide_after_comparison(self, state: ChapterWorkflowState) -> dict[str, object]:
        def action() -> dict[str, object]:
            result = VersionComparisonResult.model_validate(state["comparison"])
            if state.get("errors"):
                route = "fail"
            elif result.decision == "accept_new":
                route = "accept"
            elif result.decision in {"human_review", "keep_old_stop"}:
                route = "human_review"
            elif state["revision_attempt"] >= state["max_revision_attempts"]:
                route = "human_review"
            else:
                route = "retry"
            self._record_route(state, "decide_after_comparison", route)
            return {"route": route}

        return self._node(state, "decide_after_comparison", action)

    def _reject_revision(self, state: ChapterWorkflowState) -> dict[str, object]:
        def action() -> dict[str, object]:
            current_id = _required_id(state, "current_version_id")
            best_id = _required_id(state, "best_version_id")
            if current_id != best_id:
                best_id = self._versions.reject_revision(state["workflow_run_id"], current_id)
                self._record_aux_event(
                    state["workflow_run_id"],
                    "reject_revision",
                    WorkflowEventType.REVISION_REJECTED,
                    state["revision_attempt"],
                    version_id=current_id,
                )
            return {
                "current_version_id": best_id,
                "current_evaluation_id": self._latest_evaluation_id(best_id),
            }

        return self._node(state, "reject_revision", action)

    def _accept_version(self, state: ChapterWorkflowState) -> dict[str, object]:
        def action() -> dict[str, object]:
            version_id = _required_id(state, "current_version_id")
            self._versions.accept_version(state["workflow_run_id"], version_id)
            self._record_aux_event(
                state["workflow_run_id"],
                "accept_version",
                WorkflowEventType.VERSION_ACCEPTED,
                state["revision_attempt"],
                version_id=version_id,
                evaluation_id=state.get("current_evaluation_id"),
            )
            self._record_aux_event(
                state["workflow_run_id"],
                "accept_version",
                WorkflowEventType.WORKFLOW_COMPLETED,
                state["revision_attempt"],
                version_id=version_id,
                evaluation_id=state.get("current_evaluation_id"),
            )
            return {
                "accepted_version_id": version_id,
                "best_version_id": version_id,
                "status": WorkflowRunStatus.COMPLETED.value,
            }

        return self._node(state, "accept_version", action, terminal=True)

    def _mark_needs_human_review(self, state: ChapterWorkflowState) -> dict[str, object]:
        def action() -> dict[str, object]:
            best_id = self._versions.mark_needs_review(state["workflow_run_id"])
            self._record_aux_event(
                state["workflow_run_id"],
                "mark_needs_human_review",
                WorkflowEventType.WORKFLOW_COMPLETED,
                state["revision_attempt"],
                version_id=best_id,
            )
            return {
                "current_version_id": best_id,
                "best_version_id": best_id,
                "status": WorkflowRunStatus.COMPLETED_NEEDS_REVIEW.value,
            }

        return self._node(state, "mark_needs_human_review", action, terminal=True)

    def _fail_workflow(self, state: ChapterWorkflowState) -> dict[str, object]:
        error = WorkflowExecutionError("Workflow state selected the failure route")
        self._mark_failed_by_thread(state["thread_id"], error)
        return self._state_update(
            state, "fail_workflow", {"status": WorkflowRunStatus.FAILED.value}
        )

    @staticmethod
    def _route(state: ChapterWorkflowState) -> str:
        return state["route"]

    def _node(
        self,
        state: ChapterWorkflowState,
        node: str,
        action: NodeAction,
        *,
        terminal: bool = False,
    ) -> dict[str, object]:
        started = perf_counter()
        self._node_started(state, node)
        try:
            changes = action()
        except Exception as exc:
            self._node_failed(state, node, exc, started)
            raise
        completed_state = cast(ChapterWorkflowState, {**state, **changes})
        self._node_completed(completed_state, node, started, terminal=terminal)
        return self._state_update(state, node, changes)

    def _node_started(self, state: ChapterWorkflowState, node: str) -> None:
        if self._control_callback is not None:
            self._control_callback(node)
        with self._session_factory.begin() as session:
            run = WorkflowRunRepository(session).get(state["workflow_run_id"])
            if run is None:
                raise EntityNotFoundError("Workflow run was not found")
            if run.status is WorkflowRunStatus.CANCELLED:
                raise InvalidStateError("Cancelled workflow cannot enter another node")
            run.current_node = node
            run.updated_at = datetime.now(UTC)
            history = list(run.node_history)
            if not history or history[-1] != node:
                history.append(node)
                run.node_history = history
            self._event(
                session,
                run.id,
                node,
                WorkflowEventType.NODE_STARTED,
                state["revision_attempt"],
                "running",
            )
        if self._progress_callback is not None:
            self._progress_callback("started", node)

    def _node_completed(
        self,
        state: ChapterWorkflowState,
        node: str,
        started: float,
        *,
        terminal: bool,
    ) -> None:
        with self._session_factory.begin() as session:
            run = WorkflowRunRepository(session).get(state["workflow_run_id"])
            if run is None:
                raise EntityNotFoundError("Workflow run was not found")
            duration = max(0, round((perf_counter() - started) * 1000))
            self._event(
                session,
                run.id,
                node,
                WorkflowEventType.NODE_COMPLETED,
                state["revision_attempt"],
                "completed",
                duration_ms=duration,
                version_id=state.get("current_version_id"),
                evaluation_id=state.get("current_evaluation_id"),
            )
            if not terminal:
                run.updated_at = datetime.now(UTC)
        if self._progress_callback is not None:
            self._progress_callback("completed", node)

    def _mark_control_pause(self, thread_id: str) -> None:
        with self._session_factory() as session:
            run = WorkflowRunRepository(session).get_by_thread_id(thread_id)
            if run is None:
                raise WorkflowExecutionError("Workflow pause checkpoint was not found")
            run_id = run.id
            node = run.current_node
        self._mark_paused(run_id, node)

    def _mark_control_cancel(self, thread_id: str) -> None:
        with self._session_factory() as session:
            run = WorkflowRunRepository(session).get_by_thread_id(thread_id)
            if run is None:
                raise WorkflowExecutionError("Workflow cancellation target was not found")
            run_id = run.id
        self.cancel(run_id)

    def _node_failed(
        self, state: ChapterWorkflowState, node: str, error: Exception, started: float
    ) -> None:
        with self._session_factory.begin() as session:
            run = WorkflowRunRepository(session).get(state["workflow_run_id"])
            if run is None:
                return
            self._event(
                session,
                run.id,
                node,
                WorkflowEventType.NODE_FAILED,
                state["revision_attempt"],
                "failed",
                duration_ms=max(0, round((perf_counter() - started) * 1000)),
                error_code=type(error).__name__,
            )

    def _record_route(self, state: ChapterWorkflowState, node: str, route: str) -> None:
        self._record_aux_event(
            state["workflow_run_id"],
            node,
            WorkflowEventType.ROUTE_SELECTED,
            state["revision_attempt"],
            status=route,
        )

    def _record_aux_event(
        self,
        workflow_run_id: int,
        node: str,
        event_type: WorkflowEventType,
        attempt: int,
        *,
        status: str = "completed",
        version_id: int | None = None,
        evaluation_id: int | None = None,
    ) -> None:
        with self._session_factory.begin() as session:
            self._event(
                session,
                workflow_run_id,
                node,
                event_type,
                attempt,
                status,
                version_id=version_id,
                evaluation_id=evaluation_id,
            )

    @staticmethod
    def _event(
        session: Any,
        workflow_run_id: int,
        node: str,
        event_type: WorkflowEventType,
        attempt: int,
        status: str,
        *,
        duration_ms: int = 0,
        version_id: int | None = None,
        evaluation_id: int | None = None,
        error_code: str | None = None,
    ) -> None:
        existing = session.scalar(
            select(WorkflowEvent).where(
                WorkflowEvent.workflow_run_id == workflow_run_id,
                WorkflowEvent.node == node,
                WorkflowEvent.event_type == event_type,
                WorkflowEvent.attempt == attempt,
            )
        )
        if existing is not None:
            return
        WorkflowEventRepository(session).add(
            WorkflowEvent(
                workflow_run_id=workflow_run_id,
                node=node,
                event_type=event_type,
                attempt=attempt,
                status=status,
                duration_ms=duration_ms,
                version_id=version_id,
                evaluation_id=evaluation_id,
                error_code=error_code,
            )
        )

    def _evaluation_payload(self, evaluation_id: int) -> dict[str, object]:
        with self._session_factory() as session:
            evaluation = EvaluationRepository(session).get(evaluation_id)
            if evaluation is None:
                raise EntityNotFoundError("Workflow evaluation was not found")
            return {
                "evaluation_id": evaluation.id,
                "version_id": evaluation.chapter_version_id,
                "final_score": evaluation.overall_score,
                "consistency_score": evaluation.consistency_score,
                "outline_adherence_score": evaluation.outline_adherence_score,
                "critical_conflicts": sum(
                    item.severity is ConflictSeverity.CRITICAL for item in evaluation.conflicts
                ),
                "high_conflicts": sum(
                    item.severity is ConflictSeverity.HIGH for item in evaluation.conflicts
                ),
                "passed": evaluation.passed,
                "recommended_action": evaluation.recommended_action,
                "blocking_reasons": list(evaluation.blocking_reasons),
            }

    def _latest_evaluation_id(self, version_id: int) -> int:
        with self._session_factory() as session:
            evaluation = EvaluationRepository(session).latest_for_version(version_id)
            if evaluation is None:
                raise InvalidStateError("Version has not been evaluated")
            return evaluation.id

    def _mark_paused(self, workflow_run_id: int, node: str) -> None:
        with self._session_factory.begin() as session:
            run = WorkflowRunRepository(session).get(workflow_run_id)
            if run is None:
                raise EntityNotFoundError("Workflow run was not found")
            if run.status in _TERMINAL:
                return
            transition_workflow(run, WorkflowRunStatus.PAUSED)
            run.current_node = node
            run.updated_at = datetime.now(UTC)

    def _mark_failed_by_thread(self, thread_id: str, error: Exception) -> None:
        with self._session_factory.begin() as session:
            run = WorkflowRunRepository(session).get_by_thread_id(thread_id)
            if run is None or run.status in _TERMINAL:
                return
            transition_workflow(run, WorkflowRunStatus.FAILED)
            run.error_code = type(error).__name__
            run.error_message = redact_error(error)
            run.finished_at = datetime.now(UTC)
            run.updated_at = datetime.now(UTC)
            chapter = ChapterRepository(session).get(run.chapter_id)
            if chapter is not None:
                chapter.status = (
                    ChapterStatus.ACCEPTED
                    if chapter.accepted_version_id is not None
                    else ChapterStatus.WORKFLOW_FAILED
                )

    def _mark_budget_blocked_by_thread(self, thread_id: str, error: BudgetBlockedError) -> bool:
        """Preserve the best version and stop safely when a hard budget is reached."""
        with self._session_factory() as session:
            run = WorkflowRunRepository(session).get_by_thread_id(thread_id)
            if run is None or run.status in _TERMINAL or run.best_version_id is None:
                return False
            workflow_run_id = run.id
            revision_attempt = run.revision_attempt
            best_version_id = run.best_version_id
        self._versions.mark_needs_review(workflow_run_id)
        with self._session_factory.begin() as session:
            run = WorkflowRunRepository(session).get(workflow_run_id)
            if run is None:
                raise EntityNotFoundError("Workflow run was not found")
            reasons = list(run.blocking_reasons)
            if "budget_blocked" not in reasons:
                reasons.append("budget_blocked")
            run.blocking_reasons = reasons
            run.error_code = type(error).__name__
            run.error_message = redact_error(error)
        self._record_aux_event(
            workflow_run_id,
            "mark_needs_human_review",
            WorkflowEventType.WORKFLOW_COMPLETED,
            revision_attempt,
            version_id=best_version_id,
        )
        return True

    def _status_by_thread(self, thread_id: str) -> WorkflowStatusResult:
        with self._session_factory() as session:
            run = WorkflowRunRepository(session).get_by_thread_id(thread_id)
            if run is None:
                raise EntityNotFoundError("Workflow run was not created")
            return self._to_status(session, run)

    @staticmethod
    def _to_status(session: Any, run: WorkflowRun) -> WorkflowStatusResult:
        chapter = ChapterRepository(session).get(run.chapter_id)
        if chapter is None:
            raise EntityNotFoundError("Workflow chapter was not found")

        def number(version_id: int | None) -> int | None:
            if version_id is None:
                return None
            version = ChapterVersionRepository(session).get(version_id)
            return version.version if version is not None else None

        latest_score = session.scalar(
            select(Evaluation.overall_score)
            .where(Evaluation.workflow_run_id == run.id)
            .order_by(Evaluation.id.desc())
            .limit(1)
        )
        return WorkflowStatusResult(
            workflow_run_id=run.id,
            thread_id=run.thread_id,
            project_id=run.project_id,
            chapter_id=run.chapter_id,
            chapter_number=chapter.chapter_number,
            current_node=run.current_node,
            status=run.status,
            original_version_id=run.original_version_id,
            current_version_id=run.current_version_id,
            best_version_id=run.best_version_id,
            accepted_version_id=run.accepted_version_id,
            original_version=number(run.original_version_id),
            current_version=number(run.current_version_id),
            best_version=number(run.best_version_id),
            accepted_version=number(run.accepted_version_id),
            revision_attempt=run.revision_attempt,
            max_revision_attempts=run.max_revision_attempts,
            latest_score=latest_score,
            blocking_reasons=list(run.blocking_reasons),
            node_history=list(run.node_history),
            error_code=run.error_code,
            error_message=run.error_message,
            started_at=run.started_at,
            updated_at=run.updated_at,
            finished_at=run.finished_at,
        )

    @staticmethod
    def _run_state(run: WorkflowRun, chapter_number: int) -> dict[str, object]:
        return {
            "workflow_run_id": run.id,
            "chapter_id": run.chapter_id,
            "chapter_number": chapter_number,
            "current_node": run.current_node,
            "status": run.status.value,
            "original_version_id": run.original_version_id,
            "current_version_id": run.current_version_id,
            "best_version_id": run.best_version_id,
            "accepted_version_id": run.accepted_version_id,
            "revision_attempt": run.revision_attempt,
            "max_revision_attempts": run.max_revision_attempts,
            "node_history": list(run.node_history),
            "blocking_reasons": list(run.blocking_reasons),
            "updated_at": run.updated_at.isoformat(),
        }

    @staticmethod
    def _state_update(
        state: ChapterWorkflowState, node: str, changes: dict[str, object]
    ) -> dict[str, object]:
        history = list(state.get("node_history", []))
        if not history or history[-1] != node:
            history.append(node)
        return {
            **changes,
            "current_node": node,
            "node_history": history,
            "updated_at": datetime.now(UTC).isoformat(),
        }


def _required_id(state: ChapterWorkflowState, key: str) -> int:
    value = state.get(key)
    if not isinstance(value, int):
        raise InvalidStateError(f"Workflow state is missing {key}")
    return value
