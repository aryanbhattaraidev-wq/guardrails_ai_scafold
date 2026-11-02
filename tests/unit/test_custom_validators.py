import pytest
from guardrails.validators import FailResult, PassResult

from ai_guardrails.validators.custom import MaxLength, NonEmpty, PiiRegex


def run(validator, text):
    return validator._validate(text, {})


@pytest.mark.parametrize("text", ["", " ", "\n\t  "])
def test_non_empty_rejects_blank(text):
    assert isinstance(run(NonEmpty(), text), FailResult)


def test_non_empty_accepts_text():
    assert isinstance(run(NonEmpty(), " hi "), PassResult)


def test_max_length_boundaries():
    validator = MaxLength(max_characters=5)
    assert isinstance(run(validator, ""), PassResult)
    assert isinstance(run(validator, "12345"), PassResult)
    result = run(validator, "123456")
    assert isinstance(result, FailResult)
    assert result.fix_value is None  # never truncate silently


def test_max_length_message_never_contains_text():
    result = run(MaxLength(max_characters=3), "SECRET-TEXT")
    assert "SECRET" not in result.error_message


def test_max_length_rejects_invalid_config():
    with pytest.raises(ValueError):
        MaxLength(max_characters=0)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mail me at jane.doe@example.com now", "mail me at <EMAIL_ADDRESS> now"),
        ("call (415) 555-0132 today", "call <PHONE_NUMBER> today"),
        ("call +1 415-555-0132", "call <PHONE_NUMBER>"),
        ("ssn 123-45-6789 ok", "ssn <US_SSN> ok"),
        ("card 4111 1111 1111 1111 ok", "card <CREDIT_CARD> ok"),
    ],
)
def test_pii_regex_redacts(text, expected):
    result = run(PiiRegex(), text)
    assert isinstance(result, FailResult)
    assert result.fix_value == expected


@pytest.mark.parametrize(
    "text",
    [
        "no personal data here",
        "order number 1234567890123456",  # 16 digits but fails Luhn
        "version 1.2.3 released 2024-01-02",
    ],
)
def test_pii_regex_passes_clean_text(text):
    assert isinstance(run(PiiRegex(), text), PassResult)


def test_pii_regex_only_checks_selected_entities():
    validator = PiiRegex(entities=["EMAIL_ADDRESS"])
    assert isinstance(run(validator, "call (415) 555-0132"), PassResult)
    assert isinstance(run(validator, "a@b.co"), FailResult)


def test_pii_regex_message_lists_types_not_values():
    result = run(PiiRegex(), "a@b.co")
    assert "EMAIL_ADDRESS" in result.error_message
    assert "a@b.co" not in result.error_message


def test_pii_regex_rejects_unknown_entity():
    with pytest.raises(ValueError):
        PiiRegex(entities=["PASSPORT"])
