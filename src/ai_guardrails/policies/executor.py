"""Runs a stage plan and applies the configured failure policy."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import Any

from ai_guardrails.config.schema import OnFail, RuntimeConfig
from ai_guardrails.core.types import ReasonCode, ValidationResult, ValidationStatus
from ai_guardrails.policies.resolver import PlannedStep, StagePlan

# Safe, user-facing messages. They never include content or validator internals.
MESSAGES: dict[ReasonCode, str] = {
    ReasonCode.POLICY_VIOLATION: "The text was blocked by a content policy.",
    ReasonCode.VALIDATOR_ERROR: "Validation could not be completed.",
    ReasonCode.VALIDATOR_TIMEOUT: "Validation could not be completed in time.",
    ReasonCode.UNSUPPORTED_CONTENT: "This kind of content cannot be validated.",
    ReasonCode.UNSUPPORTED_CONTENT_SKIPPED: "Validation was skipped for unsupported content.",
    ReasonCode.STAGE_DISABLED: "Validation is disabled for this stage.",
    ReasonCode.MODEL_CALL_FAILED: "The model call failed.",
    ReasonCode.INVALID_MODEL_OUTPUT: "The model returned an unusable response.",
}


class PolicyExecutor:
    """Executes steps in order, feeding each step the previous step's output.

    Semantics (see PLAN.md section 8):

    * ``block``: stop; the stage is ``blocked``.
    * ``redact`` / ``fix``: continue with the corrected text only if the engine
      returned a trustworthy fix; otherwise the stage is ``blocked``.
    * ``log_and_continue``: record the violation and continue (config only
      allows this for non-critical validators).
    * A validator *crash or timeout* is not a violation. It fails closed
      (``error``) for critical validators when
      ``fail_closed_on_validator_error`` is true; otherwise it is recorded in
      ``diagnostics['skipped_validators']`` and the stage continues.
    """

    def __init__(self, runtime: RuntimeConfig) -> None:
        self._runtime = runtime

    async def run(
        self,
        plan: StagePlan,
        text: str,
        *,
        request_id: str,
        metadata: Mapping[str, str],
    ) -> ValidationResult:
        started = time.perf_counter()

        def finish(
            status: ValidationStatus,
            *,
            content: str | None,
            failed: list[str] | None = None,
            reason: ReasonCode | None = None,
            diagnostics: dict[str, Any] | None = None,
        ) -> ValidationResult:
            return ValidationResult(
                stage=plan.stage,
                profile=plan.profile,
                status=status,
                request_id=request_id,
                duration_ms=(time.perf_counter() - started) * 1000,
                content=content,
                failed_validators=tuple(failed or ()),
                reason_code=reason,
                message=MESSAGES.get(reason) if reason else None,
                metadata=metadata,
                diagnostics=diagnostics or {},
            )

        if not plan.enabled:
            return finish(ValidationStatus.SKIPPED, content=text, reason=ReasonCode.STAGE_DISABLED)

        current = text
        redacted_by: list[str] = []
        logged_violations: list[str] = []
        skipped_validators: list[str] = []

        def diagnostics(**extra: Any) -> dict[str, Any]:
            data: dict[str, Any] = {
                "redacted_by": redacted_by,
                "logged_violations": logged_violations,
                "skipped_validators": skipped_validators,
            }
            data.update(extra)
            return {k: v for k, v in data.items() if v}

        for step in plan.steps:
            try:
                outcome = await asyncio.wait_for(
                    step.checker.check(current), self._runtime.validation_timeout_seconds
                )
            except Exception as exc:  # noqa: BLE001 - CancelledError is a BaseException, so it still propagates
                # Checkers should raise GuardrailsExecutionError, but any
                # unexpected failure must be treated the same way: not a
                # policy violation, and never a silent pass.
                reason = (
                    ReasonCode.VALIDATOR_TIMEOUT
                    if isinstance(exc, TimeoutError)
                    else ReasonCode.VALIDATOR_ERROR
                )
                if self._fails_closed(step):
                    return finish(
                        ValidationStatus.ERROR,
                        content=None,
                        failed=[step.validator_id],
                        reason=reason,
                        diagnostics=diagnostics(error_type=type(exc).__name__),
                    )
                skipped_validators.append(step.validator_id)
                continue

            if outcome.passed:
                continue

            if step.on_fail is OnFail.LOG_AND_CONTINUE:
                logged_violations.append(step.validator_id)
            elif step.on_fail in (OnFail.REDACT, OnFail.FIX) and outcome.fixed_value is not None:
                current = outcome.fixed_value
                redacted_by.append(step.validator_id)
            else:  # block, or a requested fix that the engine could not supply
                extra = {} if step.on_fail is OnFail.BLOCK else {"no_trustworthy_fix": True}
                return finish(
                    ValidationStatus.BLOCKED,
                    content=None,
                    failed=[step.validator_id],
                    reason=ReasonCode.POLICY_VIOLATION,
                    diagnostics=diagnostics(**extra),
                )

        status = ValidationStatus.MODIFIED if redacted_by else ValidationStatus.PASSED
        return finish(status, content=current, diagnostics=diagnostics())

    def _fails_closed(self, step: PlannedStep) -> bool:
        return step.critical and self._runtime.fail_closed_on_validator_error
