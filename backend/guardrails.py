import re
from typing import Any


class GuardrailResult:
    """Simple result returned by guardrail checks."""

    def __init__(self, allowed: bool, reason: str):
        self.allowed = allowed
        self.reason = reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
        }


# Words/patterns that strongly indicate destructive SQL.
BLOCKED_SQL_PATTERNS = [
    r"\bDROP\b",
    r"\bDELETE\b",
    r"\bUPDATE\b",
    r"\bINSERT\b",
    r"\bALTER\b",
    r"\bTRUNCATE\b",
    r"\bCREATE\b",
    r"\bREPLACE\b",
    r"\bATTACH\b",
    r"\bDETACH\b",
]


def check_input(question: str) -> GuardrailResult:
    """Allow only questions that appear relevant to BI/data analysis."""
    text = question.strip().lower()

    if not text:
        return GuardrailResult(False, "Question is empty.")

    suspicious_phrases = [
        "ignore previous instructions",
        "ignore all previous instructions",
        "jailbreak",
        "reveal your system prompt",
        "show me your system prompt",
        "developer message",
    ]

    for phrase in suspicious_phrases:
        if phrase in text:
            return GuardrailResult(
                False,
                "Potential prompt-injection attempt detected.",
            )

    # A small scope check. We intentionally keep this broad.
    analytics_terms = [
        "revenue",
        "sales",
        "profit",
        "customer",
        "customers",
        "order",
        "orders",
        "product",
        "products",
        "city",
        "region",
        "data",
        "dataset",
        "row",
        "rows",
        "record",
        "records",
        "chart",
        "graph",
        "visualize",
        "visualise",
        "average",
        "total",
        "count",
        "highest",
        "lowest",
        "compare",
        "trend",
        "growth",
        "monthly",
        "quarter",
        "year",
        "database",
        "table",
        "tables",
        "schema",
        "structure",
        "solar",
        "energy",
        "generation",
        "generated",
        "power",
        "performance",
        "site",
        "sites",
        "campus",
        "campuses",
        "yield",
        "ratio",
        "deviation",
        "output",
        "capacity",
        "irradiance",
        "timestamp",
    ]

    if not any(term in text for term in analytics_terms):
        return GuardrailResult(
            False,
            "Question appears to be outside the BI/data-analysis scope.",
        )

    return GuardrailResult(True, "Input guardrail passed.")


def check_sql(sql: str) -> GuardrailResult:
    """Perform a simple application-level safety check on SQL."""
    cleaned = sql.strip()

    if not cleaned:
        return GuardrailResult(False, "SQL is empty.")

    statements = [
        statement.strip()
        for statement in cleaned.split(";")
        if statement.strip()
    ]

    if len(statements) != 1:
        return GuardrailResult(
            False,
            "Multiple SQL statements are not allowed.",
        )

    first_word = statements[0].split(None, 1)[0].upper()

    if first_word != "SELECT":
        return GuardrailResult(
            False,
            "Only SELECT statements are allowed.",
        )

    for pattern in BLOCKED_SQL_PATTERNS:
        if re.search(pattern, statements[0], re.IGNORECASE):
            return GuardrailResult(
                False,
                "Potentially destructive SQL operation detected.",
            )

    return GuardrailResult(True, "SQL guardrail passed.")


def check_answer(
    answer: str,
    result: dict[str, Any],
) -> GuardrailResult:
    """
    Basic output guardrail.

    We do not try to prove every sentence. We only prevent an answer
    from being returned when the database execution itself failed.
    """
    if result.get("status") != "success":
        return GuardrailResult(
            False,
            "Cannot return an analytical answer because SQL execution failed.",
        )

    if not answer.strip():
        return GuardrailResult(False, "Answer is empty.")

    return GuardrailResult(True, "Output guardrail passed.")
