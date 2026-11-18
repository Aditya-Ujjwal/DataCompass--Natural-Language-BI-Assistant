import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "backend"),
)

from db_dialect import get_database_dialect, get_sqlglot_dialect


def make_engine(dialect_name: str):
    return SimpleNamespace(
        dialect=SimpleNamespace(name=dialect_name)
    )


def test_sqlite_dialect_name():
    engine = make_engine("sqlite")

    assert get_database_dialect(engine) == "SQLite"
    assert get_sqlglot_dialect(engine) == "sqlite"


def test_postgresql_mapping():
    engine = make_engine("postgresql")

    assert get_database_dialect(engine) == "PostgreSQL"
    assert get_sqlglot_dialect(engine) == "postgres"


def test_mysql_mapping():
    engine = make_engine("mysql")

    assert get_database_dialect(engine) == "MySQL"
    assert get_sqlglot_dialect(engine) == "mysql"


def test_unknown_dialect_is_preserved():
    engine = make_engine("oracle")

    assert get_database_dialect(engine) == "oracle"
    assert get_sqlglot_dialect(engine) == "oracle"
