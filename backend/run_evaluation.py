from pathlib import Path
import json

from evaluation import evaluate_benchmark


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[1]
    benchmark_path = project_root / "evaluation" / "benchmark.json"

    report = evaluate_benchmark(benchmark_path)

    print("\nEvaluation Report")
    print("=" * 50)
    print(f"Total cases: {report['total_cases']}")
    print(f"Correct cases: {report['correct_cases']}")
    print(f"Accuracy: {report['accuracy']:.2%}")

    print("\nCase results:")
    for result in report["results"]:
        print(
            f"  Case {result['id']}: "
            f"{result['status']} | "
            f"correct={result['correct']}"
        )

    report_path = project_root / "evaluation" / "evaluation_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"\nDetailed report written to: {report_path}")
