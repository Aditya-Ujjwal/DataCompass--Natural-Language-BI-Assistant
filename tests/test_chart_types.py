import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from intent import parse_question_rules
from query_plan import create_query_plan
from sql_generator import build_sql_deterministically
from visualization import create_visualization, suggest_visualization

SCHEMA = {
    "sales": [
        {"name": "id", "type": "INTEGER"},
        {"name": "city", "type": "TEXT"},
        {"name": "product", "type": "TEXT"},
        {"name": "revenue", "type": "REAL"},
        {"name": "sale_date", "type": "TEXT"},
    ]
}


def test_bar_chart_request_uses_category_and_metric():
    intent = parse_question_rules("Generate a bar chart for revenue by city", schema=SCHEMA)
    plan = create_query_plan(intent, SCHEMA)
    sql = build_sql_deterministically(plan, SCHEMA, "SQLite")
    assert intent.chart_type == "bar"
    assert plan.dimension_column == "city"
    assert "GROUP BY \"city\"" in sql
    assert suggest_visualization({"columns": ["city", "total_revenue"], "rows": [["Delhi", 1.0]]}, "bar").chart_type == "bar"


def test_line_chart_uses_date_dimension_and_orders_it():
    intent = parse_question_rules("Generate a line chart for revenue over time", schema=SCHEMA)
    plan = create_query_plan(intent, SCHEMA)
    sql = build_sql_deterministically(plan, SCHEMA, "SQLite")
    assert intent.chart_type == "line"
    assert plan.dimension_column == "sale_date"
    assert 'ORDER BY "sale_date" ASC' in sql


def test_pie_chart_uses_category_metric():
    intent = parse_question_rules("Generate a pie chart for revenue by city", schema=SCHEMA)
    plan = create_query_plan(intent, SCHEMA)
    sql = build_sql_deterministically(plan, SCHEMA, "SQLite")
    spec = suggest_visualization({"columns": ["city", "total_revenue"], "rows": [["Delhi", 10.0], ["Mumbai", 5.0]]}, "pie")
    assert intent.chart_type == "pie"
    assert "GROUP BY \"city\"" in sql
    assert spec.chart_type == "pie"
    figure = create_visualization({"columns": ["city", "total_revenue"], "rows": [["Delhi", 10.0], ["Mumbai", 5.0]]}, spec)
    assert figure.data[0].type == "pie"


def test_histogram_selects_raw_metric_values():
    intent = parse_question_rules("Show a histogram of revenue", schema=SCHEMA)
    plan = create_query_plan(intent, SCHEMA)
    sql = build_sql_deterministically(plan, SCHEMA, "SQLite")
    spec = suggest_visualization({"columns": ["revenue"], "rows": [[1.0], [2.0], [3.0]]}, "histogram")
    assert intent.intent == "distribution"
    assert intent.chart_type == "histogram"
    assert plan.aggregation == "NONE"
    assert 'SELECT "revenue" FROM "sales"' in sql
    assert spec.chart_type == "histogram"
    figure = create_visualization({"columns": ["revenue"], "rows": [[1.0], [2.0], [3.0]]}, spec)
    assert figure.data[0].type == "histogram"


def test_pie_chart_falls_back_for_negative_values():
    spec = suggest_visualization(
        {"columns": ["city", "profit"], "rows": [["A", 10.0], ["B", -2.0]]},
        "pie",
    )
    assert spec.chart_type == "table"


def test_grouped_bar_supports_actual_and_expected_series():
    from visualization import VisualizationSpec

    result = {
        "columns": ["SiteKey", "TotalActualGeneration", "TotalExpectedGeneration"],
        "rows": [[1, 100.0, 120.0], [2, 140.0, 130.0]],
    }
    spec = VisualizationSpec(
        chart_type="bar",
        x="SiteKey",
        y="TotalActualGeneration",
        series=["TotalExpectedGeneration"],
        title="Actual vs Expected Generation by Site",
    )

    figure = create_visualization(result, spec)

    assert len(figure.data) == 2
    assert figure.data[0].type == "bar"
    assert figure.data[1].type == "bar"
    assert figure.layout.barmode == "group"


def test_multi_series_line_supports_actual_and_expected_generation():
    from visualization import VisualizationSpec

    result = {
        "columns": ["Timestamp", "TotalActualGeneration", "TotalExpectedGeneration"],
        "rows": [
            ["2026-11-01", 100.0, 120.0],
            ["2026-11-02", 130.0, 125.0],
        ],
    }
    spec = VisualizationSpec(
        chart_type="line",
        x="Timestamp",
        y="TotalActualGeneration",
        series=["TotalExpectedGeneration"],
        title="Actual vs Expected Generation Over Time",
    )

    figure = create_visualization(result, spec)

    assert len(figure.data) == 2
    assert all(trace.type == "scatter" for trace in figure.data)
