"""Explicit provider data-egress decisions."""

from __future__ import annotations

from storyforge.enums import PrivacyPolicy
from storyforge.exceptions import PrivacyPolicyError
from storyforge.llm.types import LLMMessage, PromptRequest
from storyforge.privacy.models import PolicyDecision, RedactionSummary
from storyforge.privacy.redaction import RedactionService


class ProviderDataPolicy:
    """Block offline egress and minimize strict-provider messages."""

    def __init__(self, redactor: RedactionService | None = None) -> None:
        self._redactor = redactor or RedactionService()

    def prepare(
        self,
        request: PromptRequest,
        *,
        policy: PrivacyPolicy,
        external: bool,
    ) -> tuple[PromptRequest, PolicyDecision]:
        if policy is PrivacyPolicy.OFFLINE and external:
            raise PrivacyPolicyError("Offline privacy policy blocks external providers")
        if policy is not PrivacyPolicy.STRICT or not external:
            return request, PolicyDecision(policy=policy, allowed=True, reason="policy_allowed")

        counts: dict[str, int] = {}
        messages: list[LLMMessage] = []
        for message in request.messages:
            redacted, summary = self._redactor.redact(message.content)
            messages.append(LLMMessage(role=message.role, content=redacted))
            for category, amount in summary.categories.items():
                counts[category] = counts.get(category, 0) + amount
        return (
            PromptRequest(prompt=request.prompt, messages=tuple(messages)),
            PolicyDecision(
                policy=policy,
                allowed=True,
                reason="strict_minimum_context",
                redactions=RedactionSummary(categories=counts),
            ),
        )
