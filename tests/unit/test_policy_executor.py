"""Policy semantics, tested with fake checkers (no Guardrails AI involved)."""

import asyncio

import pytest

from ai_guardrails.config.schema import OnFail, RuntimeConfig
from ai_guardrails.core.exceptions import GuardrailsExecutionError
from ai_guardrails.core.types import CheckOutcome, ReasonCode, ValidationStage, ValidationStatus
from ai_guardrails.policies import PlannedStep, PolicyExecutor, StagePlan


class FakeChecker:
    def __init__(self, validator_id, *, passed=True, fixed=None, raises=None, delay=0.0):
        self.validator_id = validator_id
        self._passed, self._fixed, self._raises, self._delay = passed, fixed, raises, delay
        self.seen: list[str] = []

    async def check(self, text):
        self.seen.append(text)
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._raises:
            raise self._raises
        return CheckOutcome(self.validator_id, self._passed, self._fixed)


def plan(*steps, enabled=True):
    return StagePlan("p", ValidationStage.INPUT, enabled, tuple(steps))


def step(checker, on_fail=OnFail.BLOCK, critical=True):
    return PlannedStep(checker, on_fail, critical)


async def run(p, text="hello", **runtime):
    return await PolicyExecutor(RuntimeConfig(**runtime)).run(p, text, request_id="r1", metadata={})


async def test_all_pass():
    result = await run(plan(step(FakeChecker("a")), step(FakeChecker("b"))))
    assert result.status is ValidationStatus.PASSED
    assert result.content == "hello" and result.is_allowed and result.request_id == "r1"


async def test_block_stops_pipeline_and_withholds_content():
    later = FakeChecker("later")
    result = await run(plan(step(FakeChecker("bad", passed=False)), step(later)))
    assert result.status is ValidationStatus.BLOCKED
    assert result.failed_validators == ("bad",)
    assert result.reason_code is ReasonCode.POLICY_VIOLATION
    assert result.content is None and not result.is_allowed
    assert later.seen == []


async def test_redact_continues_with_fixed_text():
    later = FakeChecker("later")
    first = FakeChecker("pii", passed=False, fixed="<X>")
    result = await run(plan(step(first, OnFail.REDACT), step(later)))
    assert result.status is ValidationStatus.MODIFIED
    assert result.content == "<X>" and result.is_allowed
    assert later.seen == ["<X>"]
    assert result.diagnostics["redacted_by"] == ["pii"]


@pytest.mark.parametrize("action", [OnFail.REDACT, OnFail.FIX])
async def test_fix_without_trustworthy_value_blocks(action):
    result = await run(plan(step(FakeChecker("v", passed=False, fixed=None), action)))
    assert result.status is ValidationStatus.BLOCKED
    assert result.diagnostics["no_trustworthy_fix"] is True


async def test_log_and_continue_records_violation():
    result = await run(
        plan(step(FakeChecker("soft", passed=False), OnFail.LOG_AND_CONTINUE, False))
    )
    assert result.status is ValidationStatus.PASSED
    assert result.diagnostics["logged_violations"] == ["soft"]


async def test_critical_crash_fails_closed():
    boom = GuardrailsExecutionError("validator 'v' raised RuntimeError")
    result = await run(plan(step(FakeChecker("v", raises=boom))))
    assert result.status is ValidationStatus.ERROR
    assert result.reason_code is ReasonCode.VALIDATOR_ERROR
    assert result.content is None and not result.is_allowed
    assert result.failed_validators == ("v",)


async def test_unexpected_exception_type_also_fails_closed():
    result = await run(plan(step(FakeChecker("v", raises=ValueError("jane@example.com")))))
    assert result.status is ValidationStatus.ERROR
    assert "jane@example.com" not in repr(result) + str(result.message)


async def test_timeout_fails_closed():
    result = await run(plan(step(FakeChecker("slow", delay=1.0))), validation_timeout_seconds=0.05)
    assert result.status is ValidationStatus.ERROR
    assert result.reason_code is ReasonCode.VALIDATOR_TIMEOUT


async def test_non_critical_crash_is_skipped_but_recorded():
    broken = FakeChecker("flaky", raises=GuardrailsExecutionError("x"))
    result = await run(plan(step(broken, critical=False), step(FakeChecker("b"))))
    assert result.status is ValidationStatus.PASSED
    assert result.diagnostics["skipped_validators"] == ["flaky"]


async def test_fail_open_only_when_explicitly_configured():
    broken = FakeChecker("v", raises=GuardrailsExecutionError("x"))
    result = await run(plan(step(broken)), fail_closed_on_validator_error=False)
    assert result.status is ValidationStatus.PASSED
    assert result.diagnostics["skipped_validators"] == ["v"]


async def test_disabled_stage_is_skipped_with_reason():
    result = await run(plan(enabled=False))
    assert result.status is ValidationStatus.SKIPPED
    assert result.reason_code is ReasonCode.STAGE_DISABLED
    assert result.is_allowed and result.content == "hello"


async def test_empty_enabled_stage_passes():
    assert (await run(plan())).status is ValidationStatus.PASSED


async def test_cancellation_propagates():
    task = asyncio.create_task(run(plan(step(FakeChecker("slow", delay=5)))))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_result_repr_hides_content():
    result = await run(plan(), text="my secret prompt")
    assert "my secret prompt" not in repr(result)
