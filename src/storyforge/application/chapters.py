"""Chapter, context, generation, version, and deterministic diff use cases."""

from __future__ import annotations

from difflib import unified_diff

from sqlalchemy.orm import Session

from storyforge.database import SessionFactory
from storyforge.enums import ChapterStatus
from storyforge.exceptions import DomainValidationError, EntityNotFoundError, InvalidStateError
from storyforge.models import Chapter, ChapterVersion
from storyforge.repositories import (
    ChapterRepository,
    ChapterVersionRepository,
    EvaluationRepository,
    ProjectRepository,
    RevisionRepository,
    WorkflowRunRepository,
)
from storyforge.schemas.api import (
    ChapterDetail,
    ChapterGenerationResponse,
    ChapterSummary,
    ContextSummary,
    GenerateChapterRequest,
    PageResponse,
    VersionDetail,
    VersionDiffResponse,
    VersionPointer,
    VersionSummary,
)
from storyforge.schemas.context import ContextBuildRequest
from storyforge.schemas.generation import ChapterGenerationRequest
from storyforge.services import ContextBuilder
from storyforge.settings import Settings

from .common import page_response
from .factory import DomainServiceFactory


class ChapterApplicationService:
    """Expose chapter operations through small response projections."""

    def __init__(
        self,
        session_factory: SessionFactory,
        factory: DomainServiceFactory,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._factory = factory
        self._settings = settings

    def list_chapters(
        self,
        project_id: int,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        has_content: bool | None = None,
        passed: bool | None = None,
        min_score: float | None = None,
        max_score: float | None = None,
        sort: str = "chapter_number",
        order: str = "asc",
    ) -> PageResponse[ChapterSummary]:
        with self._session_factory() as session:
            self._require_project(session, project_id)
            result = ChapterRepository(session).page_for_project(
                project_id,
                page=page,
                page_size=page_size,
                status=status,
                has_content=has_content,
                passed=passed,
                min_score=min_score,
                max_score=max_score,
                sort=sort,
                order=order,
            )
            items = [_chapter_summary(item) for item in result.items]
        return page_response(result, page=page, page_size=page_size, items=items)

    def get(
        self, project_id: int, chapter_number: int, *, include_content: bool = False
    ) -> ChapterDetail:
        with self._session_factory() as session:
            chapter = self._require_chapter(session, project_id, chapter_number)
            versions = ChapterVersionRepository(session)
            current = (
                versions.get(chapter.current_version_id) if chapter.current_version_id else None
            )
            accepted = (
                versions.get(chapter.accepted_version_id) if chapter.accepted_version_id else None
            )
            latest_run = WorkflowRunRepository(session).latest_for_chapter(chapter.id)
            best = (
                versions.get(latest_run.best_version_id)
                if latest_run is not None and latest_run.best_version_id is not None
                else accepted or current
            )
            content = chapter.content if include_content else None
            self._validate_content_size(content)
            return ChapterDetail(
                **_chapter_summary(chapter).model_dump(),
                outline=chapter.outline,
                outline_metadata=dict(chapter.outline_metadata),
                summary=chapter.summary,
                current_version=_pointer(current),
                accepted_version=_pointer(accepted),
                best_version=_pointer(best),
                version_count=ChapterRepository(session).count_versions(chapter.id),
                conflict_count=ChapterRepository(session).count_conflicts(chapter.id),
                workflow_status=latest_run.status if latest_run is not None else None,
                content=content,
            )

    def context(
        self, project_id: int, chapter_number: int, *, max_context_chars: int = 24_000
    ) -> ContextSummary:
        context = ContextBuilder(self._session_factory).build(
            ContextBuildRequest(
                project_id=project_id,
                chapter_number=chapter_number,
                max_context_chars=max_context_chars,
            )
        )
        if context.author_secrets:
            raise InvalidStateError("Public context unexpectedly contained author-only secrets")
        return ContextSummary(
            project_id=project_id,
            chapter_number=chapter_number,
            characters=[item.name for item in context.characters],
            locations=[item.name for item in context.locations],
            known_fact_count=len(context.known_facts),
            active_foreshadowing=[item.description for item in context.active_foreshadowing],
            previous_summary_count=len(context.recent_chapters),
            metadata=context.budget.model_dump(mode="json"),
            truncated_categories=list(context.budget.omitted_categories),
        )

    def generate(
        self, project_id: int, chapter_number: int, request: GenerateChapterRequest
    ) -> ChapterGenerationResponse:
        with self._factory.provider(
            "generation",
            project_id=project_id,
            chapter_number=chapter_number,
            override=request.provider,
        ) as provider:
            result = self._factory.generation_service(provider).generate(
                ChapterGenerationRequest(
                    project_id=project_id,
                    chapter_number=chapter_number,
                    regenerate=request.regenerate,
                    max_context_chars=request.max_context_chars,
                )
            )
        return ChapterGenerationResponse(
            project_id=result.project_id,
            chapter_id=result.chapter_id,
            chapter_number=result.chapter_number,
            version=result.version,
            status=ChapterStatus(result.status),
            title=result.title,
            summary=result.summary,
            fact_count=result.fact_count,
            character_update_count=result.character_update_count,
            foreshadowing_update_count=result.foreshadowing_update_count,
        )

    def list_versions(
        self, project_id: int, chapter_number: int, *, page: int, page_size: int
    ) -> PageResponse[VersionSummary]:
        with self._session_factory() as session:
            chapter = self._require_chapter(session, project_id, chapter_number)
            result = ChapterVersionRepository(session).page_for_chapter(
                chapter.id, page=page, page_size=page_size
            )
            evaluations = EvaluationRepository(session)
            items = [
                _version_summary(item, evaluations.latest_for_version(item.id))
                for item in result.items
            ]
        return page_response(result, page=page, page_size=page_size, items=items)

    def get_version(
        self,
        project_id: int,
        chapter_number: int,
        version_id: int,
        *,
        include_content: bool = False,
    ) -> VersionDetail:
        with self._session_factory() as session:
            chapter = self._require_chapter(session, project_id, chapter_number)
            version = ChapterVersionRepository(session).get_for_chapter(chapter.id, version_id)
            if version is None:
                raise EntityNotFoundError(f"Chapter version {version_id} was not found")
            evaluation = EvaluationRepository(session).latest_for_version(version.id)
            revision = RevisionRepository(session).get_for_new_version(version.id)
            content = version.content if include_content else None
            self._validate_content_size(content)
            return VersionDetail(
                **_version_summary(version, evaluation).model_dump(),
                title=version.title,
                summary=version.summary,
                prompt_versions=dict(version.prompt_versions),
                changes_made=_changes_made(revision.brief if revision is not None else {}),
                content=content,
            )

    def diff(
        self,
        project_id: int,
        chapter_number: int,
        version_id: int,
        *,
        old_version_id: int | None = None,
        include_unified_diff: bool = False,
    ) -> VersionDiffResponse:
        with self._session_factory() as session:
            chapter = self._require_chapter(session, project_id, chapter_number)
            repository = ChapterVersionRepository(session)
            new = repository.get_for_chapter(chapter.id, version_id)
            if new is None:
                raise EntityNotFoundError(f"Chapter version {version_id} was not found")
            inferred_old_id = old_version_id or new.parent_version_id
            if inferred_old_id is None:
                prior = [
                    item
                    for item in repository.list_for_chapter(chapter.id)
                    if item.version < new.version
                ]
                old = prior[-1] if prior else None
            else:
                old = repository.get_for_chapter(chapter.id, inferred_old_id)
            if old is None:
                raise DomainValidationError("No comparable earlier version exists")
            revision = RevisionRepository(session).get_for_new_version(new.id)
            changes = _changes_made(revision.brief if revision is not None else {})
        return self._build_diff(old, new, changes, include_unified_diff)

    def _build_diff(
        self,
        old: ChapterVersion,
        new: ChapterVersion,
        changes_made: list[str],
        include_unified_diff: bool,
    ) -> VersionDiffResponse:
        old_lines = old.content.splitlines()
        new_lines = new.content.splitlines()
        diff_lines = list(
            unified_diff(
                old_lines,
                new_lines,
                fromfile=f"version-{old.version}",
                tofile=f"version-{new.version}",
                lineterm="",
            )
        )
        additions = sum(line.startswith("+") and not line.startswith("+++") for line in diff_lines)
        deletions = sum(line.startswith("-") and not line.startswith("---") for line in diff_lines)
        rendered = "\n".join(diff_lines) if include_unified_diff else None
        truncated = rendered is not None and len(rendered) > self._settings.max_diff_chars
        if rendered is not None and truncated:
            rendered = rendered[: self._settings.max_diff_chars]
        return VersionDiffResponse(
            old_version_id=old.id,
            new_version_id=new.id,
            additions=additions,
            deletions=deletions,
            changed_line_count=additions + deletions,
            word_count_delta=new.word_count - old.word_count,
            changes_made=changes_made,
            unified_diff=rendered,
            truncated=truncated,
        )

    def _validate_content_size(self, content: str | None) -> None:
        if content is not None and len(content) > self._settings.max_chapter_content_chars:
            raise DomainValidationError("Chapter content exceeds the configured response limit")

    @staticmethod
    def _require_project(session: Session, project_id: int) -> None:
        if ProjectRepository(session).get(project_id) is None:
            raise EntityNotFoundError(f"Project {project_id} was not found")

    @staticmethod
    def _require_chapter(session: Session, project_id: int, chapter_number: int) -> Chapter:
        chapter = ChapterRepository(session).get_by_number(project_id, chapter_number)
        if chapter is None:
            raise EntityNotFoundError(
                f"Chapter {chapter_number} was not found for project {project_id}"
            )
        return chapter


def _chapter_summary(chapter: Chapter) -> ChapterSummary:
    return ChapterSummary(
        id=chapter.id,
        project_id=chapter.project_id,
        chapter_number=chapter.chapter_number,
        title=chapter.title,
        objective=chapter.objective,
        status=chapter.status,
        score=chapter.score,
        has_content=bool(chapter.content.strip()),
        current_version_id=chapter.current_version_id,
        accepted_version_id=chapter.accepted_version_id,
        updated_at=chapter.updated_at,
    )


def _pointer(version: ChapterVersion | None) -> VersionPointer | None:
    if version is None:
        return None
    return VersionPointer(id=version.id, version=version.version, status=version.status)


def _version_summary(version: ChapterVersion, evaluation: object | None) -> VersionSummary:
    score = getattr(evaluation, "overall_score", None)
    return VersionSummary(
        id=version.id,
        chapter_id=version.chapter_id,
        version=version.version,
        status=version.status,
        source=version.source,
        parent_version_id=version.parent_version_id,
        score=score if isinstance(score, (int, float)) else None,
        word_count=version.word_count,
        provider=version.provider,
        model=version.model,
        created_at=version.created_at,
        accepted_at=version.accepted_at,
    )


def _changes_made(brief: object) -> list[str]:
    if not isinstance(brief, dict):
        return []
    raw = brief.get("instructions", [])
    if not isinstance(raw, list):
        return []
    changes: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            value = item.get("required_change") or item.get("problem")
            if isinstance(value, str):
                changes.append(value)
    return changes
