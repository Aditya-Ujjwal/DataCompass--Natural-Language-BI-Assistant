import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "backend"),
)

from intent import QueryIntent
from query_plan import create_query_plan


def make_schema():
    return {
        "sales": [
            {
                "name": "id",
                "type": "INTEGER",
                "nullable": False,
                "primary_key": True,
            },
            {
                "name": "city",
                "type": "TEXT",
                "nullable": False,
                "primary_key": False,
            },
            {
                "name": "revenue",
                "type": "REAL",
                "nullable": False,
                "primary_key": False,
            },
            {
                "name": "sale_date",
                "type": "TEXT",
                "nullable": False,
                "primary_key": False,
            },
        ]
    }


def test_plural_dimension_matches_schema():
    intent = QueryIntent(
        intent="ranking",
        metric="revenue",
        dimension="cities",
        limit=4,
        sort_order="descending",
    )

    plan = create_query_plan(intent, make_schema())

    assert plan.dimension_column == "city"
    assert plan.metric_column == "revenue"
    assert plan.limit == 4


def test_total_revenue_matches_revenue_column():
    intent = QueryIntent(
        intent="aggregation",
        metric="total revenue",
        dimension="city",
    )

    plan = create_query_plan(intent, make_schema())

    assert plan.metric_column == "revenue"


def test_lookup_plan_does_not_require_metric():
    intent = QueryIntent(
        intent="lookup",
        metric=None,
        dimension=None,
        limit=10,
    )

    plan = create_query_plan(intent, make_schema())

    assert plan.table == "sales"
    assert plan.metric_column is None
    assert plan.aggregation == "NONE"
    assert plan.limit == 10
