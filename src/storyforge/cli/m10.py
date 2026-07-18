"""Milestone 10 provider governance, usage, budget, and smoke commands."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import Engine

from storyforge.application import DomainServiceFactory, GovernanceApplicationService
from storyforge.database import SessionFactory, create_database_engine, create_session_factory
from storyforge.enums import BudgetPeriod, ModelProfile, PrivacyPolicy, ProviderCallStatus, TaskType
from storyforge.exceptions import ConfigurationError, DomainValidationError
from storyforge.llm import OpenAICompatibleConfig, OpenAICompatibleProvider
from storyforge.llm.types import LLMMessage, PromptReference, PromptRequest
from storyforge.m10_demo import run_demo_m10
from storyforge.schemas.api import ProjectBudgetUpdateRequest
from storyforge.settings import Settings


class _SmokeResponse(BaseModel):
    ok: Literal["ok"]


@dataclass(frozen=True, slots=True)
class _Services:
    engine: Engine
    governance: GovernanceApplicationService


@contextmanager
def _services() -> Iterator[_Services]:
    settings = Settings.from_env()
    engine = create_database_engine(settings.database_url)
    session_factory: SessionFactory = create_session_factory(engine)
    factory = DomainServiceFactory(session_factory, settings)
    try:
        yield _Services(
            engine=engine,
            governance=GovernanceApplicationService(session_factory, factory),
        )
    finally:
        engine.dispose()


def _provider_list(_: argparse.Namespace) -> list[dict[str, object]]:
    with _services() as services:
        return [item.model_dump(mode="json") for item in services.governance.providers()]


def _provider_health(_: argparse.Namespace) -> list[dict[str, object]]:
    with _services() as services:
        return [item.model_dump(mode="json") for item in services.governance.health()]


def _provider_smoke(args: argparse.Namespace) -> dict[str, object]:
    settings = Settings.from_env()
    if not settings.enable_real_provider_tests:
        raise ConfigurationError(
            "Real provider smoke tests require STORYFORGE_ENABLE_REAL_PROVIDER_TESTS=true"
        )
    if settings.llm_provider == "mock" or args.provider != settings.llm_provider:
        raise DomainValidationError("Smoke provider must match the configured external provider")
    key = settings.llm_api_key
    if key is None:
        raise ConfigurationError("Configured smoke provider has no server-side API key")
    provider = OpenAICompatibleProvider(
        OpenAICompatibleConfig(
            api_key=key,
            model=settings.llm_model,
            base_url=settings.llm_api_base_url,
            timeout_seconds=min(settings.llm_timeout_seconds, 30),
            max_retries=0,
            repair_retries=0,
            retry_base_delay_seconds=0,
            structured_output_mode=settings.llm_structured_output_mode,
            max_output_tokens=64,
            provider_name=settings.llm_provider,
        )
    )
    try:
        result = provider.generate(
            PromptRequest(
                prompt=PromptReference("provider.smoke", "v1"),
                messages=(
                    LLMMessage(
                        "system",
                        "Return one minimal JSON object matching the supplied schema.",
                    ),
                    LLMMessage("user", 'Return exactly the JSON meaning {"ok":"ok"}.'),
                ),
            ),
            _SmokeResponse,
        )
    finally:
        provider.close()
    return {
        "provider": result.provider,
        "model": result.model,
        "authentication": "succeeded",
        "structured_output": result.output.ok == "ok",
        "input_tokens": result.usage.input_tokens if result.usage else None,
        "output_tokens": result.usage.output_tokens if result.usage else None,
        "usage_source": result.usage.source if result.usage else "unknown",
        "request_id_present": bool(result.request_id),
        "embedding_tested": False,
    }


def _usage_summary(args: argparse.Namespace) -> dict[str, object]:
    with _services() as services:
        return services.governance.usage_summary(
            project_id=args.project_id,
            workflow_run_id=args.workflow_run_id,
            task_type=TaskType(args.task_type) if args.task_type else None,
            provider=args.provider,
            model=args.model,
            status=ProviderCallStatus(args.status) if args.status else None,
        ).model_dump(mode="json")


def _usage_calls(args: argparse.Namespace) -> dict[str, object]:
    with _services() as services:
        return services.governance.usage_calls(
            page=args.page,
            page_size=args.page_size,
            project_id=args.project_id,
            workflow_run_id=args.workflow_run_id,
            task_type=TaskType(args.task_type) if args.task_type else None,
            provider=args.provider,
            model=args.model,
            status=ProviderCallStatus(args.status) if args.status else None,
        ).model_dump(mode="json")


def _budget_show(args: argparse.Namespace) -> dict[str, object]:
    with _services() as services:
        return services.governance.budget(args.project_id).model_dump(mode="json")


def _budget_set(args: argparse.Namespace) -> dict[str, object]:
    if not args.yes:
        raise DomainValidationError("Budget updates require the explicit --yes flag")
    with _services() as services:
        return services.governance.set_budget(
            args.project_id,
            ProjectBudgetUpdateRequest(
                currency=args.currency,
                soft_limit=args.soft_limit,
                hard_limit=args.hard_limit,
                period=BudgetPeriod(args.period),
                enabled=not args.disabled,
            ),
        ).model_dump(mode="json")


def _model_show(args: argparse.Namespace) -> dict[str, object]:
    with _services() as services:
        return services.governance.model_settings(args.project_id).model_dump(mode="json")


def _model_set(args: argparse.Namespace) -> dict[str, object]:
    if not args.yes:
        raise DomainValidationError("Model profile updates require the explicit --yes flag")
    with _services() as services:
        return services.governance.set_model_profile(
            args.project_id, ModelProfile(args.profile)
        ).model_dump(mode="json")


def _privacy_show(args: argparse.Namespace) -> dict[str, object]:
    return _model_show(args)


def _privacy_set(args: argparse.Namespace) -> dict[str, object]:
    if not args.yes:
        raise DomainValidationError("Privacy policy updates require the explicit --yes flag")
    with _services() as services:
        return services.governance.set_privacy_policy(
            args.project_id, PrivacyPolicy(args.policy)
        ).model_dump(mode="json")


def _demo(_: argparse.Namespace) -> dict[str, object]:
    return run_demo_m10().model_dump(mode="json")


def configure_m10_commands(commands: Any) -> None:
    """Register all M10 commands using the shared application service."""
    provider = commands.add_parser("provider", help="Inspect and smoke-test model providers")
    provider_sub = provider.add_subparsers(dest="provider_command", required=True)
    listing = provider_sub.add_parser("list", help="List registered safe capabilities")
    _output(listing)
    listing.set_defaults(handler=_provider_list)
    health = provider_sub.add_parser("health", help="Show configured and circuit state")
    _output(health)
    health.set_defaults(handler=_provider_health)
    smoke = provider_sub.add_parser("smoke-test", help="Run an explicitly enabled tiny real call")
    _output(smoke)
    smoke.add_argument("--provider", required=True)
    smoke.set_defaults(handler=_provider_smoke)

    usage = commands.add_parser("usage", help="Inspect content-free provider usage")
    usage_sub = usage.add_subparsers(dest="usage_command", required=True)
    summary = usage_sub.add_parser("summary", help="Summarize tokens and estimated cost")
    _usage_arguments(summary)
    summary.set_defaults(handler=_usage_summary)
    calls = usage_sub.add_parser("calls", help="List provider attempts")
    _usage_arguments(calls)
    calls.add_argument("--page", type=int, default=1)
    calls.add_argument("--page-size", type=int, default=20)
    calls.set_defaults(handler=_usage_calls)

    budget = commands.add_parser("budget", help="Show or set project budget")
    budget_sub = budget.add_subparsers(dest="budget_command", required=True)
    show_budget = budget_sub.add_parser("show", help="Show budget and remaining amount")
    _project_output(show_budget)
    show_budget.set_defaults(handler=_budget_show)
    set_budget = budget_sub.add_parser("set", help="Set project budget limits")
    _project_output(set_budget)
    set_budget.add_argument("--soft-limit", required=True)
    set_budget.add_argument("--hard-limit", required=True)
    set_budget.add_argument("--currency", default="USD")
    set_budget.add_argument("--period", choices=tuple(BudgetPeriod), default="lifetime")
    set_budget.add_argument("--disabled", action="store_true")
    set_budget.add_argument("--yes", action="store_true")
    set_budget.set_defaults(handler=_budget_set)

    model = commands.add_parser("model-profile", help="Show or set a controlled model profile")
    model_sub = model.add_subparsers(dest="model_command", required=True)
    show_model = model_sub.add_parser("show", help="Show project model settings")
    _project_output(show_model)
    show_model.set_defaults(handler=_model_show)
    set_model = model_sub.add_parser("set", help="Set a predefined profile")
    _project_output(set_model)
    set_model.add_argument("--profile", choices=tuple(ModelProfile), required=True)
    set_model.add_argument("--yes", action="store_true")
    set_model.set_defaults(handler=_model_set)

    privacy = commands.add_parser("privacy-policy", help="Show or set project privacy policy")
    privacy_sub = privacy.add_subparsers(dest="privacy_command", required=True)
    show_privacy = privacy_sub.add_parser("show", help="Show project privacy settings")
    _project_output(show_privacy)
    show_privacy.set_defaults(handler=_privacy_show)
    set_privacy = privacy_sub.add_parser("set", help="Set an enforced privacy policy")
    _project_output(set_privacy)
    set_privacy.add_argument("--policy", choices=tuple(PrivacyPolicy), required=True)
    set_privacy.add_argument("--yes", action="store_true")
    set_privacy.set_defaults(handler=_privacy_set)

    demo = commands.add_parser("demo-m10", help="Run the complete offline M10 governance demo")
    _output(demo)
    demo.set_defaults(handler=_demo)


def _output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", choices=("human", "json"), default="human")


def _project_output(parser: argparse.ArgumentParser) -> None:
    _output(parser)
    parser.add_argument("--project-id", type=int, required=True)


def _usage_arguments(parser: argparse.ArgumentParser) -> None:
    _output(parser)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--project-id", type=int)
    scope.add_argument("--workflow-run-id", type=int)
    parser.add_argument("--task-type", choices=tuple(TaskType))
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--status", choices=tuple(ProviderCallStatus))
