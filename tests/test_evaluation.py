import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "backend"),
)

from evaluation import (
    EvaluationCase,
    extract_result_value,
    load_benchmark,
)


def test_extract_city_and_value():
    result = {
        "rows": [["Delhi", 190000.0]],
    }

    city, value = extract_result_value(result)

    assert city == "Delhi"
    assert value == 190000.0


def test_extract_single_value():
    result = {
        "rows": [[425000.0]],
    }

    city, value = extract_result_value(result)

    assert city is None
    assert value == 425000.0


def test_extract_empty_result():
    city, value = extract_result_value({"rows": []})

    assert city is None
    assert value is None


def test_load_benchmark():
    root = Path(__file__).resolve().parents[1]
    cases = load_benchmark(root / "evaluation" / "benchmark.json")

    assert len(cases) == 3
    assert isinstance(cases[0], EvaluationCase)
    assert cases[0].expected_city == "Delhi"
    assert cases[2].expected_value == 425000.0


def test_evaluation_case_structure():
    case = EvaluationCase(
        id=1,
        question="Which city generated the highest revenue?",
        expected_city="Delhi",
        expected_value=190000.0,
    )

    assert case.id == 1
    assert case.expected_city == "Delhi"
