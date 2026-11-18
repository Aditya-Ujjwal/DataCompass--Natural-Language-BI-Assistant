import re
from typing import Any
from pydantic import BaseModel

try:
    from google import genai
except ImportError:
    from types import SimpleNamespace
    genai = SimpleNamespace(Client=None)
from config import GEMINI_API_KEY, GEMINI_MODEL


class AnswerEvaluation(BaseModel):
    grounded: bool
    reason: str


def _normalise_number(value: Any) -> str | None:
    try:
        number = float(str(value).replace(",", "").replace("₹", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    return str(int(number)) if number.is_integer() else str(number)


def basic_groundedness_check(answer: str, execution_result: dict[str, Any]) -> AnswerEvaluation:
    if execution_result.get("status") != "success":
        return AnswerEvaluation(grounded=False, reason="Database execution did not succeed.")
    if not answer.strip():
        return AnswerEvaluation(grounded=False, reason="Answer is empty.")
    rows = execution_result.get("rows", [])
    if not rows:
        has_number = re.search(r"(?<![A-Za-z])-?\d[\d,]*(?:\.\d+)?", answer)
        return AnswerEvaluation(
            grounded=not bool(has_number),
            reason=("No rows were returned and the answer contains no numeric claim." if not has_number
                    else "Answer contains a numeric claim but the database returned no rows."),
        )
    supported_values: list[float] = []
    for row in rows:
        for item in row:
            normalized = _normalise_number(item)
            if normalized is not None:
                supported_values.append(float(normalized))
    # Row count is execution metadata, so it is also supported by the result envelope.
    row_count = execution_result.get("row_count")
    if row_count is not None:
        supported_values.append(float(row_count))
    matches = re.findall(r"(?<![A-Za-z])-?\d[\d,]*(?:\.\d+)?", answer)
    unsupported = []
    for token in matches:
        displayed = float(token.replace(",", ""))
        decimal_places = len(token.split(".", 1)[1]) if "." in token else 0
        # Accept a value rounded for display (e.g. 1.13 for 1.132018), but
        # do not accept an unsupported value that merely shares some digits.
        is_supported = any(round(value, decimal_places) == round(displayed, decimal_places)
                           for value in supported_values)
        if not is_supported:
            unsupported.append(token)
    if unsupported:
        return AnswerEvaluation(grounded=False, reason=f"Answer contains numeric value(s) not found in the database result: {unsupported}")
    return AnswerEvaluation(grounded=True, reason="Numeric values in the answer are supported by the database result.")


def llm_groundedness_check(question: str, answer: str, execution_result: dict[str, Any], model: str | None = None) -> AnswerEvaluation:
    if not GEMINI_API_KEY or genai is None or genai.Client is None:
        raise ValueError("Gemini is not configured for semantic answer evaluation.")
    prompt = f"Evaluate whether the answer is fully supported by the database result. Return grounded=false if it invents any fact or number.\nQuestion: {question}\nResult: {execution_result}\nAnswer: {answer}"
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(model=model or GEMINI_MODEL, contents=prompt, config={"response_mime_type": "application/json", "response_schema": AnswerEvaluation})
    if not response.text:
        raise RuntimeError("The LLM returned an empty evaluation response.")
    return AnswerEvaluation.model_validate_json(response.text)


def evaluate_answer(question: str, answer: str, execution_result: dict[str, Any], use_llm_judge: bool = False) -> AnswerEvaluation:
    basic = basic_groundedness_check(answer, execution_result)
    if not basic.grounded or not use_llm_judge:
        return basic
    return llm_groundedness_check(question, answer, execution_result)
