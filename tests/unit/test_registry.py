import pytest
from guardrails import OnFailAction

from ai_guardrails.core.exceptions import ConfigurationError, ValidatorUnavailableError
from ai_guardrails.validators import ValidatorSpec, default_registry
from ai_guardrails.validators.custom import MaxLength, NonEmpty, PiiRegex
from ai_guardrails.validators.registry import _NoParams

NOOP = OnFailAction.NOOP


def test_known_validators_are_registered():
    assert {"non_empty", "input_length", "output_length", "pii_regex", "ban_list"} <= set(
        default_registry().names()
    )


def test_unknown_validator_lists_alternatives():
    with pytest.raises(ValidatorUnavailableError, match="non_empty"):
        default_registry().build("typo_validator", {}, NOOP)


def test_params_are_validated_before_construction():
    registry = default_registry()
    with pytest.raises(ConfigurationError, match="max_characters"):
        registry.build("input_length", {}, NOOP)
    with pytest.raises(ConfigurationError, match="max_characters"):
        registry.build("input_length", {"max_characters": 0}, NOOP)
    with pytest.raises(ConfigurationError, match="max_chars"):
        registry.build("input_length", {"max_characters": 5, "max_chars": 3}, NOOP)
    with pytest.raises(ConfigurationError, match="entities"):
        registry.build("pii_regex", {"entities": ["PASSPORT"]}, NOOP)


def test_builds_expected_classes():
    registry = default_registry()
    assert isinstance(registry.build("non_empty", {}, NOOP), NonEmpty)
    assert isinstance(registry.build("output_length", {"max_characters": 5}, NOOP), MaxLength)
    assert isinstance(registry.build("pii_regex", {}, NOOP), PiiRegex)


def test_duplicate_registration_is_rejected():
    registry = default_registry()
    with pytest.raises(ConfigurationError, match="already registered"):
        registry.register(ValidatorSpec("non_empty", _NoParams, lambda p, f: NonEmpty(on_fail=f)))


def test_missing_optional_package_fails_with_install_hint(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("guardrails_ai"):
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ValidatorUnavailableError, match="uv add guardrails-ai-ban-list"):
        default_registry().build("ban_list", {"banned_words": ["x"]}, NOOP)
