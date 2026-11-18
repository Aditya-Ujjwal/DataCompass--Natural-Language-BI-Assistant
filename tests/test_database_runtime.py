import sqlite3
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from database import configure_database, get_database_info, get_engine, reset_database_connection


def make_db(path: Path) -> str:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE metrics (id INTEGER PRIMARY KEY, category TEXT, amount REAL)")
    connection.execute("INSERT INTO metrics (category, amount) VALUES ('A', 12.5), ('B', 7.5)")
    connection.commit()
    connection.close()
    return f"sqlite:///{path.as_posix()}"


def test_runtime_connection_discovers_tables_and_dialect(tmp_path):
    url = make_db(tmp_path / "metrics.db")
    try:
        result = configure_database(url)
        info = get_database_info()
        assert result["tables"] == ["metrics"]
        assert info["database_type"] == "SQLite"
        assert info["is_demo"] is False
    finally:
        reset_database_connection()


def test_external_sqlite_connection_is_read_only(tmp_path):
    url = make_db(tmp_path / "readonly.db")
    try:
        configure_database(url)
        with get_engine().connect() as connection:
            rows = connection.execute(text("SELECT COUNT(*) FROM metrics")).scalar_one()
            assert rows == 2
            with pytest.raises(Exception):
                connection.execute(text("INSERT INTO metrics (category, amount) VALUES ('C', 1)"))
    finally:
        reset_database_connection()


def test_unsupported_database_scheme_is_rejected():
    with pytest.raises(ValueError, match="Supported databases"):
        configure_database("oracle+cx_oracle://user:pass@host/db")


def test_reset_returns_sample_database(tmp_path):
    url = make_db(tmp_path / "another.db")
    try:
        configure_database(url)
        info = reset_database_connection()
        assert info["is_demo"] is True
        assert info["database_type"] == "SQLite"
    finally:
        reset_database_connection()
