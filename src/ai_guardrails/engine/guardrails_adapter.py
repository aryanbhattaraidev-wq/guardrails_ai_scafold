"""Runs one Guardrails AI guard and reports a project-level ``CheckOutcome``."""

from __future__ import annotations

import asyncio
from typing import Any

from ai_guardrails.core.exceptions import GuardrailsExecutionError
from ai_guardrails.core.types import CheckOutcome
from ai_guardrails.engine.result_mapper import map_outcome


class GuardrailsStep:
    """A single validator wrapped in its own ``AsyncGuard``.

    One guard per validator keeps failure attribution exact (we always know
    which validator objected) and lets the policy layer apply per-validator
    actions, timeouts, and error handling.
    """

    def __init__(self, validator_id: str, guard: Any) -> None:
        self.validator_id = validator_id
        self._guard = guard

    async def check(self, text: str) -> CheckOutcome:
        try:
            outcome = await self._guard.validate(text)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Keep the original as __cause__ for internal debugging, but do not
            # copy its message (it may contain content) into ours.
            raise GuardrailsExecutionError(
                f"validator '{self.validator_id}' raised {type(exc).__name__}"
            ) from exc
        return map_outcome(self.validator_id, text, outcome)
