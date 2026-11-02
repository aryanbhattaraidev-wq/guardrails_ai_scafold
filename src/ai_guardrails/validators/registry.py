"""Explicit registry of the validators that configuration may refer to.

Config names are looked up here, never imported dynamically from YAML strings.
Each entry pairs a pydantic model (parameter validation) with a factory that
builds the Guardrails AI validator. Optional validator packages are imported
inside their factory, so a missing package fails at startup with an actionable
message instead of being silently omitted.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from guardrails import OnFailAction
from guardrails.validators import Validator
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ai_guardrails.core.exceptions import ConfigurationError, ValidatorUnavailableError
from ai_guardrails.validators.custom import MaxLength, NonEmpty, PiiRegex
from ai_guardrails.validators.custom.pii_regex import SUPPORTED_ENTITIES

ValidatorFactory = Callable[[Any, OnFailAction], Validator]


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


@dataclass(frozen=True, slots=True)
class ValidatorSpec:
    name: str
    params_model: type[BaseModel]
    factory: ValidatorFactory
    description: str = ""


class ValidatorRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ValidatorSpec] = {}

    def register(self, spec: ValidatorSpec) -> None:
        """Add a validator. Raises if the name is already taken."""
        if spec.name in self._specs:
            raise ConfigurationError(f"Validator '{spec.name}' is already registered")
        self._specs[spec.name] = spec

    def names(self) -> list[str]:
        return sorted(self._specs)

    def get(self, name: str) -> ValidatorSpec:
        try:
            return self._specs[name]
        except KeyError:
            raise ValidatorUnavailableError(
                f"Unknown validator '{name}'. Registered validators: {', '.join(self.names())}"
            ) from None

    def build(self, name: str, params: Mapping[str, Any], on_fail: OnFailAction) -> Validator:
        """Validate ``params`` then construct the Guardrails AI validator."""
        spec = self.get(name)
        try:
            parsed = spec.params_model.model_validate(dict(params))
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(p) for p in e['loc']) or '<params>'}: {e['msg']}"
                for e in exc.errors(include_input=False, include_url=False)
            )
            raise ConfigurationError(f"Invalid params for validator '{name}': {details}") from None
        return spec.factory(parsed, on_fail)


# --- parameter models -------------------------------------------------------


class _NoParams(_Params):
    pass


class _MaxLengthParams(_Params):
    max_characters: int = Field(gt=0)


class _PiiParams(_Params):
    entities: list[str] = Field(default_factory=lambda: list(SUPPORTED_ENTITIES), min_length=1)

    @field_validator("entities")
    @classmethod
    def _known(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - set(SUPPORTED_ENTITIES))
        if unknown:
            raise ValueError(
                f"unsupported entities {unknown}; supported: {list(SUPPORTED_ENTITIES)}"
            )
        return value


class _BanListParams(_Params):
    banned_words: list[str] = Field(min_length=1)
    # 0 = exact (case- and whitespace-insensitive) match. Higher values allow
    # fuzzy matches and produce more false positives.
    max_l_dist: int = Field(default=0, ge=0, le=3)


# --- factories --------------------------------------------------------------


def _non_empty(_: _NoParams, on_fail: OnFailAction) -> Validator:
    return NonEmpty(on_fail=on_fail)


def _max_length(params: _MaxLengthParams, on_fail: OnFailAction) -> Validator:
    return MaxLength(max_characters=params.max_characters, on_fail=on_fail)


def _pii_regex(params: _PiiParams, on_fail: OnFailAction) -> Validator:
    return PiiRegex(entities=params.entities, on_fail=on_fail)


def _ban_list(params: _BanListParams, on_fail: OnFailAction) -> Validator:
    try:
        from guardrails_ai.ban_list import BanList
    except ImportError as exc:
        raise ValidatorUnavailableError(
            "Validator 'ban_list' needs the 'guardrails-ai-ban-list' package; "
            "install it with: uv add guardrails-ai-ban-list"
        ) from exc
    return BanList(
        banned_words=params.banned_words,  # type: ignore[arg-type]  # upstream hint is wrong
        max_l_dist=params.max_l_dist,
        on_fail=on_fail,  # type: ignore[arg-type]  # upstream hint is too narrow
    )


def default_registry() -> ValidatorRegistry:
    """A registry containing every validator this project ships support for."""
    registry = ValidatorRegistry()
    registry.register(ValidatorSpec("non_empty", _NoParams, _non_empty, "Reject blank text"))
    registry.register(
        ValidatorSpec("input_length", _MaxLengthParams, _max_length, "Maximum characters")
    )
    registry.register(
        ValidatorSpec("output_length", _MaxLengthParams, _max_length, "Maximum characters")
    )
    registry.register(
        ValidatorSpec("pii_regex", _PiiParams, _pii_regex, "Basic pattern-based PII redaction")
    )
    registry.register(
        ValidatorSpec(
            "ban_list", _BanListParams, _ban_list, "Banned phrases (guardrails-ai-ban-list)"
        )
    )
    return registry
