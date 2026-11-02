"""Resolve (profile, stage) to a ready-to-run list of checks."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ai_guardrails.config.schema import OnFail, Settings, ValidatorConfig
from ai_guardrails.core.exceptions import UnknownProfileError
from ai_guardrails.core.protocols import Checker
from ai_guardrails.core.types import ValidationStage

CheckerFactory = Callable[[ValidatorConfig], Checker]


@dataclass(frozen=True, slots=True)
class PlannedStep:
    checker: Checker
    on_fail: OnFail
    critical: bool

    @property
    def validator_id(self) -> str:
        return self.checker.validator_id


@dataclass(frozen=True, slots=True)
class StagePlan:
    profile: str
    stage: ValidationStage
    enabled: bool
    steps: tuple[PlannedStep, ...]


class PolicyResolver:
    """Builds every plan eagerly so misconfiguration fails at startup."""

    def __init__(
        self, plans: Mapping[tuple[str, ValidationStage], StagePlan], default: str
    ) -> None:
        self._plans = dict(plans)
        self._default = default

    @classmethod
    def from_settings(cls, settings: Settings, make_checker: CheckerFactory) -> PolicyResolver:
        plans: dict[tuple[str, ValidationStage], StagePlan] = {}
        for profile_name, profile in settings.profiles.items():
            for stage in ValidationStage:
                policy = getattr(profile, stage.value)
                steps = tuple(
                    PlannedStep(make_checker(v), v.on_fail, v.critical)
                    for v in policy.validators
                    if policy.enabled and v.enabled
                )
                plans[(profile_name, stage)] = StagePlan(profile_name, stage, policy.enabled, steps)
        return cls(plans, settings.runtime.default_profile)

    @property
    def profile_names(self) -> list[str]:
        return sorted({profile for profile, _ in self._plans})

    def resolve(self, profile: str | None, stage: ValidationStage) -> StagePlan:
        name = profile or self._default
        try:
            return self._plans[(name, stage)]
        except KeyError:
            raise UnknownProfileError(
                f"Unknown profile '{name}'. Known profiles: {', '.join(self.profile_names)}"
            ) from None
