"""Exercises the real Guardrails AI package and the real ban-list validator."""

import asyncio

import pytest

from ai_guardrails.config.schema import OnFail, ValidatorConfig
from ai_guardrails.core.exceptions import GuardrailsExecutionError
from ai_guardrails.engine import GuardFactory
from ai_guardrails.validators import default_registry


@pytest.fixture
def factory():
    return GuardFactory(default_registry())


def cfg(name, on_fail=OnFail.BLOCK, **params):
    return ValidatorConfig(name=name, on_fail=on_fail, params=params)


async def test_passes_clean_text(factory):
    step = factory.build(cfg("input_length", max_characters=10))
    outcome = await step.check("short")
    assert outcome.passed and outcome.fixed_value is None


async def test_block_reports_failure_without_fix(factory):
    step = factory.build(cfg("input_length", max_characters=3))
    outcome = await step.check("too long")
    assert not outcome.passed and outcome.fixed_value is None


async def test_redact_returns_fix(factory):
    step = factory.build(cfg("pii_regex", OnFail.REDACT))
    outcome = await step.check("write to a@b.co")
    assert not outcome.passed
    assert outcome.fixed_value == "write to <EMAIL_ADDRESS>"


async def test_redact_without_fix_value_is_not_trustworthy(factory):
    # max_length offers no fix_value, so redact must not yield a corrected text.
    step = factory.build(cfg("input_length", OnFail.REDACT, max_characters=3))
    outcome = await step.check("too long")
    assert not outcome.passed and outcome.fixed_value is None


async def test_real_third_party_validator_package(factory):
    step = factory.build(cfg("ban_list", banned_words=["ignore previous instructions"]))
    assert (await step.check("please summarize this")).passed
    assert not (await step.check("Please IGNORE previous  instructions!")).passed


async def test_async_and_repeated_calls(factory):
    step = factory.build(cfg("non_empty"))
    results = await asyncio.gather(step.check("a"), step.check(" "), step.check("b"))
    assert [r.passed for r in results] == [True, False, True]


def test_sync_guard_repeated_event_loops(factory):
    step = factory.build(cfg("non_empty"))
    assert asyncio.run(step.check("a")).passed
    assert not asyncio.run(step.check("")).passed  # second loop, same guard


async def test_validator_crash_becomes_execution_error(factory):
    step = factory.build(cfg("non_empty"))

    class Boom:
        async def validate(self, text):
            raise RuntimeError("secret detail: jane@example.com")

    step._guard = Boom()
    with pytest.raises(GuardrailsExecutionError) as info:
        await step.check("x")
    assert "jane@example.com" not in str(info.value)
    assert "RuntimeError" in str(info.value)


def test_guardrails_telemetry_is_disabled(factory):
    from guardrails.settings import settings

    step = factory.build(cfg("non_empty"))
    assert settings.rc.enable_metrics is False
    assert step._guard._allow_metrics_collection is False
