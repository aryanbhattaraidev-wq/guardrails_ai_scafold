"""Translate a Guardrails AI ``ValidationOutcome`` into a project ``CheckOutcome``.

Observed behaviour of guardrails-ai 0.11 that this mapping relies on:

* A validator that finds a violation always leaves a summary with
  ``validator_status == "fail"``.
* With ``OnFailAction.NOOP`` the outcome has ``validation_passed=False`` and the
  original text in ``validated_output``.
* With ``OnFailAction.FIX`` and a ``fix_value``, ``validation_passed=True`` and
  ``validated_output`` holds the fix. Without a ``fix_value`` the outcome has
  ``validation_passed=False`` and ``validated_output=None``.
"""

from __future__ import annotations

from typing import Any

from ai_guardrails.core.types import CheckOutcome


def map_outcome(validator_id: str, original: str, outcome: Any) -> CheckOutcome:
    """Return ``passed`` if no violation was reported, otherwise the failure.

    ``fixed_value`` is set only when the engine produced a different, non-empty
    string *and* considers the fixed result valid; anything else is not a
    trustworthy correction.
    """
    summaries = getattr(outcome, "validation_summaries", None) or []
    reported_violation = any(
        str(getattr(s, "validator_status", "")).lower().endswith("fail") for s in summaries
    )
    if outcome.validation_passed and not reported_violation:
        return CheckOutcome(validator_id=validator_id, passed=True)

    fixed = outcome.validated_output
    trustworthy = (
        outcome.validation_passed
        and isinstance(fixed, str)
        and fixed != original
        and fixed.strip() != ""
    )
    return CheckOutcome(
        validator_id=validator_id,
        passed=False,
        fixed_value=fixed if trustworthy else None,
    )
