"""Reject text longer than a configured number of characters.

Registered once and exposed under two config names (``input_length`` and
``output_length``) so profiles read naturally.
"""

from __future__ import annotations

from typing import Any

from guardrails.validators import FailResult, PassResult, Validator, register_validator


@register_validator(name="ai_guardrails/max_length", data_type="string")
class MaxLength(Validator):
    """Fails when ``len(text) > max_characters``.

    No ``fix_value`` is offered: silently truncating a prompt or answer would
    change its meaning, so an over-long text is a violation, not a repair.
    """

    def __init__(self, max_characters: int, on_fail: Any = None) -> None:
        if max_characters < 1:
            raise ValueError("max_characters must be at least 1")
        super().__init__(on_fail=on_fail, max_characters=max_characters)
        self._max_characters = max_characters

    def _validate(self, value: Any, metadata: dict[str, Any]) -> PassResult | FailResult:
        length = len(value)
        if length <= self._max_characters:
            return PassResult()
        # Lengths only: the message must never contain the text itself.
        return FailResult(
            error_message=f"Text has {length} characters; the maximum is {self._max_characters}"
        )
