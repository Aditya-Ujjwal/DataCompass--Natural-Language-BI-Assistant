from database import get_engine, initialize_database
from intent import understand_question
from query_plan import create_query_plan, print_query_plan
from schema import get_database_schema


if __name__ == "__main__":
    question = "Which city generated the highest revenue last quarter?"

    initialize_database()
    engine = get_engine()
    schema = get_database_schema(engine)

    intent = understand_question(question)
    plan = create_query_plan(intent, schema)

    print("Structured intent:")
    print(intent.model_dump_json(indent=2))
    print_query_plan(plan)
