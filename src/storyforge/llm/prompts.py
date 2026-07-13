"""Central registration and rendering for named, versioned prompts."""

from collections.abc import Mapping
from dataclasses import dataclass
from string import Formatter

from storyforge.llm.exceptions import PromptRegistryError
from storyforge.llm.types import LLMMessage, MessageRole, PromptReference, PromptRequest


@dataclass(frozen=True, slots=True)
class PromptMessageTemplate:
    """A role and format-string pair inside a prompt template."""

    role: MessageRole
    template: str

    def __post_init__(self) -> None:
        if not self.template.strip():
            raise PromptRegistryError("Prompt message template must not be empty")


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """Named and versioned collection of message templates."""

    name: str
    version: str
    messages: tuple[PromptMessageTemplate, ...]

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.version.strip():
            raise PromptRegistryError("Prompt name and version must not be empty")
        if not self.messages:
            raise PromptRegistryError("Prompt template must contain at least one message")

    def render(self, variables: Mapping[str, object] | None = None) -> PromptRequest:
        """Render all messages while rejecting missing or unused variables."""
        values = dict(variables or {})
        required: set[str] = set()
        formatter = Formatter()
        for message in self.messages:
            for _, field_name, _, _ in formatter.parse(message.template):
                if field_name is None:
                    continue
                if not field_name.isidentifier():
                    raise PromptRegistryError(
                        f"Prompt {self.name}@{self.version} uses unsupported field {field_name!r}"
                    )
                required.add(field_name)

        missing = required - values.keys()
        unexpected = values.keys() - required
        if missing:
            names = ", ".join(sorted(missing))
            raise PromptRegistryError(
                f"Prompt {self.name}@{self.version} is missing variables: {names}"
            )
        if unexpected:
            names = ", ".join(sorted(unexpected))
            raise PromptRegistryError(
                f"Prompt {self.name}@{self.version} received unused variables: {names}"
            )

        try:
            rendered = tuple(
                LLMMessage(role=message.role, content=message.template.format_map(values))
                for message in self.messages
            )
        except (KeyError, ValueError) as exc:
            raise PromptRegistryError(
                f"Prompt {self.name}@{self.version} could not be rendered"
            ) from exc
        return PromptRequest(
            prompt=PromptReference(name=self.name, version=self.version),
            messages=rendered,
        )


class PromptRegistry:
    """In-memory source of truth for prompt templates and their default versions."""

    def __init__(self) -> None:
        self._templates: dict[tuple[str, str], PromptTemplate] = {}
        self._defaults: dict[str, str] = {}

    def register(self, template: PromptTemplate, *, make_default: bool = False) -> None:
        """Register one immutable prompt version."""
        key = (template.name, template.version)
        if key in self._templates:
            raise PromptRegistryError(
                f"Prompt {template.name}@{template.version} is already registered"
            )
        self._templates[key] = template
        if make_default or template.name not in self._defaults:
            self._defaults[template.name] = template.version

    def set_default(self, name: str, version: str) -> None:
        """Select an already registered version as the name's default."""
        if (name, version) not in self._templates:
            raise PromptRegistryError(f"Prompt {name}@{version} is not registered")
        self._defaults[name] = version

    def get(self, name: str, version: str | None = None) -> PromptTemplate:
        """Return an exact version, or the explicitly selected default."""
        selected_version = version or self._defaults.get(name)
        if selected_version is None:
            raise PromptRegistryError(f"Prompt {name!r} is not registered")
        try:
            return self._templates[(name, selected_version)]
        except KeyError as exc:
            raise PromptRegistryError(
                f"Prompt {name}@{selected_version} is not registered"
            ) from exc

    def render(
        self,
        name: str,
        *,
        variables: Mapping[str, object] | None = None,
        version: str | None = None,
    ) -> PromptRequest:
        """Render a registered prompt and preserve its resolved version."""
        return self.get(name, version).render(variables)

    def versions(self, name: str) -> tuple[str, ...]:
        """List registered versions for one prompt name."""
        versions = sorted(
            version for prompt_name, version in self._templates if prompt_name == name
        )
        return tuple(versions)
