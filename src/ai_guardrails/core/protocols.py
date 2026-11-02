"""Structural interfaces, so integrations can accept the real service or a fake."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from ai_guardrails.core.types import CheckOutcome, ValidationResult


class Checker(Protocol):
    """One configured validator, ready to run. Implemented by the engine."""

    validator_id: str

    async def check(self, text: str) -> CheckOutcome:
        """Run the validator. Raises ``GuardrailsExecutionError`` if it crashes."""
        ...


class GuardrailsLike(Protocol):
    """The subset of ``GuardrailsService`` that integrations rely on."""

    async def validate_input(
        self,
        text: Any,
        *,
        profile: str | None = None,
        request_id: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> ValidationResult: ...

    async def validate_output(
        self,
        text: Any,
        *,
        profile: str | None = None,
        request_id: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> ValidationResult: ...
