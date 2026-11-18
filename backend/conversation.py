from typing import Literal, Any
import re
from pydantic import BaseModel

try:
    from google import genai
except ImportError:
    from types import SimpleNamespace
    genai = SimpleNamespace(Client=None)
from config import GEMINI_API_KEY, GEMINI_MODEL


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class Conversation:
    def __init__(self) -> None:
        self.messages: list[Message] = []
    def add_user_message(self, content: str) -> None:
        self.messages.append(Message(role="user", content=content))
    def add_assistant_message(self, content: str) -> None:
        self.messages.append(Message(role="assistant", content=content))
    def get_history(self) -> list[Message]:
        return list(self.messages)
    def clear(self) -> None:
        self.messages.clear()


class RewrittenQuestion(BaseModel):
    rewritten_question: str


def resolve_follow_up_locally(question: str, history: list[dict[str, Any]], known_values: list[str] | None = None) -> str:
    """Resolve common 'what about X?' follow-ups without spending an LLM call."""
    if not history:
        return question
    if not re.match(r"^(what about|how about|and what about|and in|what about in)\b", question.strip(), re.IGNORECASE):
        return question
    target = None
    for value in known_values or ["Delhi", "Mumbai", "Bangalore", "Laptop", "Phone", "Tablet"]:
        if re.search(rf"(?<!\w){re.escape(value)}(?!\w)", question, re.IGNORECASE):
            target = value
            break
    if not target:
        return question
    previous = str(history[-1].get("resolved_question") or history[-1].get("question") or "")
    context = " ".join(str(item.get("resolved_question") or item.get("question") or "") for item in history[-3:])
    metric = "revenue" if re.search(r"\b(revenue|sales)\b", context, re.IGNORECASE) else ""
    period_match = re.search(r"\b(last quarter|previous quarter|this quarter|last month|previous month|this month|last year|this year|last 30 days|last 7 days)\b", context, re.IGNORECASE)
    period = f" {period_match.group(1)}" if period_match else ""
    if target.lower() in {"delhi", "mumbai", "bangalore"} and metric:
        return f"What was {metric} in {target}{period}?"
    if target.lower() in {"laptop", "phone", "tablet"} and metric:
        return f"What was {metric} for {target}{period}?"
    return question


def rewrite_follow_up(question: str, history: list[Message], model: str | None = None) -> RewrittenQuestion:
    if not GEMINI_API_KEY or genai is None or genai.Client is None:
        raise ValueError("GEMINI_API_KEY is not configured for semantic follow-up rewriting.")
    history_text = "\n".join(f"{m.role.upper()}: {m.content}" for m in history)
    prompt = f"Rewrite this follow-up as one standalone BI question. Preserve meaning and invent no filters or metrics.\nHistory:\n{history_text}\nNew question: {question}"
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(model=model or GEMINI_MODEL, contents=prompt, config={"response_mime_type": "application/json", "response_schema": RewrittenQuestion})
    if not response.text:
        raise RuntimeError("The LLM returned an empty rewritten question.")
    return RewrittenQuestion.model_validate_json(response.text)
