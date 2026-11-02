"""Turns validated configuration into Guardrails AI guards."""

from __future__ import annotations

from guardrails import AsyncGuard, OnFailAction
from guardrails.settings import settings as guardrails_settings

from ai_guardrails.config.schema import OnFail, ValidatorConfig
from ai_guardrails.engine.guardrails_adapter import GuardrailsStep
from ai_guardrails.validators.registry import ValidatorRegistry

# Project action -> Guardrails AI action. The names are not interchangeable:
#   * block / log_and_continue: NOOP, so the engine only *reports* the failure
#     and our policy executor decides what happens (and which validator failed).
#   * redact / fix: FIX, so the engine applies the validator's fix_value.
_ACTION_MAP: dict[OnFail, OnFailAction] = {
    OnFail.BLOCK: OnFailAction.NOOP,
    OnFail.LOG_AND_CONTINUE: OnFailAction.NOOP,
    OnFail.REDACT: OnFailAction.FIX,
    OnFail.FIX: OnFailAction.FIX,
}


def disable_guardrails_telemetry() -> None:
    """Stop Guardrails AI from exporting usage spans to its hosted endpoint.

    guardrails-ai enables anonymous metrics by default. This package is
    privacy-sensitive, so it is switched off unconditionally.
    """
    guardrails_settings.rc.enable_metrics = False


class GuardFactory:
    """Builds one ``GuardrailsStep`` per configured validator."""

    def __init__(self, registry: ValidatorRegistry) -> None:
        self._registry = registry

    def build(self, config: ValidatorConfig) -> GuardrailsStep:
        # Validators read the metrics flag when constructed, so disable first.
        disable_guardrails_telemetry()
        validator = self._registry.build(config.name, config.params, _ACTION_MAP[config.on_fail])
        guard = AsyncGuard().use(validator)  # type: ignore[no-untyped-call]
        # Guard.configure() re-reads ~/.guardrailsrc, which can switch metrics
        # back on, so pass the flag explicitly and then re-assert the global.
        guard.configure(allow_metrics_collection=False)
        disable_guardrails_telemetry()
        return GuardrailsStep(validator_id=config.name, guard=guard)
