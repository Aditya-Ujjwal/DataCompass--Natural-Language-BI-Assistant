from sqlalchemy.engine import Engine


DIALECT_NAMES = {
    "sqlite": "SQLite",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
}


def get_database_dialect(engine: Engine) -> str:
    """Return a human-readable SQL dialect name for a SQLAlchemy engine."""
    name = engine.dialect.name.lower()
    return DIALECT_NAMES.get(name, name)


def get_sqlglot_dialect(engine: Engine) -> str:
    """
    Return the SQLGlot dialect name used by validation.

    SQLGlot uses PostgreSQL/MySQL/SQLite dialect names directly.
    """
    name = engine.dialect.name.lower()

    if name == "postgresql":
        return "postgres"
    if name == "mysql":
        return "mysql"
    if name == "sqlite":
        return "sqlite"

    return name
