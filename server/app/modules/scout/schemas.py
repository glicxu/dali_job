from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.scout.catalog import is_safe_current_path


ScoutStatus = Literal["answered", "navigate", "needs_context", "unsupported"]


class AskScoutPageContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_id: int | None = Field(default=None, gt=0)
    job_id: int | None = Field(default=None, gt=0)
    interview_id: int | None = Field(default=None, gt=0)
    resume_profile_id: int | None = Field(default=None, gt=0)


class AskScoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=3, max_length=1000)
    current_path: str | None = Field(default=None, max_length=255)
    page_context: AskScoutPageContext = Field(default_factory=AskScoutPageContext)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Question must contain at least 3 characters.")
        return value

    @field_validator("current_path")
    @classmethod
    def validate_current_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not is_safe_current_path(value):
            raise ValueError("current_path must be a known local DaliJob path.")
        return value


class ScoutModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ScoutStatus
    answer: str = Field(..., min_length=1, max_length=1500)
    action_id: str | None = None
    action_parameters: dict[str, Any] = Field(default_factory=dict)
    alternative_action_ids: list[str] = Field(default_factory=list, max_length=2)
    limitations: list[str] = Field(default_factory=list, max_length=3)
    confidence: Literal["low", "medium", "high"]


class ScoutAction(BaseModel):
    action_id: str
    label: str
    href: str


class AskScoutResult(BaseModel):
    status: ScoutStatus
    answer: str
    primary_action: ScoutAction | None = None
    alternative_actions: list[ScoutAction] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

