import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from sql_validator import validate_sql
SCHEMA = {"sales": [{"name":"id","type":"INTEGER"},{"name":"city","type":"TEXT"},{"name":"product","type":"TEXT"},{"name":"revenue","type":"REAL"},{"name":"sale_date","type":"TEXT"}]}

def test_valid_select_query():
    result = validate_sql('SELECT city, SUM(revenue) AS total_revenue FROM sales GROUP BY city;', SCHEMA)
    assert result.is_valid and result.normalized_sql

def test_rejects_unknown_table():
    result = validate_sql('SELECT city FROM customers;', SCHEMA)
    assert not result.is_valid and 'Unknown table' in result.message

def test_rejects_unknown_column():
    result = validate_sql('SELECT profit FROM sales;', SCHEMA)
    assert not result.is_valid and 'Unknown column' in result.message

def test_rejects_destructive_query():
    result = validate_sql('DROP TABLE sales;', SCHEMA)
    assert not result.is_valid and 'read-only SELECT' in result.message

def test_rejects_multiple_statements():
    result = validate_sql('SELECT * FROM sales; DROP TABLE sales;', SCHEMA)
    assert not result.is_valid and 'one SQL statement' in result.message

def test_rejects_empty_sql():
    assert not validate_sql('', SCHEMA).is_valid
