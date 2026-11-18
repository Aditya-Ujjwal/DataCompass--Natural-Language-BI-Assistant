from database import get_engine, initialize_database
from sql_executor import execute_sql


if __name__ == "__main__":
    initialize_database()
    engine = get_engine()

    sql = """
    SELECT
        city,
        SUM(revenue) AS total_revenue
    FROM sales
    GROUP BY city
    ORDER BY total_revenue DESC
    LIMIT 1;
    """

    result = execute_sql(engine, sql)

    print("\nExecution result:")
    print(f"Status: {result['status']}")
    print(f"Columns: {result['columns']}")
    print(f"Rows: {result['rows']}")
    print(f"Row count: {result['row_count']}")
    print(f"Execution time: {result['execution_time']:.6f} seconds")
    print(f"Error: {result['error']}")
