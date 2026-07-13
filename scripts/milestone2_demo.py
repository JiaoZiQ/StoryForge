"""Run the Milestone 2 structured-output path without network access."""

import json

from pydantic import BaseModel, ConfigDict

from storyforge.llm import (
    MockLLMProvider,
    PromptMessageTemplate,
    PromptRegistry,
    PromptTemplate,
)


class DemoOutput(BaseModel):
    """Small response contract used only by the offline demonstration."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    next_step: str


def main() -> None:
    """Render a versioned prompt and validate deterministic mock output."""
    registry = PromptRegistry()
    registry.register(
        PromptTemplate(
            name="demo.next-step",
            version="1.0.0",
            messages=(
                PromptMessageTemplate(
                    role="system",
                    template="Return the next development step as structured data.",
                ),
                PromptMessageTemplate(role="user", template="Milestone: {milestone}"),
            ),
        )
    )
    request = registry.render("demo.next-step", variables={"milestone": "2"})
    provider = MockLLMProvider(
        {
            DemoOutput: {
                "summary": "Structured output validated locally.",
                "next_step": "Stop after Milestone 2 acceptance.",
            }
        }
    )
    response = provider.generate(request, DemoOutput)
    print(
        json.dumps(
            {
                "provider": response.provider,
                "prompt": response.prompt.name,
                "prompt_version": response.prompt.version,
                "output": response.output.model_dump(mode="json"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
