import json
from pathlib import Path
from typing import Any


DEFAULT_CONTEXT_PATH = (
    Path(__file__).resolve().parents[1]
    / "context"
    / "business_context.json"
)


def load_business_context(
    path: Path | None = None,
) -> dict[str, Any]:
    """Load business/database context from JSON."""
    context_path = path or DEFAULT_CONTEXT_PATH

    if not context_path.exists():
        raise FileNotFoundError(
            f"Business context file not found: {context_path}"
        )

    return json.loads(context_path.read_text(encoding="utf-8"))


def save_business_context(
    context: dict[str, Any],
    path: Path | None = None,
) -> None:
    """Save business/database context as formatted JSON."""
    context_path = path or DEFAULT_CONTEXT_PATH
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text(
        json.dumps(context, indent=2),
        encoding="utf-8",
    )


def context_to_prompt_text(
    context: dict[str, Any],
) -> str:
    """Convert business context into concise prompt text."""
    lines: list[str] = []

    database_description = context.get("database_description")
    if database_description:
        lines.append(
            f"Database description: {database_description}"
        )

    tables = context.get("tables", {})
    if tables:
        lines.append("\nTables:")
        for table, description in tables.items():
            lines.append(f"- {table}: {description}")

    columns = context.get("columns", {})
    if columns:
        lines.append("\nColumns:")
        for column, description in columns.items():
            lines.append(f"- {column}: {description}")

    metrics = context.get("metrics", {})
    if metrics:
        lines.append("\nMetrics:")
        for metric, definition in metrics.items():
            lines.append(f"- {metric}: {definition}")

    rules = context.get("business_rules", [])
    if rules:
        lines.append("\nBusiness rules:")
        for rule in rules:
            lines.append(f"- {rule}")

    terminology = context.get("terminology", {})
    if terminology:
        lines.append("\nTerminology:")
        for term, definition in terminology.items():
            lines.append(f"- {term}: {definition}")

    return "\n".join(lines)
