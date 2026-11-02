from types import SimpleNamespace

from ai_guardrails.engine.result_mapper import map_outcome


def outcome(passed, output, statuses=()):
    return SimpleNamespace(
        validation_passed=passed,
        validated_output=output,
        validation_summaries=[SimpleNamespace(validator_status=s) for s in statuses],
    )


def test_pass():
    result = map_outcome("v", "hello", outcome(True, "hello"))
    assert result.passed and result.fixed_value is None


def test_noop_failure_has_no_fix():
    result = map_outcome("v", "hello", outcome(False, "hello", ["fail"]))
    assert not result.passed and result.fixed_value is None


def test_fix_applied_is_trustworthy():
    result = map_outcome("v", "a@b.co", outcome(True, "<EMAIL>", ["fail"]))
    assert not result.passed and result.fixed_value == "<EMAIL>"


def test_fix_requested_but_missing_is_not_trustworthy():
    result = map_outcome("v", "hello", outcome(False, None, ["fail"]))
    assert not result.passed and result.fixed_value is None


def test_fix_identical_to_original_is_not_trustworthy():
    result = map_outcome("v", "hello", outcome(True, "hello", ["fail"]))
    assert not result.passed and result.fixed_value is None


def test_empty_fix_is_not_trustworthy():
    result = map_outcome("v", "hello", outcome(True, "   ", ["fail"]))
    assert result.fixed_value is None


def test_failure_summary_wins_even_if_engine_says_passed():
    result = map_outcome("v", "hello", outcome(True, "hello", ["fail"]))
    assert not result.passed
