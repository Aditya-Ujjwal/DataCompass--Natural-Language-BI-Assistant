import sys
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "backend"),
)

from answer_evaluation import (
    AnswerEvaluation,
    basic_groundedness_check,
    evaluate_answer,
)


def make_result():
    return {
        "status": "success",
        "columns": ["city", "total_revenue"],
        "rows": [["Delhi", 190000.0]],
        "row_count": 1,
        "execution_time": 0.001,
        "error": None,
    }


def test_answer_evaluation_model():
    result = AnswerEvaluation(
        grounded=True,
        reason="Supported by the result.",
    )

    assert result.grounded is True


def test_supported_answer_is_grounded():
    result = basic_groundedness_check(
        "Delhi generated 190000.",
        make_result(),
    )

    assert result.grounded is True


def test_unsupported_number_is_not_grounded():
    result = basic_groundedness_check(
        "Delhi generated 500000.",
        make_result(),
    )

    assert result.grounded is False
    assert "numeric" in result.reason.lower()


def test_empty_answer_is_not_grounded():
    result = basic_groundedness_check(
        "",
        make_result(),
    )

    assert result.grounded is False


def test_failed_execution_is_not_grounded():
    result = basic_groundedness_check(
        "Delhi generated 190000.",
        {
            "status": "error",
            "rows": [],
        },
    )

    assert result.grounded is False


def test_empty_database_result_without_numbers_can_be_grounded():
    result = basic_groundedness_check(
        "No matching records were found.",
        {
            "status": "success",
            "rows": [],
        },
    )

    assert result.grounded is True


def test_empty_database_result_with_number_is_not_grounded():
    result = basic_groundedness_check(
        "Revenue was 190000.",
        {
            "status": "success",
            "rows": [],
        },
    )

    assert result.grounded is False


def test_evaluate_answer_uses_basic_check_by_default():
    result = evaluate_answer(
        "Which city generated the highest revenue?",
        "Delhi generated 190000.",
        make_result(),
    )

    assert result.grounded is True


def test_formatted_numeric_answer_is_grounded():
    result = basic_groundedness_check(
        "Delhi generated 190,000.0.",
        make_result(),
    )

    assert result.grounded is True
