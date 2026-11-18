import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "backend"),
)

from intent import QueryIntent, normalize_intent


def test_total_revenue_normalizes_to_revenue():
    intent = QueryIntent(
        intent="aggregation",
        metric="total revenue",
        dimension="city",
    )

    normalized = normalize_intent(intent)

    assert normalized.metric == "revenue"


def test_plural_city_normalizes_to_city():
    intent = QueryIntent(
        intent="ranking",
        metric="revenue",
        dimension="cities",
        limit=4,
        sort_order="descending",
    )

    normalized = normalize_intent(intent)

    assert normalized.dimension == "city"
    assert normalized.limit == 4


def test_rows_can_be_a_lookup_without_metric():
    intent = QueryIntent(
        intent="lookup",
        metric=None,
        dimension=None,
        limit=10,
    )

    normalized = normalize_intent(intent)

    assert normalized.intent == "lookup"
    assert normalized.metric is None
    assert normalized.limit == 10
