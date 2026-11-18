from answer_evaluation import evaluate_answer


if __name__ == "__main__":
    database_result = {
        "status": "success",
        "columns": ["city", "total_revenue"],
        "rows": [["Delhi", 190000.0]],
        "row_count": 1,
        "execution_time": 0.001,
        "error": None,
    }

    question = "Which city generated the highest revenue?"

    good_answer = "Delhi generated the highest revenue with a total of 190000."
    bad_answer = "Delhi generated the highest revenue with a total of 500000."

    good = evaluate_answer(
        question,
        good_answer,
        database_result,
    )

    bad = evaluate_answer(
        question,
        bad_answer,
        database_result,
    )

    print("\nAnswer evaluation:")
    print(f"Good answer: {good.model_dump()}")
    print(f"Bad answer:  {bad.model_dump()}")
