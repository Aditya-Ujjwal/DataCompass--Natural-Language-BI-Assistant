from __future__ import annotations
from decimal import Decimal
from numbers import Number
from typing import Any

import plotly.graph_objects as go
from pydantic import BaseModel, Field


class VisualizationSpec(BaseModel):
    chart_type: str
    x: str | None = None
    y: str | None = None
    series: list[str] = Field(default_factory=list)
    title: str = "Query Result"
    bins: int = Field(default=10, ge=3, le=40)


def _is_numeric(value: Any) -> bool:
    return isinstance(value, (Number, Decimal)) and not isinstance(value, bool)


def _humanize(value: str) -> str:
    import re
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value))
    return " ".join(value.replace("_", " ").replace("-", " ").split())


def _numeric_columns(columns: list[str], rows: list[list[Any]]) -> list[str]:
    numeric = []
    for idx, col in enumerate(columns):
        values = [row[idx] for row in rows if idx < len(row) and row[idx] is not None]
        if values and all(_is_numeric(value) for value in values):
            numeric.append(col)
    return numeric


def _categorical_column(columns: list[str], numeric: list[str]) -> str | None:
    return next((col for col in columns if col not in numeric), None)


def suggest_visualization(
    result: dict[str, Any],
    preferred_chart: str | None = None,
) -> VisualizationSpec:
    """Choose a chart spec based on the actual returned columns and values."""
    columns = result.get("columns", [])
    rows = result.get("rows", [])
    if not columns or not rows:
        return VisualizationSpec(chart_type="table", title="Query Results")

    numeric = _numeric_columns(columns, rows)
    category = _categorical_column(columns, numeric)
    chart = (preferred_chart or "").lower().strip()

    if chart == "table":
        return VisualizationSpec(chart_type="table", title="Query Results")
    if chart == "histogram":
        if numeric:
            return VisualizationSpec(chart_type="histogram", x=numeric[0], title=f"Distribution of {_humanize(numeric[0])}")
        return VisualizationSpec(chart_type="table", title="Histogram unavailable — no numeric column")
    if chart in {"bar", "line", "pie"}:
        if numeric and category:
            if chart == "pie":
                yi = columns.index(numeric[0])
                pie_values = [float(row[yi]) for row in rows if row[yi] is not None]
                if not pie_values or any(value < 0 for value in pie_values) or sum(pie_values) <= 0:
                    return VisualizationSpec(chart_type="table", title="Pie chart unavailable — values must be non-negative and sum above zero")
            title_prefix = {"bar": "Bar chart", "line": "Trend", "pie": "Share by"}[chart]
            return VisualizationSpec(chart_type=chart, x=category, y=numeric[0], title=f"{title_prefix}: {_humanize(numeric[0])} by {_humanize(category)}")
        return VisualizationSpec(chart_type="table", title=f"{chart.title()} chart unavailable — need a category and numeric column")

    if len(rows) == 1 and len(numeric) == 1:
        return VisualizationSpec(chart_type="kpi", y=numeric[0], title="Key Result")
    if numeric and category:
        return VisualizationSpec(chart_type="bar", x=category, y=numeric[0], title=f"{_humanize(numeric[0])} by {_humanize(category)}")
    return VisualizationSpec(chart_type="table", title="Query Results")


def create_visualization(result: dict[str, Any], spec: VisualizationSpec | None = None):
    """Create a Plotly figure for KPI, bar, line, pie, histogram, or table."""
    columns, rows = result.get("columns", []), result.get("rows", [])
    spec = spec or suggest_visualization(result)
    x_index = columns.index(spec.x) if spec.x in columns else -1
    y_index = columns.index(spec.y) if spec.y in columns else -1

    if spec.chart_type == "kpi" and rows and y_index >= 0:
        value = float(rows[0][y_index])
        return go.Figure(go.Indicator(mode="number", value=value, title={"text": spec.title}))
    if spec.chart_type in {"bar", "line"} and rows and x_index >= 0 and y_index >= 0:
        x_values = [row[x_index] for row in rows]
        series_keys = [spec.y, *spec.series]
        figure = go.Figure()
        for series_key in series_keys:
            if series_key not in columns:
                continue
            series_index = columns.index(series_key)
            y_values = [float(row[series_index]) if row[series_index] is not None else None for row in rows]
            if spec.chart_type == "bar":
                figure.add_trace(go.Bar(x=x_values, y=y_values, name=series_key))
            else:
                figure.add_trace(go.Scatter(x=x_values, y=y_values, mode="lines+markers", name=series_key))
        return figure.update_layout(
            title=spec.title,
            xaxis_title=spec.x,
            yaxis_title=", ".join(series_keys),
            barmode="group" if spec.chart_type == "bar" else None,
        )
    if spec.chart_type == "pie" and rows and x_index >= 0 and y_index >= 0:
        labels = [str(row[x_index]) for row in rows]
        values = [float(row[y_index]) for row in rows]
        return go.Figure(go.Pie(labels=labels, values=values, hole=0.35)).update_layout(title=spec.title)
    if spec.chart_type == "histogram" and rows and x_index >= 0:
        values = [float(row[x_index]) for row in rows if row[x_index] is not None]
        return go.Figure(go.Histogram(x=values, nbinsx=spec.bins)).update_layout(title=spec.title, xaxis_title=spec.x, yaxis_title="Count")
    return go.Figure(go.Table(
        header={"values": columns},
        cells={"values": [[row[i] for row in rows] for i in range(len(columns))]},
    )).update_layout(title=spec.title)
