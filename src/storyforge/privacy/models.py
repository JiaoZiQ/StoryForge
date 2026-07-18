"""Typed privacy decisions without retaining original sensitive values."""

from pydantic import BaseModel, ConfigDict, Field

from storyforge.enums import PrivacyPolicy


class RedactionSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    categories: dict[str, int] = Field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.categories.values())


class PolicyDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy: PrivacyPolicy
    allowed: bool
    reason: str
    redactions: RedactionSummary = Field(default_factory=RedactionSummary)
