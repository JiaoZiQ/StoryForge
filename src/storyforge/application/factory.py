"""Request-scoped construction of existing domain services and LLM providers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import make_url

from storyforge.agents import CriticAgent, FactExtractorAgent, RevisionAgent, WriterAgent
from storyforge.consistency import ConsistencyChecker
from storyforge.database import SessionFactory
from storyforge.demo import build_critic_provider, build_demo_provider
from storyforge.embeddings import embedding_provider
from storyforge.embeddings.governed import GovernedEmbeddingProvider
from storyforge.enums import TaskType
from storyforge.evaluation import EvaluationScorer, MechanicalEvaluator
from storyforge.exceptions import DomainValidationError, EntityNotFoundError
from storyforge.llm import (
    LLMProvider,
    OpenAICompatibleConfig,
    OpenAICompatibleProvider,
)
from storyforge.m5_demo import build_m5_provider
from storyforge.memory import MemoryIndexService
from storyforge.prompts import build_prompt_registry
from storyforge.providers import (
    GovernedLLMProvider,
    ModelRouter,
    ProviderCallContext,
    build_provider_registry,
)
from storyforge.reliability import CircuitBreaker, ProviderRateLimiter, RetryPolicy
from storyforge.repositories import ChapterRepository, ProjectRepository
from storyforge.retrieval import (
    FactRetriever,
    GraphRetriever,
    HybridRetriever,
    HybridWeights,
    KeywordRetriever,
    VectorRetriever,
)
from storyforge.revision import AcceptanceEvaluator, RevisionBriefBuilder
from storyforge.services import (
    ChapterGenerationService,
    ChapterVersionService,
    ChapterWorkflowService,
    ContextBuilder,
    EvaluationService,
)
from storyforge.settings import Settings
from storyforge.usage import BudgetService


class DomainServiceFactory:
    """Build fresh, explicitly configured services for one adapter operation."""

    def __init__(self, session_factory: SessionFactory, settings: Settings) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.provider_registry = build_provider_registry(settings)
        self.model_router = ModelRouter(self.provider_registry, settings)
        self.rate_limiter = ProviderRateLimiter(
            requests_per_minute=settings.rate_limit_rpm,
            tokens_per_minute=settings.rate_limit_tpm,
            max_concurrency=settings.provider_max_concurrency,
        )
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=settings.circuit_failure_threshold,
            cooldown_seconds=settings.circuit_cooldown_seconds,
        )

    def validate_provider(self, override: str | None) -> None:
        if override is not None and override != self.settings.llm_provider:
            raise DomainValidationError(
                "Provider override must match the configured application provider"
            )

    def project_target(self, project_id: int) -> int:
        with self.session_factory() as session:
            project = ProjectRepository(session).get(project_id)
            if project is None:
                raise EntityNotFoundError(f"Project {project_id} was not found")
            return project.target_chapters

    @contextmanager
    def provider(
        self,
        purpose: str,
        *,
        project_id: int | None = None,
        chapter_number: int | None = None,
        override: str | None = None,
    ) -> Iterator[LLMProvider]:
        """Yield a provider and close real HTTP resources deterministically."""
        self.validate_provider(override)
        raw_provider: LLMProvider
        if self.settings.llm_provider == "mock":
            if purpose == "planning":
                if project_id is None:
                    raise DomainValidationError("Planning provider requires a project ID")
                raw_provider = build_demo_provider(self.project_target(project_id))
            elif purpose == "generation":
                if project_id is None or chapter_number is None:
                    raise DomainValidationError("Generation provider requires a chapter")
                raw_provider = build_demo_provider(
                    self.project_target(project_id), chapter_number=chapter_number
                )
            elif purpose == "evaluation":
                raw_provider = build_critic_provider(self.settings.mock_critic_scenario)
            elif purpose == "workflow":
                raw_provider = build_m5_provider(self.settings.mock_workflow_scenario)
            else:
                raise DomainValidationError(f"Unsupported provider purpose: {purpose}")
        else:
            key = self.settings.llm_api_key
            if key is None:
                raise DomainValidationError("Configured provider has no API key")
            raw_provider = OpenAICompatibleProvider(
                OpenAICompatibleConfig(
                    api_key=key,
                    model=self.settings.llm_model,
                    base_url=self.settings.llm_api_base_url,
                    timeout_seconds=self.settings.llm_timeout_seconds,
                    max_retries=0,
                    repair_retries=self.settings.llm_repair_retries,
                    retry_base_delay_seconds=self.settings.llm_retry_base_delay_seconds,
                    structured_output_mode=self.settings.llm_structured_output_mode,
                    max_output_tokens=self.settings.llm_max_output_tokens,
                    provider_name=self.settings.llm_provider,
                )
            )

        context = self.provider_call_context(project_id, chapter_number)
        providers: dict[tuple[str, str], LLMProvider] = {}
        if self.settings.llm_provider == "mock":
            providers[("mock", "mock-storyforge-v1")] = raw_provider
            providers[("mock", "mock-storyforge-fallback-v1")] = raw_provider
        else:
            providers[(self.settings.llm_provider, self.settings.llm_model)] = raw_provider
        provider = GovernedLLMProvider(
            session_factory=self.session_factory,
            providers=providers,
            registry=self.provider_registry,
            router=self.model_router,
            context=context,
            budget=BudgetService(self.session_factory, self.settings),
            rate_limiter=self.rate_limiter,
            circuit_breaker=self.circuit_breaker,
            retry_policy=RetryPolicy(
                max_retries=self.settings.provider_max_retries,
                base_delay_seconds=self.settings.llm_retry_base_delay_seconds,
            ),
            total_deadline_seconds=self.settings.provider_total_deadline_seconds,
        )
        try:
            yield provider
        finally:
            if isinstance(raw_provider, OpenAICompatibleProvider):
                raw_provider.close()

    def provider_call_context(
        self, project_id: int | None, chapter_number: int | None
    ) -> ProviderCallContext:
        """Resolve persisted project policy and optional chapter identity."""
        profile = self.settings.model_profile
        privacy = self.settings.privacy_policy
        chapter_id: int | None = None
        if project_id is not None:
            with self.session_factory() as session:
                project = ProjectRepository(session).get(project_id)
                if project is None:
                    raise EntityNotFoundError(f"Project {project_id} was not found")
                profile = project.model_profile
                privacy = project.privacy_policy
                if chapter_number is not None:
                    chapter = ChapterRepository(session).get_by_number(project_id, chapter_number)
                    chapter_id = chapter.id if chapter is not None else None
        return ProviderCallContext(
            project_id=project_id,
            chapter_id=chapter_id,
            profile=profile,
            privacy_policy=privacy,
        )

    def generation_service(self, provider: LLMProvider) -> ChapterGenerationService:
        registry = build_prompt_registry()
        return ChapterGenerationService(
            self.session_factory,
            self.context_builder(),
            WriterAgent(provider, registry),
            FactExtractorAgent(provider, registry),
        )

    def evaluation_service(self, provider: LLMProvider) -> EvaluationService:
        return EvaluationService(
            self.session_factory,
            MechanicalEvaluator(),
            ConsistencyChecker(),
            CriticAgent(provider, build_prompt_registry()),
            EvaluationScorer(),
        )

    def workflow_service(self, provider: LLMProvider) -> ChapterWorkflowService:
        registry = build_prompt_registry()
        versions = ChapterVersionService(
            self.session_factory,
            self.context_builder(),
            WriterAgent(provider, registry),
            FactExtractorAgent(provider, registry),
            RevisionAgent(provider, registry),
            RevisionBriefBuilder(),
            AcceptanceEvaluator(),
            self.memory_index_service(),
        )
        return ChapterWorkflowService(
            self.session_factory,
            versions,
            self.evaluation_service(provider),
            self.checkpoint_path(),
        )

    def memory_index_service(self) -> MemoryIndexService:
        return MemoryIndexService(
            self.session_factory,
            self.governed_embedding_provider,
            provider_name=self.settings.embedding_provider,
            model_name=self.settings.embedding_model,
            dimensions=self.settings.embedding_dimensions,
        )

    def hybrid_retriever(self) -> HybridRetriever:
        keyword = KeywordRetriever(self.session_factory)
        vector = VectorRetriever(
            self.session_factory,
            self.governed_embedding_provider,
            dimensions=self.settings.embedding_dimensions,
        )
        fact = FactRetriever(self.session_factory)
        graph = GraphRetriever(self.session_factory)
        return HybridRetriever(
            keyword=keyword.retrieve,
            vector=vector.retrieve,
            fact=fact.retrieve,
            graph=graph.retrieve,
            weights=HybridWeights(
                keyword=self.settings.hybrid_keyword_weight,
                vector=self.settings.hybrid_vector_weight,
                fact=self.settings.hybrid_fact_weight,
                graph=self.settings.hybrid_graph_weight,
            ),
        )

    def context_builder(self) -> ContextBuilder:
        return ContextBuilder(
            self.session_factory,
            hybrid_retriever=self.hybrid_retriever(),
            retrieval_top_k=self.settings.retrieval_top_k,
            retrieval_max_context_chars=self.settings.retrieval_max_context_chars,
        )

    @contextmanager
    def governed_embedding_provider(
        self, project_id: int, task_type: TaskType
    ) -> Iterator[GovernedEmbeddingProvider]:
        """Yield embeddings behind the same policy and audit controls as LLM calls."""
        route = self.model_router.route(task_type, self.settings.model_profile)
        capability = self.provider_registry.get(route.primary_model)
        context = self.provider_call_context(project_id, None)
        with embedding_provider(self.settings) as raw_provider:
            yield GovernedEmbeddingProvider(
                provider=raw_provider,
                capability=capability,
                task_type=task_type,
                session_factory=self.session_factory,
                context=context,
                budget=BudgetService(self.session_factory, self.settings),
                rate_limiter=self.rate_limiter,
                circuit_breaker=self.circuit_breaker,
                max_retries=self.settings.provider_max_retries,
            )

    def checkpoint_path(self) -> Path:
        if self.settings.checkpoint_path is not None:
            return self.settings.checkpoint_path.expanduser().resolve()
        url = make_url(self.settings.database_url)
        if url.get_backend_name() == "sqlite" and url.database not in {None, "", ":memory:"}:
            database_path = Path(str(url.database)).expanduser().resolve()
            return database_path.with_name(f"{database_path.stem}.checkpoints.sqlite3")
        return Path(".storyforge-checkpoints.sqlite3").resolve()
