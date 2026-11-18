from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass
class RequestMetrics:
    """Simple metrics for one BI assistant request."""

    request_id: str
    started_at: str
    model: str | None = None
    provider: str | None = None
    total_time: float | None = None
    execution_time: float | None = None
    retries: int = 0
    status: str = "started"
    result_rows: int = 0
    evaluation_score: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def start_request(
    model: str | None = None,
    provider: str | None = None,
) -> RequestMetrics:
    """Create metrics for a new request."""
    return RequestMetrics(
        request_id=str(uuid4()),
        started_at=datetime.now(timezone.utc).isoformat(),
        model=model,
        provider=provider,
    )


def finish_request(
    metrics: RequestMetrics,
    total_time: float,
    status: str,
    result_rows: int = 0,
    retries: int = 0,
    evaluation_score: float | None = None,
    error: str | None = None,
) -> RequestMetrics:
    """Complete the metrics object with request outcomes."""
    metrics.total_time = total_time
    metrics.status = status
    metrics.result_rows = result_rows
    metrics.retries = retries
    metrics.evaluation_score = evaluation_score
    metrics.error = error

    return metrics


def record_execution_time(
    metrics: RequestMetrics,
    execution_time: float | None,
) -> RequestMetrics:
    """Record database execution time."""
    metrics.execution_time = execution_time
    return metrics


def print_metrics(metrics: RequestMetrics) -> None:
    """Print a readable metrics summary."""
    print("\nRequest Metrics")
    print("=" * 50)

    for key, value in metrics.to_dict().items():
        print(f"{key}: {value}")
