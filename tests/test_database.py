import sys
from pathlib import Path
from sqlalchemy import text
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from database import get_engine, initialize_database, test_connection as database_connection_check

def test_database_connection():
    assert database_connection_check() is True

def test_sales_table_exists():
    initialize_database()
    with get_engine().connect() as connection:
        name = connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='sales'")).scalar_one_or_none()
    assert name == "sales"

def test_sample_data_exists():
    initialize_database()
    with get_engine().connect() as connection:
        count = connection.execute(text("SELECT COUNT(*) FROM sales")).scalar_one()
    assert count == 5
