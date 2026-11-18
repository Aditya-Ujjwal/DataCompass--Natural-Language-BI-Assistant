from database import get_engine, initialize_database
from schema import get_database_schema
from sql_generator import generate_sql
from intent import understand_question
from query_plan import create_query_plan
from sql_validator import validate_sql


if __name__ == "__main__":
    question = "Which city generated the highest revenue last quarter?"

    initialize_database()
    engine = get_engine()
    schema = get_database_schema(engine)

    intent = understand_question(question)
    plan = create_query_plan(intent, schema)
    generated_sql = generate_sql(plan, schema)

    print("\nGenerated SQL:")
    print(generated_sql.sql)

    result = validate_sql(generated_sql.sql, schema)

    print("\nValidation:")
    print(f"Valid: {result.is_valid}")
    print(f"Message: {result.message}")

    if result.normalized_sql:
        print("\nNormalized SQL:")
        print(result.normalized_sql)
