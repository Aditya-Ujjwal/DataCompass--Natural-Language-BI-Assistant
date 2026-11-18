import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "backend"),
)

from api_models import AskRequest, AskResponse


def test_ask_request():
    request = AskRequest(
        question="Which city generated the highest revenue?"
    )

    assert request.question.startswith("Which city")


def test_ask_response():
    response = AskResponse(
        status="success",
        answer="Delhi generated the highest revenue.",
    )

    assert response.status == "success"
    assert response.answer.startswith("Delhi")


def test_ask_request_rejects_empty_question():
    with pytest.raises(ValidationError):
        AskRequest(question="")


def test_ask_response_allows_error_information():
    response = AskResponse(
        status="error",
        stage="sql_execution",
        message="Database error",
    )

    assert response.status == "error"
    assert response.stage == "sql_execution"
    assert response.message == "Database error"
