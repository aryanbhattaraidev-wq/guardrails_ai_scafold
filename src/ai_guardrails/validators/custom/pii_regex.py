"""Basic pattern-based PII detection and redaction.

This is deliberately small and offline. It catches well-formatted emails, US-style
phone numbers, US SSNs, and Luhn-valid card numbers. It is NOT an ML detector: it
misses names, addresses, free-form identifiers, and non-US formats. For broader
coverage add a maintained detector package (see docs/adding_validators.md).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from guardrails.validators import FailResult, PassResult, Validator, register_validator

SUPPORTED_ENTITIES = ("EMAIL_ADDRESS", "PHONE_NUMBER", "US_SSN", "CREDIT_CARD")

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_PHONE = re.compile(r"(?<![\w+])(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?!\w)")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")

Redactor = Callable[[str], tuple[str, bool]]


def _luhn_ok(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        number = int(char)
        if index % 2 == 1:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def _redact_cards(text: str) -> tuple[str, bool]:
    found = False

    def replace(match: re.Match[str]) -> str:
        nonlocal found
        digits = re.sub(r"\D", "", match.group())
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            found = True
            return "<CREDIT_CARD>"
        return match.group()

    return _CARD.sub(replace, text), found


def _redact_with(pattern: re.Pattern[str], label: str) -> Redactor:
    def redact(text: str) -> tuple[str, bool]:
        new_text, count = pattern.subn(f"<{label}>", text)
        return new_text, count > 0

    return redact


# Order matters: longer digit runs first so a card is not mistaken for a phone.
_REDACTORS: dict[str, Redactor] = {
    "CREDIT_CARD": _redact_cards,
    "US_SSN": _redact_with(_SSN, "US_SSN"),
    "PHONE_NUMBER": _redact_with(_PHONE, "PHONE_NUMBER"),
    "EMAIL_ADDRESS": _redact_with(_EMAIL, "EMAIL_ADDRESS"),
}


@register_validator(name="ai_guardrails/pii_regex", data_type="string")
class PiiRegex(Validator):
    """Fails when configured PII patterns are found; the fix is a redacted copy."""

    def __init__(self, entities: list[str] | None = None, on_fail: Any = None) -> None:
        chosen = list(entities) if entities else list(SUPPORTED_ENTITIES)
        unknown = sorted(set(chosen) - set(SUPPORTED_ENTITIES))
        if unknown:
            raise ValueError(f"unsupported entities: {', '.join(unknown)}")
        super().__init__(on_fail=on_fail, entities=chosen)
        self._entities = set(chosen)

    def _validate(self, value: Any, metadata: dict[str, Any]) -> PassResult | FailResult:
        redacted = value
        detected: list[str] = []
        for entity, redactor in _REDACTORS.items():
            if entity not in self._entities:
                continue
            redacted, hit = redactor(redacted)
            if hit:
                detected.append(entity)
        if not detected:
            return PassResult()
        # Entity *types* only; never the matched values.
        return FailResult(
            error_message=f"Detected PII: {', '.join(detected)}",
            fix_value=redacted,
        )
