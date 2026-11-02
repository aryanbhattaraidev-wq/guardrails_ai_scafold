"""Project-level types. Nothing here depends on Guardrails AI."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

_EMPTY: Mapping[str, Any] = MappingProxyType({})


class ValidationStage(StrEnum):
    INPUT = "input"
    OUTPUT = "output"
    RETRIEVAL = "retrieval"
    TOOL_INPUT = "tool_input"
    TOOL_OUTPUT = "tool_output"


class ValidationStatus(StrEnum):
    PASSED = "passed"  # every enabled blocking check passed
    MODIFIED = "modified"  # content was changed by an allowed fix/redaction
    BLOCKED = "blocked"  # a policy check failed; continuation is forbidden
    ERROR = "error"  # validation could not be completed
    SKIPPED = "skipped"  # intentionally skipped by explicit configuration


class ReasonCode(StrEnum):
    """Stable, safe, user-facing codes. They never contain content."""

    POLICY_VIOLATION = "policy_violation"
    VALIDATOR_ERROR = "validator_error"
    VALIDATOR_TIMEOUT = "validator_timeout"
    UNSUPPORTED_CONTENT = "unsupported_content"
    STAGE_DISABLED = "stage_disabled"
    UNSUPPORTED_CONTENT_SKIPPED = "unsupported_content_skipped"
    MODEL_CALL_FAILED = "model_call_failed"
    INVALID_MODEL_OUTPUT = "invalid_model_output"


_ALLOWED = frozenset({ValidationStatus.PASSED, ValidationStatus.MODIFIED, ValidationStatus.SKIPPED})


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Outcome of validating one piece of text at one stage.

    ``content`` and ``diagnostics`` are excluded from ``repr`` so that logging a
    result by accident does not leak prompts, outputs, or PII.
    """

    stage: ValidationStage
    profile: str
    status: ValidationStatus
    request_id: str
    duration_ms: float = 0.0
    content: str | None = field(default=None, repr=False)
    failed_validators: tuple[str, ...] = ()
    reason_code: ReasonCode | None = None
    message: str | None = None  # safe, user-facing
    metadata: Mapping[str, str] = field(default=_EMPTY, repr=False)
    diagnostics: Mapping[str, Any] = field(default=_EMPTY, repr=False)  # internal only

    @property
    def is_allowed(self) -> bool:
        """True if the caller may continue with ``content`` (or the original, if skipped)."""
        return self.status in _ALLOWED


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    """What one validator concluded, independent of Guardrails AI's classes.

    ``passed`` means "no violation"; ``fixed_value`` is set only when the
    validator reported a violation *and* supplied a corrected string.
    """

    validator_id: str
    passed: bool
    fixed_value: str | None = None


@dataclass(frozen=True, slots=True)
class GuardedCallResult:
    """Outcome of ``guarded_call``: input check, model call, output check."""

    status: ValidationStatus
    request_id: str
    content: str | None = field(default=None, repr=False)
    reason_code: ReasonCode | None = None
    message: str | None = None
    input_result: ValidationResult | None = None
    output_result: ValidationResult | None = None
    diagnostics: Mapping[str, Any] = field(default=_EMPTY, repr=False)

    @property
    def is_allowed(self) -> bool:
        return self.status in _ALLOWED
