from typing import Any
from pydantic import BaseModel, Field, field_validator


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=100)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question cannot be blank.")
        return value.strip()


class AskResponse(BaseModel):
    status: str
    question: str | None = None
    resolved_question: str | None = None
    session_id: str | None = None
    message: str | None = None
    stage: str | None = None
    intent: dict[str, Any] | None = None
    query_plan: dict[str, Any] | None = None
    sql: str | None = None
    execution: dict[str, Any] | None = None
    answer: str | None = None
    answer_evaluation: dict[str, Any] | None = None
    visualization: dict[str, Any] | None = None
    analysis_trace: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    database_profile: dict[str, Any] | None = None

class DatabaseConnectRequest(BaseModel):
    """Connection URL supplied by the local user; the API never echoes it."""
    connection_url: str = Field(..., min_length=8, max_length=2000)

    @field_validator("connection_url")
    @classmethod
    def connection_url_must_be_nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Connection URL cannot be blank.")
        return value
