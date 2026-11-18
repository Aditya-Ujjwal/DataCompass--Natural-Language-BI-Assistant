from database import get_engine, initialize_database
from schema import print_database_schema


if __name__ == "__main__":
    initialize_database()
    engine = get_engine()
    print_database_schema(engine)
