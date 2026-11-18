import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from database import get_engine, initialize_database
from schema import get_database_schema


def test_schema_finds_sales_table():
    initialize_database()
    schema = get_database_schema(get_engine())
    assert "sales" in schema


def test_schema_finds_sales_columns():
    initialize_database()
    schema = get_database_schema(get_engine())
    column_names = [column["name"] for column in schema["sales"]]
    assert column_names == ["id", "city", "product", "revenue", "sale_date"]


def test_schema_contains_column_metadata():
    initialize_database()
    schema = get_database_schema(get_engine())
    revenue_column = next(
        column for column in schema["sales"] if column["name"] == "revenue"
    )
    assert revenue_column["type"] == "REAL"
    assert revenue_column["nullable"] is False
    assert revenue_column["primary_key"] is False


def test_schema_identifies_primary_key():
    initialize_database()
    schema = get_database_schema(get_engine())
    id_column = next(column for column in schema["sales"] if column["name"] == "id")
    assert id_column["primary_key"] is True
