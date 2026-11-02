"""Wrap an application's own model call with input and output guardrails.

This module never creates an LLM client and never makes a model call of its
own. The application passes the function it already uses.

Contract
--------
* Expected policy outcomes (blocked, redacted, validator errors that fail
  closed) are **returned** as a ``GuardedCallResult``; they never raise.
* If the model callable raises, the result has ``status=error`` and
  ``reason_code=model_call_failed`` (only the exception *type* is recorded).
  Pass ``raise_on_error=True`` to get a ``ModelCallError`` instead, with the
  original exception chained as ``__cause__``.
* If the callable returns something that is not ``str`` (and no ``extract_text``
  was given), the result has ``reason_code=invalid_model_output``.
* ``asyncio.CancelledError`` always propagates.
* The model is never retried.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from ai_guardrails.core.exceptions import ModelCallError
from ai_guardrails.core.protocols import GuardrailsLike
from ai_guardrails.core.sync import run_sync
from ai_guardrails.core.types import (
    GuardedCallResult,
    ReasonCode,
    ValidationResult,
    ValidationStatus,
)
from ai_guardrails.observability.logging import log_event
from ai_guardrails.policies.executor import MESSAGES

# Takes the validated text; returns text (or anything ``extract_text`` can read).
LlmCall = Callable[[str], Any | Awaitable[Any]]


async def guarded_call(
    user_input: Any,
    llm_call: LlmCall,
    *,
    guardrails: GuardrailsLike,
    profile: str | None = None,
    request_id: str | None = None,
    metadata: Mapping[str, str] | None = None,
    extract_text: Callable[[Any], str] | None = None,
    raise_on_error: bool = False,
) -> GuardedCallResult:
    """Validate input, call the model with the validated text, validate output.

    ``llm_call`` may be a plain function (run in a worker thread so it cannot
    block the event loop) or an ``async def``. It receives only text that
    passed the input policy, with any redactions applied.
    ``extract_text`` converts a provider response object to a string.
    """
    rid = request_id or uuid.uuid4().hex

    input_result = await guardrails.validate_input(
        user_input, profile=profile, request_id=rid, metadata=metadata
    )
    if not input_result.is_allowed:
        return _from_blocked_input(input_result)

    # When the stage is disabled/skipped, content is the original text. If a
    # non-text payload was explicitly allowed through (on_unsupported_content:
    # skip) there is no validated text, so the original is forwarded as configured.
    model_input = input_result.content if input_result.content is not None else user_input

    try:
        raw = await _invoke(llm_call, model_input)
    except Exception as exc:  # noqa: BLE001 - CancelledError is a BaseException and propagates
        log_event(
            "model_call_failed",
            logging.WARNING,
            request_id=rid,
            error_type=type(exc).__name__,
        )
        if raise_on_error:
            raise ModelCallError(f"model call failed: {type(exc).__name__}") from exc
        return _error(rid, ReasonCode.MODEL_CALL_FAILED, input_result, type(exc).__name__)

    try:
        text = extract_text(raw) if extract_text else raw
    except Exception as exc:  # noqa: BLE001
        return _error(rid, ReasonCode.INVALID_MODEL_OUTPUT, input_result, type(exc).__name__)
    if not isinstance(text, str):
        return _error(rid, ReasonCode.INVALID_MODEL_OUTPUT, input_result, type(text).__name__)

    output_result = await guardrails.validate_output(
        text, profile=profile, request_id=rid, metadata=metadata
    )
    if not output_result.is_allowed:
        return GuardedCallResult(
            status=output_result.status,
            request_id=rid,
            content=None,
            reason_code=output_result.reason_code,
            message=output_result.message,
            input_result=input_result,
            output_result=output_result,
        )

    status = output_result.status
    if input_result.status is ValidationStatus.MODIFIED and status is not ValidationStatus.MODIFIED:
        status = ValidationStatus.MODIFIED
    return GuardedCallResult(
        status=status,
        request_id=rid,
        content=output_result.content,
        input_result=input_result,
        output_result=output_result,
    )


def guarded_call_sync(
    user_input: Any,
    llm_call: LlmCall,
    *,
    guardrails: GuardrailsLike,
    **kwargs: Any,
) -> GuardedCallResult:
    """Blocking variant of ``guarded_call`` for scripts (no running event loop)."""
    return run_sync(guarded_call(user_input, llm_call, guardrails=guardrails, **kwargs))


async def _invoke(llm_call: LlmCall, text: Any) -> Any:
    is_async = inspect.iscoroutinefunction(llm_call) or inspect.iscoroutinefunction(
        getattr(llm_call, "__call__", None)  # noqa: B004 - callable objects with async __call__
    )
    result = llm_call(text) if is_async else await asyncio.to_thread(llm_call, text)
    if inspect.isawaitable(result):
        result = await result
    return result


def _from_blocked_input(result: ValidationResult) -> GuardedCallResult:
    return GuardedCallResult(
        status=result.status,
        request_id=result.request_id,
        content=None,
        reason_code=result.reason_code,
        message=result.message,
        input_result=result,
    )


def _error(
    request_id: str,
    reason: ReasonCode,
    input_result: ValidationResult,
    error_type: str,
) -> GuardedCallResult:
    return GuardedCallResult(
        status=ValidationStatus.ERROR,
        request_id=request_id,
        content=None,
        reason_code=reason,
        message=MESSAGES[reason],
        input_result=input_result,
        diagnostics={"error_type": error_type},
    )
