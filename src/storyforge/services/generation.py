"""Durable chapter generation and fact extraction orchestration."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from storyforge.agents import FactExtractorAgent, WriterAgent
from storyforge.consistency.normalizer import FactNormalizer
from storyforge.database import SessionFactory
from storyforge.enums import (
    ChapterStatus,
    ChapterVersionStatus,
    FactStatus,
    ForeshadowingStatus,
    ProjectStatus,
)
from storyforge.exceptions import (
    AgentExecutionError,
    ChapterGenerationError,
    EntityNotFoundError,
    InvalidStateError,
)
from storyforge.models import ChapterVersion, Fact, Foreshadowing
from storyforge.repositories import (
    ChapterRepository,
    CharacterRepository,
    ForeshadowingRepository,
    ProjectRepository,
)
from storyforge.schemas.context import ContextBuildRequest
from storyforge.schemas.generation import (
    ChapterDraft,
    ChapterGenerationRequest,
    ChapterGenerationResult,
    FactExtractionRequest,
    FactExtractionResult,
    GenerationMetadata,
)
from storyforge.services.context_builder import ContextBuilder


class ChapterGenerationService:
    """Generate one chapter and persist its structured aftermath."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context_builder: ContextBuilder,
        writer: WriterAgent,
        fact_extractor: FactExtractorAgent,
    ) -> None:
        self._session_factory = session_factory
        self._context_builder = context_builder
        self._writer = writer
        self._fact_extractor = fact_extractor

    def generate(self, request: ChapterGenerationRequest) -> ChapterGenerationResult:
        """Run context, writer, extraction, and persistence with explicit failure states."""
        self._validate_start(request)
        context = self._context_builder.build(
            ContextBuildRequest(
                project_id=request.project_id,
                chapter_number=request.chapter_number,
                max_context_chars=request.max_context_chars,
            )
        )
        self._set_running(request)
        try:
            writer_result = self._writer.write(context)
        except AgentExecutionError as exc:
            self._mark_failure(request, ChapterStatus.FAILED)
            raise ChapterGenerationError("WriterAgent failed") from exc

        generated_at = datetime.now(UTC)
        writer_metadata = GenerationMetadata(
            provider=writer_result.provider,
            model=writer_result.model,
            prompt_versions=writer_result.prompt_versions,
            attempts=writer_result.attempts,
            duration_ms=writer_result.duration_ms,
            generated_at=generated_at,
        )
        try:
            version = self._persist_draft(request, writer_result.output, writer_metadata)
        except SQLAlchemyError as exc:
            self._mark_failure(request, ChapterStatus.FAILED)
            raise ChapterGenerationError("Draft persistence failed and was rolled back") from exc
        extraction_request = FactExtractionRequest(
            project_id=request.project_id,
            chapter_number=request.chapter_number,
            chapter_content=writer_result.output.content,
            context_summary=writer_result.output.summary,
            new_entities=writer_result.output.new_entities,
        )
        try:
            extraction_result = self._fact_extractor.extract(extraction_request)
        except AgentExecutionError as exc:
            self._mark_failure(request, ChapterStatus.FACT_EXTRACTION_FAILED)
            raise ChapterGenerationError(
                "FactExtractorAgent failed; the generated draft was preserved"
            ) from exc

        metadata = GenerationMetadata(
            provider=writer_result.provider,
            model=writer_result.model,
            prompt_versions={
                **writer_result.prompt_versions,
                **extraction_result.prompt_versions,
            },
            attempts=writer_result.attempts + extraction_result.attempts,
            duration_ms=writer_result.duration_ms + extraction_result.duration_ms,
            generated_at=generated_at,
        )
        try:
            return self._persist_extraction(
                request,
                writer_result.output,
                extraction_result.output,
                metadata,
                version,
            )
        except SQLAlchemyError as exc:
            self._mark_failure(request, ChapterStatus.FACT_EXTRACTION_FAILED)
            raise ChapterGenerationError("Fact persistence failed and was rolled back") from exc

    def _validate_start(self, request: ChapterGenerationRequest) -> None:
        with self._session_factory() as session:
            project = ProjectRepository(session).get(request.project_id)
            if project is None:
                raise EntityNotFoundError(f"Project {request.project_id} was not found")
            allowed_project_statuses = {
                ProjectStatus.PLANNED,
                ProjectStatus.GENERATING,
                ProjectStatus.FAILED,
            }
            if request.regenerate:
                allowed_project_statuses.add(ProjectStatus.COMPLETED)
            if project.status not in allowed_project_statuses:
                raise InvalidStateError(f"Project cannot generate from status {project.status}")
            chapter = ChapterRepository(session).get_by_number(
                request.project_id, request.chapter_number
            )
            if chapter is None:
                raise EntityNotFoundError(
                    f"Chapter {request.chapter_number} was not found for project {request.project_id}"
                )
            if chapter.content.strip() and not request.regenerate:
                raise InvalidStateError("Chapter already has content; pass regenerate=True")
            if chapter.status in {ChapterStatus.GENERATING, ChapterStatus.EXTRACTING_FACTS}:
                raise InvalidStateError("Chapter generation is already in progress")

    def _set_running(self, request: ChapterGenerationRequest) -> None:
        with self._session_factory.begin() as session:
            project = ProjectRepository(session).get(request.project_id)
            chapter = ChapterRepository(session).get_by_number(
                request.project_id, request.chapter_number
            )
            if project is None or chapter is None:
                raise EntityNotFoundError("Project or chapter disappeared before generation")
            project.status = ProjectStatus.GENERATING
            chapter.status = ChapterStatus.GENERATING

    def _persist_draft(
        self,
        request: ChapterGenerationRequest,
        draft: ChapterDraft,
        metadata: GenerationMetadata,
    ) -> int:
        with self._session_factory.begin() as session:
            chapter = ChapterRepository(session).get_by_number(
                request.project_id, request.chapter_number
            )
            if chapter is None:
                raise EntityNotFoundError("Chapter disappeared while saving its draft")
            version = chapter.version + 1 if chapter.content.strip() else chapter.version
            chapter.version = version
            chapter.title = draft.title
            chapter.content = draft.content
            chapter.summary = draft.summary
            chapter.status = ChapterStatus.EXTRACTING_FACTS
            chapter.generation_metadata = metadata.model_dump(mode="json")
            snapshot = ChapterVersion(
                chapter_id=chapter.id,
                version=version,
                title=draft.title,
                content=draft.content,
                summary=draft.summary,
                generation_metadata=metadata.model_dump(mode="json"),
                status=ChapterVersionStatus.DRAFT,
                source="generated",
                word_count=len(draft.content.split()),
                provider=metadata.provider,
                model=metadata.model,
                prompt_versions=metadata.prompt_versions,
            )
            session.add(snapshot)
            session.flush()
            chapter.current_version_id = snapshot.id
        return version

    def _persist_extraction(
        self,
        request: ChapterGenerationRequest,
        draft: ChapterDraft,
        extraction: FactExtractionResult,
        metadata: GenerationMetadata,
        version: int,
    ) -> ChapterGenerationResult:
        with self._session_factory.begin() as session:
            project = ProjectRepository(session).get(request.project_id)
            chapter = ChapterRepository(session).get_by_number(
                request.project_id, request.chapter_number
            )
            if project is None or chapter is None:
                raise EntityNotFoundError("Project or chapter disappeared during extraction")
            snapshot = session.scalar(
                select(ChapterVersion).where(
                    ChapterVersion.chapter_id == chapter.id,
                    ChapterVersion.version == version,
                )
            )
            if snapshot is None:
                raise ChapterGenerationError("Chapter version disappeared during extraction")
            for previous_fact in session.scalars(
                select(Fact).where(
                    Fact.chapter_id == chapter.id,
                    Fact.status == FactStatus.ACCEPTED,
                    Fact.chapter_version_id != snapshot.id,
                )
            ):
                previous_fact.status = FactStatus.SUPERSEDED
            normalizer = FactNormalizer()
            session.add_all(
                Fact(
                    project_id=request.project_id,
                    chapter_id=chapter.id,
                    subject=item.subject,
                    predicate=item.predicate,
                    object=item.object,
                    fact_type=item.fact_type,
                    confidence=item.confidence,
                    source_quote=item.source_quote,
                    valid_from_chapter=item.valid_from_chapter,
                    valid_to_chapter=item.valid_to_chapter,
                    chapter_version_id=snapshot.id,
                    status=FactStatus.ACCEPTED,
                    normalized_hash=normalizer.identity_hash(
                        item.subject, item.predicate, item.object
                    ),
                )
                for item in extraction.facts
            )
            character_count = self._apply_character_updates(session, request.project_id, extraction)
            foreshadowing_count = self._apply_foreshadowing_updates(session, request, extraction)
            for item in session.scalars(
                select(Foreshadowing).where(
                    Foreshadowing.project_id == request.project_id,
                    Foreshadowing.setup_chapter == request.chapter_number,
                    Foreshadowing.status == ForeshadowingStatus.PLANNED,
                )
            ):
                item.status = ForeshadowingStatus.OPEN
            chapter.status = ChapterStatus.GENERATED
            chapter.generation_metadata = metadata.model_dump(mode="json")
            snapshot.generation_metadata = metadata.model_dump(mode="json")
            snapshot.status = ChapterVersionStatus.ACCEPTED
            snapshot.accepted_at = datetime.now(UTC)
            chapter.accepted_version_id = snapshot.id
            chapters = ChapterRepository(session).list_for_project(request.project_id)
            project.status = (
                ProjectStatus.COMPLETED
                if all(item.status == ChapterStatus.GENERATED for item in chapters)
                else ProjectStatus.GENERATING
            )
            result = ChapterGenerationResult(
                project_id=request.project_id,
                chapter_id=chapter.id,
                chapter_number=chapter.chapter_number,
                version=version,
                status=chapter.status,
                title=draft.title,
                summary=draft.summary,
                content=draft.content,
                fact_count=len(extraction.facts),
                character_update_count=character_count,
                foreshadowing_update_count=foreshadowing_count,
                generation_metadata=metadata,
            )
        return result

    @staticmethod
    def _apply_character_updates(
        session: Session, project_id: int, extraction: FactExtractionResult
    ) -> int:
        repository = CharacterRepository(session)
        characters = {item.name: item for item in repository.list_for_project(project_id)}
        count = 0
        for update in extraction.character_updates:
            character = characters.get(update.character_name)
            if character is not None:
                character.current_state = update.value
                count += 1
        return count

    @staticmethod
    def _apply_foreshadowing_updates(
        session: Session,
        request: ChapterGenerationRequest,
        extraction: FactExtractionResult,
    ) -> int:
        repository = ForeshadowingRepository(session)
        count = 0
        for update in extraction.foreshadowing_updates:
            existing = (
                repository.get(update.foreshadowing_id)
                if update.foreshadowing_id is not None
                else None
            )
            if existing is None and update.action == "setup":
                existing = session.scalar(
                    select(Foreshadowing).where(
                        Foreshadowing.project_id == request.project_id,
                        Foreshadowing.setup_chapter == request.chapter_number,
                        Foreshadowing.description == update.description,
                    )
                )
            if existing is not None and existing.project_id != request.project_id:
                continue
            if update.action == "setup":
                if existing is not None:
                    existing.status = ForeshadowingStatus.OPEN
                else:
                    repository.add(
                        Foreshadowing(
                            project_id=request.project_id,
                            setup_chapter=request.chapter_number,
                            expected_payoff_chapter=request.chapter_number,
                            description=update.description,
                            status=ForeshadowingStatus.OPEN,
                        )
                    )
                count += 1
            elif existing is not None and update.action == "resolve":
                existing.status = ForeshadowingStatus.RESOLVED
                existing.payoff_chapter = request.chapter_number
                count += 1
            elif existing is not None and update.action == "advance":
                existing.status = ForeshadowingStatus.OPEN
                count += 1
        return count

    def _mark_failure(
        self, request: ChapterGenerationRequest, chapter_status: ChapterStatus
    ) -> None:
        with self._session_factory.begin() as session:
            project = ProjectRepository(session).get(request.project_id)
            chapter = ChapterRepository(session).get_by_number(
                request.project_id, request.chapter_number
            )
            if project is not None:
                project.status = ProjectStatus.FAILED
            if chapter is not None:
                chapter.status = chapter_status
