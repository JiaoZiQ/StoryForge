"""Tests for named, versioned prompt registration and rendering."""

from collections.abc import Callable

import pytest

from storyforge.llm import (
    PromptMessageTemplate,
    PromptRegistry,
    PromptRegistryError,
    PromptTemplate,
)


def _template(version: str, suffix: str = "") -> PromptTemplate:
    return PromptTemplate(
        name="chapter.plan",
        version=version,
        messages=(
            PromptMessageTemplate(role="system", template="Plan a chapter."),
            PromptMessageTemplate(role="user", template="Project: {title}." + suffix),
        ),
    )


def test_registry_resolves_defaults_and_records_exact_rendered_version() -> None:
    registry = PromptRegistry()
    registry.register(_template("1.0.0"))
    registry.register(_template("2.0.0", " Revised."))

    default_request = registry.render("chapter.plan", variables={"title": "North Wind"})
    exact_request = registry.render(
        "chapter.plan",
        version="2.0.0",
        variables={"title": "North Wind"},
    )

    assert default_request.prompt.name == "chapter.plan"
    assert default_request.prompt.version == "1.0.0"
    assert default_request.messages[1].content == "Project: North Wind."
    assert exact_request.prompt.version == "2.0.0"
    assert exact_request.messages[1].content.endswith("Revised.")
    assert registry.versions("chapter.plan") == ("1.0.0", "2.0.0")


def test_registry_can_change_default_version() -> None:
    registry = PromptRegistry()
    registry.register(_template("1.0.0"))
    registry.register(_template("2.0.0"), make_default=True)
    assert registry.get("chapter.plan").version == "2.0.0"

    registry.set_default("chapter.plan", "1.0.0")
    assert registry.get("chapter.plan").version == "1.0.0"


def test_registry_rejects_duplicate_and_unknown_prompts() -> None:
    registry = PromptRegistry()
    registry.register(_template("1.0.0"))

    with pytest.raises(PromptRegistryError, match="already registered"):
        registry.register(_template("1.0.0"))
    with pytest.raises(PromptRegistryError, match="not registered"):
        registry.get("missing")
    with pytest.raises(PromptRegistryError, match="not registered"):
        registry.get("chapter.plan", "9.0.0")
    with pytest.raises(PromptRegistryError, match="not registered"):
        registry.set_default("chapter.plan", "9.0.0")


@pytest.mark.parametrize(
    ("variables", "message"),
    [
        ({}, "missing variables"),
        ({"title": "North Wind", "unused": True}, "unused variables"),
    ],
)
def test_prompt_render_rejects_incorrect_variables(
    variables: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(PromptRegistryError, match=message):
        _template("1.0.0").render(variables)


def test_prompt_render_rejects_complex_format_fields() -> None:
    template = PromptTemplate(
        name="invalid",
        version="1",
        messages=(PromptMessageTemplate(role="user", template="{project.title}"),),
    )
    with pytest.raises(PromptRegistryError, match="unsupported field"):
        template.render({"project": object()})


def test_prompt_render_wraps_empty_rendered_message() -> None:
    template = PromptTemplate(
        name="empty.after.render",
        version="1",
        messages=(PromptMessageTemplate(role="user", template="{value}"),),
    )
    with pytest.raises(PromptRegistryError, match="could not be rendered"):
        template.render({"value": " "})


@pytest.mark.parametrize(
    "factory",
    [
        lambda: PromptMessageTemplate(role="user", template=" "),
        lambda: PromptTemplate(name="", version="1", messages=(_template("1").messages[0],)),
        lambda: PromptTemplate(name="name", version="", messages=(_template("1").messages[0],)),
        lambda: PromptTemplate(name="name", version="1", messages=()),
    ],
)
def test_prompt_components_reject_empty_values(factory: Callable[[], object]) -> None:
    with pytest.raises(PromptRegistryError):
        factory()
