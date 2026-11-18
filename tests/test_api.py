import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "backend"),
)

from app import app


client = TestClient(app)


def test_ask_endpoint_success():
    fake_result = {
        "status": "success",
        "question": "Which city generated the highest revenue?",
        "intent": {"intent": "ranking"},
        "query_plan": {"table": "sales"},
        "sql": "SELECT city FROM sales;",
        "execution": {
            "status": "success",
            "row_count": 1,
        },
        "answer": "Delhi generated the highest revenue.",
        "answer_evaluation": {
            "grounded": True,
        },
        "visualization": {
            "chart_type": "kpi",
        },
        "analysis_trace": {
            "question": "Which city generated the highest revenue?",
        },
        "metrics": {
            "status": "success",
        },
    }

    with patch("app.run_assistant", return_value=fake_result):
        response = client.post(
            "/ask",
            json={
                "question": "Which city generated the highest revenue?"
            },
        )

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "success"
    assert data["answer"] == "Delhi generated the highest revenue."
    assert data["visualization"]["chart_type"] == "kpi"


def test_ask_endpoint_rejects_empty_question():
    response = client.post(
        "/ask",
        json={"question": ""},
    )

    assert response.status_code == 422


def test_ask_endpoint_rejects_missing_question():
    response = client.post(
        "/ask",
        json={},
    )

    assert response.status_code == 422


def test_ask_endpoint_returns_blocked_result():
    fake_result = {
        "status": "blocked",
        "stage": "input_guardrail",
        "message": "Question is outside the BI scope.",
        "metrics": {
            "status": "blocked",
        },
    }

    with patch("app.run_assistant", return_value=fake_result):
        response = client.post(
            "/ask",
            json={"question": "Tell me a joke."},
        )

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "blocked"
    assert data["stage"] == "input_guardrail"
