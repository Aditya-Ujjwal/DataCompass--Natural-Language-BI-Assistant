from pathlib import Path

from database import get_engine, initialize_database
from sql_executor import execute_sql
from visualization import create_visualization, suggest_visualization


if __name__ == "__main__":
    initialize_database()
    engine = get_engine()

    # Use a multi-row result so that the demo shows a useful BI bar chart.
    sql = """
    SELECT city, SUM(revenue) AS total_revenue
    FROM sales
    GROUP BY city
    ORDER BY total_revenue DESC;
    """

    result = execute_sql(engine, sql)
    spec = suggest_visualization(result)
    figure = create_visualization(result, spec)

    output = Path(__file__).resolve().parents[1] / "data" / "revenue_by_city.html"
    figure.write_html(output)

    print("\nVisualization specification:")
    print(spec.model_dump_json(indent=2))
    print(f"\nInteractive chart written to: {output}")
