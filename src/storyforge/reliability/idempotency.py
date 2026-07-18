"""Database-enforced provider-call idempotency claims."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from storyforge.database import SessionFactory
from storyforge.enums import IdempotencyStatus
from storyforge.exceptions import IdempotencyConflictError
from storyforge.models import ProviderIdempotencyRecord
from storyforge.usage.repositories import ProviderIdempotencyRepository


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    replay: bool


class IdempotencyService:
    """Own one normalized request across retries, fallback, and node replay."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def claim(self, key: str) -> IdempotencyClaim:
        try:
            with self._session_factory.begin() as session:
                repository = ProviderIdempotencyRepository(session)
                current = repository.for_key(key, lock=True)
                if current is None:
                    repository.add(
                        ProviderIdempotencyRecord(
                            idempotency_key=key,
                            status=IdempotencyStatus.ACTIVE,
                        )
                    )
                    return IdempotencyClaim(replay=False)
                if current.status is IdempotencyStatus.SUCCEEDED:
                    return IdempotencyClaim(replay=True)
                if current.status is IdempotencyStatus.ACTIVE:
                    raise IdempotencyConflictError("Identical provider request is already active")
                current.status = IdempotencyStatus.ACTIVE
                current.provider_call_id = None
                current.response_hash = None
                current.error_code = None
                return IdempotencyClaim(replay=False)
        except IntegrityError as exc:
            raise IdempotencyConflictError("Identical provider request is already active") from exc

    def succeed(self, key: str, provider_call_id: int, response_hash: str) -> None:
        self._finish(
            key,
            status=IdempotencyStatus.SUCCEEDED,
            provider_call_id=provider_call_id,
            response_hash=response_hash,
            error_code=None,
        )

    def fail(self, key: str, error_code: str) -> None:
        self._finish(
            key,
            status=IdempotencyStatus.FAILED,
            provider_call_id=None,
            response_hash=None,
            error_code=error_code,
        )

    def _finish(
        self,
        key: str,
        *,
        status: IdempotencyStatus,
        provider_call_id: int | None,
        response_hash: str | None,
        error_code: str | None,
    ) -> None:
        with self._session_factory.begin() as session:
            current = ProviderIdempotencyRepository(session).for_key(key, lock=True)
            if current is None:
                raise RuntimeError("Provider idempotency record disappeared")
            current.status = status
            current.provider_call_id = provider_call_id
            current.response_hash = response_hash
            current.error_code = error_code
