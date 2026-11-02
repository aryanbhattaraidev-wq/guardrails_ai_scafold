"""Pydantic models describing the YAML policy configuration.

Every model rejects unknown keys so a misspelled security setting fails loudly
instead of being silently ignored. Models are frozen: settings are resolved
once at startup and then shared read-only.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OnFail(StrEnum):
    """What the project does when a validator reports a violation."""

    BLOCK = "block"
    REDACT = "redact"
    FIX = "fix"
    LOG_AND_CONTINUE = "log_and_continue"


class AppConfig(_Strict):
    name: str = "ai-guardrails"
    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class RuntimeConfig(_Strict):
    default_profile: str = "default"
    validation_timeout_seconds: float = Field(default=5.0, gt=0)
    fail_closed_on_validator_error: bool = True
    # Behaviour for non-text payloads (images, bytes, ...). We never claim to
    # have inspected content we could not read.
    on_unsupported_content: Literal["block", "skip"] = "block"
    log_content: bool = False


class ApiConfig(_Strict):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    max_text_chars: int = Field(default=100_000, gt=0)
    auth_enabled: bool = False
    # Name of the environment variable holding the API key. The key itself must
    # never live in YAML.
    api_key_env: str = "AI_GUARDRAILS_API_KEY"


class ValidatorConfig(_Strict):
    name: str = Field(min_length=1)
    enabled: bool = True
    on_fail: OnFail = OnFail.BLOCK
    # Critical validators fail closed when they crash or time out (subject to
    # runtime.fail_closed_on_validator_error). Non-critical ones are logged and
    # skipped, which must be an explicit choice.
    critical: bool = True
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _log_and_continue_needs_non_critical(self) -> ValidatorConfig:
        if self.on_fail is OnFail.LOG_AND_CONTINUE and self.critical:
            raise ValueError(
                f"validator '{self.name}': on_fail=log_and_continue requires "
                "critical: false (set it explicitly)"
            )
        return self


class StagePolicy(_Strict):
    enabled: bool = False
    validators: list[ValidatorConfig] = Field(default_factory=list)


class ProfileConfig(_Strict):
    """A named collection of stage policies. Missing stages are disabled."""

    input: StagePolicy = Field(default_factory=StagePolicy)
    output: StagePolicy = Field(default_factory=StagePolicy)
    retrieval: StagePolicy = Field(default_factory=StagePolicy)
    tool_input: StagePolicy = Field(default_factory=StagePolicy)
    tool_output: StagePolicy = Field(default_factory=StagePolicy)


class Settings(_Strict):
    """Root configuration object."""

    app: AppConfig = Field(default_factory=AppConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    profiles: dict[str, ProfileConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def _cross_field_checks(self) -> Settings:
        if self.runtime.default_profile not in self.profiles:
            raise ValueError(
                f"runtime.default_profile '{self.runtime.default_profile}' "
                "is not defined under profiles"
            )
        if self.app.environment == "production" and self.runtime.log_content:
            raise ValueError("runtime.log_content must be false in production")
        if self.api.host not in LOOPBACK_HOSTS and not self.api.auth_enabled:
            raise ValueError(
                "api.auth_enabled must be true when api.host is not a loopback address"
            )
        return self
