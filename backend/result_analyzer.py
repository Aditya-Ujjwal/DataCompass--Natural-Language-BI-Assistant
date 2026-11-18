from typing import Any
from pydantic import BaseModel
try:
    from google import genai
except ImportError:
    from types import SimpleNamespace
    genai = SimpleNamespace(Client=None)
from config import GEMINI_API_KEY, GEMINI_MODEL, USE_LLM_ANSWER


class AnalysisResult(BaseModel):
    answer: str


def _fmt(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}".rstrip("0").rstrip(".")
    return str(value)


def _humanize(value: str) -> str:
    """Make snake_case and CamelCase database names readable in answers."""
    import re
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value))
    value = value.replace("_", " ").replace("-", " ")
    return " ".join(part for part in value.split() if part).strip().lower()


def build_answer_prompt(question: str, query_result: dict[str, Any]) -> str:
    return f"""Answer the BI question using only this query result. Do not invent values.
Question: {question}
Columns: {query_result.get('columns')}
Rows: {query_result.get('rows')}
""".strip()


def _template_answer(question: str, query_result: dict[str, Any], query_plan: Any = None) -> str:
    rows = query_result.get("rows", [])
    columns = query_result.get("columns", [])
    if query_result.get("status") != "success":
        return "The database query did not complete successfully."
    if not rows:
        return "No matching records were found for the requested criteria."
    if query_plan is not None and getattr(query_plan, "metric_column", None) is None and getattr(query_plan, "aggregation", "") == "NONE":
        return f"Returned {len(rows)} rows from the dataset. The records are shown in the table below."
    if columns == ["total_revenue"] or (len(columns) == 1 and str(columns[0]).startswith("total_")):
        return f"{columns[0].replace('_', ' ').capitalize()} is {_fmt(rows[0][0])}."
    numeric_index = next((i for i in range(len(columns)) if all(isinstance(row[i], (int, float)) for row in rows if row[i] is not None)), None)
    category_index = next((i for i in range(len(columns)) if i != numeric_index and not str(columns[i]).startswith("total_")), None)
    if numeric_index is not None and category_index is not None:
        pairs = [(str(row[category_index]), row[numeric_index]) for row in rows]
        ranking_words = ("highest", "top", "lowest", "bottom", "most", "least")
        is_ranking = any(word in question.lower() for word in ranking_words)
        if len(pairs) == 1 and is_ranking:
            label, value = pairs[0]
            direction = "lowest" if any(w in question.lower() for w in ("lowest", "bottom", "least")) else "highest"
            metric_label = _humanize(columns[numeric_index].removeprefix("total_"))
            return f"{label} generated the {direction} {metric_label}, with a total of {_fmt(value)}."
        metric_label = _humanize(columns[numeric_index].removeprefix("total_"))
        dimension_label = _humanize(columns[category_index])
        summary_label = "Top results by" if is_ranking else metric_label.capitalize() + " by"
        return f"{summary_label} {dimension_label}: " + "; ".join(
            f"{label} — {_fmt(value)}" for label, value in pairs
        ) + "."
    if len(rows) == 1:
        return "The result is: " + ", ".join(f"{col}: {_fmt(val)}" for col, val in zip(columns, rows[0])) + "."
    return f"Found {len(rows)} rows. The returned records are shown in the table below."


def generate_answer(question: str, query_result: dict[str, Any], query_plan: Any = None) -> AnalysisResult:
    """Use deterministic phrasing for database-backed answers; optional LLM enrichment."""
    chart_type = getattr(query_plan, "chart_type", None) if query_plan is not None else None
    if query_result.get("status") == "success" and query_result.get("rows"):
        if chart_type == "histogram":
            metric = getattr(query_plan, "metric_column", None) or "the selected metric"
            answer = f"The histogram shows the distribution of {_humanize(metric)} across the returned database observations."
        elif chart_type in {"bar", "pie", "line"}:
            dimension = getattr(query_plan, "dimension_column", None) or "the selected category"
            metric = getattr(query_plan, "metric_column", None) or "the selected metric"
            label = {"bar": "bar chart", "pie": "pie chart", "line": "line chart"}[chart_type]
            answer = f"The {label} compares {_humanize(metric)} by {_humanize(dimension)} using the returned database values."
        else:
            answer = _template_answer(question, query_result, query_plan=query_plan)
    else:
        answer = _template_answer(question, query_result, query_plan=query_plan)
    if USE_LLM_ANSWER and GEMINI_API_KEY and genai is not None and genai.Client is not None and query_result.get("status") == "success":
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=build_answer_prompt(question, query_result),
            )
            if response.text:
                answer = response.text.strip()
        except Exception:
            # A template answer remains available even if the model is rate-limited.
            pass
    return AnalysisResult(answer=answer)
