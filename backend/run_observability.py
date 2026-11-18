import time

from observability import (
    finish_request,
    print_metrics,
    record_execution_time,
    start_request,
)


if __name__ == "__main__":
    metrics = start_request(
        model="gemini-3.6-flash",
        provider="Google Gemini",
    )

    started = time.perf_counter()

    # Simulate a database call for demonstration.
    time.sleep(0.01)
    record_execution_time(metrics, 0.0021)

    total_time = time.perf_counter() - started

    finish_request(
        metrics,
        total_time=total_time,
        status="success",
        result_rows=1,
        retries=0,
        evaluation_score=1.0,
    )

    print_metrics(metrics)
