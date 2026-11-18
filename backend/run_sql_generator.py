from database import get_engine, initialize_database
from intent import understand_question
from query_plan import create_query_plan
from schema import get_database_schema
from sql_generator import generate_sql


if __name__ == "__main__":
    question = "Which city generated the highest revenue last quarter?"

    initialize_database()
    engine = get_engine()
    schema = get_database_schema(engine)

    intent = understand_question(question)
    plan = create_query_plan(intent, schema)
    result = generate_sql(plan, schema)

    print("\nGenerated SQL:")
    print(result.sql)
