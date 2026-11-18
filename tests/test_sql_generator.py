import sys
from pathlib import Path
from unittest.mock import patch
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from intent import QueryIntent
from query_plan import create_query_plan
from sql_generator import SQLResult, build_sql_prompt, build_sql_deterministically, generate_sql


def schema():
    return {"sales": [{"name":"id","type":"INTEGER"},{"name":"city","type":"TEXT"},{"name":"product","type":"TEXT"},{"name":"revenue","type":"REAL"},{"name":"sale_date","type":"TEXT"}]}


def plan():
    return create_query_plan(QueryIntent(intent="ranking", metric="revenue", dimension="city", sort_order="descending", limit=1), schema())


def test_sql_result_model():
    assert SQLResult(sql="SELECT * FROM sales").sql.startswith("SELECT")


def test_prompt_contains_context_and_dialect():
    prompt = build_sql_prompt(plan(), schema(), {"metrics":{"revenue":"SUM(sales.revenue)"}}, "SQLite")
    assert "SQLite" in prompt and "SUM(sales.revenue)" in prompt and "sales" in prompt


def test_deterministic_ranking_sql():
    sql = build_sql_deterministically(plan(), schema())
    assert "GROUP BY \"city\"" in sql and "ORDER BY \"total_revenue\" DESC" in sql and "LIMIT 1" in sql


def test_deterministic_top_four_sql():
    query_plan = create_query_plan(QueryIntent(intent="ranking", metric="revenue", dimension="cities", sort_order="descending", limit=4), schema())
    sql = build_sql_deterministically(query_plan, schema())
    assert "LIMIT 4" in sql


def test_lookup_sql_defaults_limit():
    query_plan = create_query_plan(QueryIntent(intent="lookup", metric=None, dimension=None, limit=10), schema())
    sql = build_sql_deterministically(query_plan, schema())
    assert 'SELECT * FROM "sales"' in sql and "LIMIT 10" in sql


def test_time_period_is_sqlite_compatible():
    query_plan = create_query_plan(QueryIntent(intent="ranking", metric="revenue", dimension="city", time_period="last quarter", sort_order="descending", limit=1), schema())
    sql = build_sql_deterministically(query_plan, schema())
    assert "DATE_TRUNC" not in sql and "sale_date" in sql


def test_sql_generation_does_not_require_api_key_for_supported_question():
    with patch("sql_generator.GEMINI_API_KEY", None):
        result = generate_sql(plan(), schema())
    assert "SELECT" in result.sql


def test_llm_fallback_requires_key_when_forced():
    with patch("sql_generator.GEMINI_API_KEY", None):
        with pytest.raises(ValueError, match="LLM SQL generation"):
            generate_sql(plan(), schema(), force_llm=True)


def test_deterministic_sql_quotes_real_world_identifiers_with_spaces():
    from query_plan import QueryPlan
    from sql_generator import build_sql_deterministically

    schema = {
        "Generation Raw": [
            {"name": "Generation ID", "type": "INTEGER", "primary_key": True},
            {"name": "Solar Site", "type": "TEXT", "primary_key": False},
            {"name": "Energy Generated", "type": "REAL", "primary_key": False},
        ]
    }
    plan = QueryPlan(
        goal="Compare energy by site",
        table="Generation Raw",
        metric_column="Energy Generated",
        dimension_column="Solar Site",
        aggregation="SUM",
        metric_table="Generation Raw",
        dimension_table="Generation Raw",
    )

    sql = build_sql_deterministically(plan, schema, "SQLite")

    assert 'FROM "Generation Raw"' in sql
    assert 'SUM("Energy Generated")' in sql
    assert 'GROUP BY "Solar Site"' in sql
