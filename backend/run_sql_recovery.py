from database import get_engine, initialize_database
from schema import get_database_schema
from sql_recovery import execute_with_recovery


if __name__ == "__main__":
    initialize_database()
    engine = get_engine()
    schema = get_database_schema(engine)

    # Deliberately invalid SQLite SQL to demonstrate recovery.
    sql = """
    SELECT city, SUM(revenue) AS total_revenue
    FROM sales
    WHERE DATE_TRUNC('quarter', sale_date) IS NOT NULL
    GROUP BY city
    ORDER BY total_revenue DESC
    LIMIT 1;
    """

    result = execute_with_recovery(
        engine=engine,
        sql=sql,
        schema=schema,
        dialect="SQLite",
        max_retries=2,
    )

    print("\nSQL recovery result:")
    print(f"Status: {result['status']}")
    print(f"Retries: {result.get('retries')}")
    print(f"Attempted SQL: {result.get('attempted_sql')}")
    print(f"Rows: {result.get('rows')}")
    print(f"Row count: {result.get('row_count')}")
    print(f"Error: {result.get('error')}")
    print(f"Recovery errors: {result.get('recovery_errors')}")
