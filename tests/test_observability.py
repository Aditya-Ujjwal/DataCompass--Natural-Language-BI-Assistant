import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "backend"),
)

from observability import (
    RequestMetrics,
    finish_request,
    record_execution_time,
    start_request,
)


def test_start_request_creates_request_id():
    metrics = start_request()

    assert metrics.request_id
    assert metrics.status == "started"


def test_start_request_stores_model_and_provider():
    metrics = start_request(
        model="gemini-3.6-flash",
        provider="Google Gemini",
    )

    assert metrics.model == "gemini-3.6-flash"
    assert metrics.provider == "Google Gemini"


def test_record_execution_time():
    metrics = start_request()

    record_execution_time(metrics, 0.123)

    assert metrics.execution_time == 0.123


def test_finish_request_records_outcome():
    metrics = start_request()

    result = finish_request(
        metrics,
        total_time=0.5,
        status="success",
        result_rows=3,
        retries=1,
        evaluation_score=0.9,
    )

    assert result.total_time == 0.5
    assert result.status == "success"
    assert result.result_rows == 3
    assert result.retries == 1
    assert result.evaluation_score == 0.9


def test_metrics_to_dict():
    metrics = RequestMetrics(
        request_id="test-id",
        started_at="2026-09-03T00:00:00+00:00",
    )

    data = metrics.to_dict()

    assert data["request_id"] == "test-id"
    assert data["status"] == "started"
