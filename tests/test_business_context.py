import json
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "backend"),
)

from business_context import (
    context_to_prompt_text,
    load_business_context,
    save_business_context,
)


def test_load_default_business_context():
    context = load_business_context()

    assert context["database_description"]
    assert "sales.revenue" in context["columns"]
    assert "revenue" in context["metrics"]


def test_context_to_prompt_text_contains_business_definitions():
    context = {
        "database_description": "Sales database.",
        "tables": {"sales": "Sales transactions."},
        "columns": {"sales.revenue": "Revenue from a transaction."},
        "metrics": {"revenue": "SUM(sales.revenue)."},
        "business_rules": ["Use sales.revenue for revenue."],
        "terminology": {"revenue": "sales revenue"},
    }

    text = context_to_prompt_text(context)

    assert "Sales database." in text
    assert "sales.revenue" in text
    assert "SUM(sales.revenue)" in text
    assert "Use sales.revenue" in text


def test_save_and_load_business_context(tmp_path):
    path = tmp_path / "context.json"

    context = {
        "database_description": "Test database.",
        "metrics": {"revenue": "SUM(sales.revenue)."},
    }

    save_business_context(context, path)
    loaded = load_business_context(path)

    assert loaded == context


def test_saved_context_is_valid_json(tmp_path):
    path = tmp_path / "context.json"

    context = {"metrics": {"revenue": "SUM(sales.revenue)."}}

    save_business_context(context, path)

    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["metrics"]["revenue"] == "SUM(sales.revenue)."
