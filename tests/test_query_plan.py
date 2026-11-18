import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from intent import QueryIntent
from query_plan import create_query_plan


@pytest.fixture
def sales_schema():
    return {
        "sales": [
            {"name": "id", "type": "INTEGER", "nullable": False, "primary_key": True},
            {"name": "city", "type": "TEXT", "nullable": False, "primary_key": False},
            {"name": "product", "type": "TEXT", "nullable": False, "primary_key": False},
            {"name": "revenue", "type": "REAL", "nullable": False, "primary_key": False},
            {"name": "sale_date", "type": "TEXT", "nullable": False, "primary_key": False},
        ]
    }


def test_create_ranking_plan(sales_schema):
    intent = QueryIntent(
        intent="ranking",
        metric="revenue",
        dimension="city",
        filters=[],
        time_period="last quarter",
        sort_order="descending",
        limit=1,
    )

    plan = create_query_plan(intent, sales_schema)

    assert plan.table == "sales"
    assert plan.metric_column == "revenue"
    assert plan.dimension_column == "city"
    assert plan.aggregation == "SUM"
    assert plan.time_period == "last quarter"
    assert plan.sort_order == "descending"
    assert plan.limit == 1


def test_create_lookup_plan(sales_schema):
    intent = QueryIntent(
        intent="lookup",
        metric="revenue",
        dimension=None,
        filters=["city=Delhi"],
        time_period=None,
        sort_order="none",
        limit=None,
    )

    plan = create_query_plan(intent, sales_schema)

    assert plan.table == "sales"
    assert plan.metric_column == "revenue"
    assert plan.dimension_column is None
    assert plan.aggregation == "NONE"
    assert plan.filters == ["city=Delhi"]


def test_plan_fails_when_metric_is_not_in_schema(sales_schema):
    intent = QueryIntent(
        intent="aggregation",
        metric="profit",
        dimension=None,
        filters=[],
        time_period=None,
        sort_order="none",
        limit=None,
    )

    with pytest.raises(ValueError, match="profit"):
        create_query_plan(intent, sales_schema)
