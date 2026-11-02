"""The public entry point: ``GuardrailsService``."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from ai_guardrails.config.schema import Settings
from ai_guardrails.core.exceptions import UnsupportedContentError
from ai_guardrails.core.sync import run_sync
from ai_guardrails.core.types import (
    ReasonCode,
    ValidationResult,
    ValidationStage,
    ValidationStatus,
)
from ai_guardrails.engine.guard_factory import GuardFactory
from ai_guardrails.observability.logging import log_event, log_result
from ai_guardrails.observability.metrics import Metrics
from ai_guardrails.policies.executor import MESSAGES, PolicyExecutor
from ai_guardrails.policies.resolver import PolicyResolver
from ai_guardrails.validators.registry import ValidatorRegistry, default_registry


def serialize_payload(payload: Any) -> str:
    """Turn a tool payload into text for validation, or refuse.

    Policy: ``str`` is used as-is; mappings, lists and tuples of JSON-compatible
    values become canonical JSON (sorted keys, no ASCII escaping). Anything else
    is refused rather than stringified with ``repr()``, because an object's repr
    is not a faithful representation of what a tool will actually receive.
    The validated ``content`` of a tool-stage result is that serialized text.
    """
    if isinstance(payload, str):
        return payload
    if isinstance(payload, Mapping | list | tuple):
        try:
            return json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError):
            pass
    raise UnsupportedContentError(
        f"Cannot serialize payload of type {type(payload).__name__} for validation"
    )


class GuardrailsService:
    """Validates text at the application boundary using configured policies.

    Create once at startup (``from_config``) and share. All validators and guards
    are built eagerly, so a bad config or missing validator package fails there,
    not on the first request.
    """

    def __init__(
        self,
        settings: Settings,
        resolver: PolicyResolver,
        executor: PolicyExecutor,
        metrics: Metrics,
    ) -> None:
        self._settings = settings
        self._resolver = resolver
        self._executor = executor
        self._metrics = metrics

    @classmethod
    def from_config(
        cls,
        settings: Settings,
        *,
        registry: ValidatorRegistry | None = None,
        metrics: Metrics | None = None,
    ) -> GuardrailsService:
        factory = GuardFactory(registry or default_registry())
        resolver = PolicyResolver.from_settings(settings, factory.build)
        if settings.runtime.log_content:
            log_event(
                "content_logging_enabled",
                level=logging.WARNING,
                warning="runtime.log_content is true: prompts and outputs will be logged",
            )
        return cls(settings, resolver, PolicyExecutor(settings.runtime), metrics or Metrics())

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def metrics(self) -> Metrics:
        return self._metrics

    @property
    def profile_names(self) -> list[str]:
        return self._resolver.profile_names

    # --- async API ----------------------------------------------------------

    async def validate(
        self,
        stage: ValidationStage,
        content: Any,
        *,
        profile: str | None = None,
        request_id: str | None = None,
        metadata: Mapping[str, str] | None = None,
        diagnostics: Mapping[str, Any] | None = None,
    ) -> ValidationResult:
        """Validate ``content`` at ``stage`` under ``profile``.

        Raises ``UnknownProfileError`` for a profile that does not exist (a
        programming error). Policy outcomes, validator failures and unsupported
        content are returned as results, never raised.
        """
        rid = request_id or uuid.uuid4().hex
        meta = dict(metadata or {})
        plan = self._resolver.resolve(profile, stage)

        if isinstance(content, str):
            result = await self._executor.run(plan, content, request_id=rid, metadata=meta)
        else:
            result = self._unsupported(plan.profile, stage, rid, meta, stage_enabled=plan.enabled)

        if diagnostics:
            result = _with_diagnostics(result, diagnostics)
        self._metrics.record(result)
        log_result(result, log_content=self._settings.runtime.log_content)
        return result

    async def validate_input(
        self,
        text: Any,
        *,
        profile: str | None = None,
        request_id: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> ValidationResult:
        return await self.validate(
            ValidationStage.INPUT, text, profile=profile, request_id=request_id, metadata=metadata
        )

    async def validate_output(
        self,
        text: Any,
        *,
        profile: str | None = None,
        request_id: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> ValidationResult:
        return await self.validate(
            ValidationStage.OUTPUT, text, profile=profile, request_id=request_id, metadata=metadata
        )

    async def validate_retrieved_context(
        self,
        text: Any,
        metadata: Mapping[str, str] | None = None,
        *,
        profile: str | None = None,
        request_id: str | None = None,
    ) -> ValidationResult:
        """Validate retrieved text. Retrieved documents are untrusted data."""
        return await self.validate(
            ValidationStage.RETRIEVAL,
            text,
            profile=profile,
            request_id=request_id,
            metadata=metadata,
        )

    async def validate_tool_input(
        self,
        tool_name: str,
        payload: Any,
        *,
        profile: str | None = None,
        request_id: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> ValidationResult:
        return await self._validate_tool(
            ValidationStage.TOOL_INPUT, tool_name, payload, profile, request_id, metadata
        )

    async def validate_tool_output(
        self,
        tool_name: str,
        payload: Any,
        *,
        profile: str | None = None,
        request_id: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> ValidationResult:
        """Validate a tool result. Tool output is untrusted data."""
        return await self._validate_tool(
            ValidationStage.TOOL_OUTPUT, tool_name, payload, profile, request_id, metadata
        )

    async def _validate_tool(
        self,
        stage: ValidationStage,
        tool_name: str,
        payload: Any,
        profile: str | None,
        request_id: str | None,
        metadata: Mapping[str, str] | None,
    ) -> ValidationResult:
        try:
            content: Any = serialize_payload(payload)
        except UnsupportedContentError:
            content = payload  # not a str, so validate() reports unsupported content
        return await self.validate(
            stage,
            content,
            profile=profile,
            request_id=request_id,
            metadata=metadata,
            diagnostics={"tool_name": tool_name},
        )

    # --- sync API (for scripts and the CLI) ---------------------------------

    def validate_sync(
        self, stage: ValidationStage, content: Any, **kwargs: Any
    ) -> ValidationResult:
        """Blocking variant of ``validate``. Not callable from a running event loop."""
        return run_sync(self.validate(stage, content, **kwargs))

    def validate_input_sync(self, text: Any, **kwargs: Any) -> ValidationResult:
        return run_sync(self.validate_input(text, **kwargs))

    def validate_output_sync(self, text: Any, **kwargs: Any) -> ValidationResult:
        return run_sync(self.validate_output(text, **kwargs))

    # --- helpers ------------------------------------------------------------

    def _unsupported(
        self,
        profile: str,
        stage: ValidationStage,
        request_id: str,
        metadata: Mapping[str, str],
        *,
        stage_enabled: bool,
    ) -> ValidationResult:
        """Result for non-text content. Never claims the content was inspected."""
        if not stage_enabled:
            status, reason = ValidationStatus.SKIPPED, ReasonCode.STAGE_DISABLED
        elif self._settings.runtime.on_unsupported_content == "skip":
            status, reason = ValidationStatus.SKIPPED, ReasonCode.UNSUPPORTED_CONTENT_SKIPPED
        else:
            status, reason = ValidationStatus.BLOCKED, ReasonCode.UNSUPPORTED_CONTENT
        return ValidationResult(
            stage=stage,
            profile=profile,
            status=status,
            request_id=request_id,
            content=None,
            reason_code=reason,
            message=MESSAGES[reason],
            metadata=metadata,
        )


def _with_diagnostics(result: ValidationResult, extra: Mapping[str, Any]) -> ValidationResult:
    return replace(result, diagnostics={**result.diagnostics, **extra})
