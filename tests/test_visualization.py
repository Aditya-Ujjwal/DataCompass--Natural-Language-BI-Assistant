import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from visualization import VisualizationSpec, create_visualization, suggest_visualization


def test_single_numeric_result_becomes_kpi():
    result = {
        "columns": ["city", "total_revenue"],
        "rows": [["Delhi", 190000.0]],
    }

    spec = suggest_visualization(result)

    assert spec.chart_type == "kpi"
    assert spec.y == "total_revenue"


def test_categorical_numeric_result_becomes_bar_chart():
    result = {
        "columns": ["city", "total_revenue"],
        "rows": [
            ["Delhi", 190000.0],
            ["Mumbai", 155000.0],
        ],
    }

    spec = suggest_visualization(result)

    assert spec.chart_type == "bar"
    assert spec.x == "city"
    assert spec.y == "total_revenue"


def test_empty_result_becomes_table():
    result = {"columns": ["city"], "rows": []}

    spec = suggest_visualization(result)

    assert spec.chart_type == "table"


def test_visualization_spec_is_pydantic_model():
    spec = VisualizationSpec(chart_type="bar", x="city", y="revenue")

    assert spec.chart_type == "bar"


def test_bar_chart_figure_contains_bar_data():
    result = {
        "columns": ["city", "total_revenue"],
        "rows": [["Delhi", 190000.0], ["Mumbai", 155000.0]],
    }

    figure = create_visualization(result)

    assert len(figure.data) == 1
    assert figure.data[0].type == "bar"
