from analysis_trace import build_analysis_trace, print_analysis_trace
from assistant import run_assistant


if __name__ == "__main__":
    question = "Which city generated the highest revenue?"
    result = run_assistant(question)

    trace = build_analysis_trace(
        question=question,
        intent=result.get("intent"),
        query_plan=result.get("query_plan"),
        sql=result.get("sql"),
        validation=result.get("validation"),
        execution=result.get("execution"),
        answer=result.get("answer"),
        visualization=result.get("visualization"),
    )

    print_analysis_trace(trace)
