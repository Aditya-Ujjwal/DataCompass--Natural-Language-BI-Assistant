from database import get_engine, initialize_database
from sql_executor import execute_sql
from result_analyzer import generate_answer


if __name__ == "__main__":
    question = "Which city generated the highest revenue?"

    initialize_database()
    engine = get_engine()

    sql = """
    SELECT city, SUM(revenue) AS total_revenue
    FROM sales
    GROUP BY city
    ORDER BY total_revenue DESC
    LIMIT 1;
    """

    query_result = execute_sql(engine, sql)
    result = generate_answer(question, query_result)

    print("\nDatabase result:")
    print(query_result)

    print("\nGenerated answer:")
    print(result.answer)
