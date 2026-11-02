"""Reject empty or whitespace-only text."""

from __future__ import annotations

from typing import Any

from guardrails.validators import FailResult, PassResult, Validator, register_validator


@register_validator(name="ai_guardrails/non_empty", data_type="string")
class NonEmpty(Validator):
    """Fails when the text is blank. Offers no fix: there is nothing to repair."""

    def _validate(self, value: Any, metadata: dict[str, Any]) -> PassResult | FailResult:
        if isinstance(value, str) and value.strip():
            return PassResult()
        return FailResult(error_message="Text is empty or whitespace-only")
