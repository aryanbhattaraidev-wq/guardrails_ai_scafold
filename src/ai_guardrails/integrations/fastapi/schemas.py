"""HTTP request/response models. Deliberately small and free of internals."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ai_guardrails.core.types import ValidationResult


class ValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    profile: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    # Untrusted, echoed back only. Never used to make decisions.
    metadata: dict[str, str] = Field(default_factory=dict, max_length=20)


class ValidateResponse(BaseModel):
    status: str
    is_allowed: bool
    content: str | None
    stage: str
    policy: str
    failed_validators: list[str]
    reason_code: str | None
    message: str | None
    request_id: str
    duration_ms: float

    @classmethod
    def from_result(cls, result: ValidationResult) -> ValidateResponse:
        return cls(
            status=result.status.value,
            is_allowed=result.is_allowed,
            content=result.content,
            stage=result.stage.value,
            policy=result.profile,
            failed_validators=list(result.failed_validators),
            reason_code=result.reason_code.value if result.reason_code else None,
            message=result.message,
            request_id=result.request_id,
            duration_ms=round(result.duration_ms, 3),
        )


class HealthResponse(BaseModel):
    status: str
    profiles: list[str]
