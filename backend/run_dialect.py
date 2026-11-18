from database import get_engine
from db_dialect import get_database_dialect, get_sqlglot_dialect


if __name__ == "__main__":
    engine = get_engine()

    print("\nDatabase dialect information:")
    print(f"SQLAlchemy dialect: {engine.dialect.name}")
    print(f"Human-readable dialect: {get_database_dialect(engine)}")
    print(f"SQLGlot dialect: {get_sqlglot_dialect(engine)}")
