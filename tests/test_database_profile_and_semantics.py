import sys
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from schema import get_database_profile
from intent import parse_question_rules
from query_plan import create_query_plan
from sql_generator import build_sql_deterministically
from sql_validator import validate_sql
from sql_executor import execute_sql
from visualization import suggest_visualization, create_visualization


def make_solar_database():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE solar_site_details (
                SiteKey INTEGER PRIMARY KEY,
                SiteName TEXT NOT NULL,
                CampusKey INTEGER
            )
        """))
        connection.execute(text("""
            CREATE TABLE generation_raw (
                GenerationID INTEGER PRIMARY KEY,
                SiteKey INTEGER NOT NULL,
                Timestamp TEXT NOT NULL,
                SolarGeneration REAL NOT NULL,
                FOREIGN KEY (SiteKey) REFERENCES solar_site_details(SiteKey)
            )
        """))
        connection.execute(text("""
            CREATE TABLE performance_results (
                PerformanceID INTEGER PRIMARY KEY,
                SiteKey INTEGER NOT NULL,
                Timestamp TEXT NOT NULL,
                PerformanceRatio REAL,
                FOREIGN KEY (SiteKey) REFERENCES solar_site_details(SiteKey)
            )
        """))
        connection.execute(text("""
            INSERT INTO solar_site_details VALUES
            (1, 'North Solar Park', 1),
            (2, 'East Solar Park', 1),
            (3, 'West Solar Park', 2)
        """))
        connection.execute(text("""
            INSERT INTO generation_raw VALUES
            (1, 1, '2026-01-01', 100),
            (2, 1, '2026-01-02', 120),
            (3, 2, '2026-01-01', 80),
            (4, 3, '2026-01-01', 160)
        """))
        connection.execute(text("""
            INSERT INTO performance_results VALUES
            (1, 1, '2026-01-01', 0.91),
            (2, 2, '2026-01-01', 0.96),
            (3, 3, '2026-01-01', 0.87)
        """))
    return engine


def run_question(engine, question):
    profile = get_database_profile(engine)
    schema = profile["schema"]
    intent = parse_question_rules(question, schema=schema)
    assert intent is not None
    plan = create_query_plan(
        intent,
        schema,
        profile["relationships"],
        question=question,
    )
    sql = build_sql_deterministically(plan, schema, "SQLite")
    validation = validate_sql(sql, schema, "SQLite")
    assert validation.is_valid, validation.message
    result = execute_sql(engine, validation.normalized_sql or sql)
    assert result["status"] == "success", result["error"]
    return profile, intent, plan, sql, result


def test_database_profile_discovers_all_tables_columns_and_relationships():
    engine = make_solar_database()
    try:
        profile = get_database_profile(engine)
        names = {table["name"] for table in profile["tables"]}
        assert names == {"solar_site_details", "generation_raw", "performance_results"}
        assert profile["table_count"] == 3
        assert any(
            relation["from_table"] == "generation_raw"
            and relation["to_table"] == "solar_site_details"
            for relation in profile["relationships"]
        )
        generation = next(table for table in profile["tables"] if table["name"] == "generation_raw")
        assert {column["name"] for column in generation["columns"]} >= {
            "SiteKey", "Timestamp", "SolarGeneration"
        }
    finally:
        engine.dispose()


def test_solar_energy_question_joins_site_dimension_and_returns_top_site():
    engine = make_solar_database()
    try:
        _profile, intent, plan, sql, result = run_question(
            engine,
            "Which Solar Site generates the most solar energy?",
        )
        assert intent.metric == "SolarGeneration"
        assert intent.dimension == "SiteName"
        assert plan.table == "generation_raw"
        assert plan.dimension_table == "solar_site_details"
        assert "JOIN \"solar_site_details\"" in sql
        assert result["rows"] == [["North Solar Park", 220.0]]
    finally:
        engine.dispose()


def test_performance_ranking_uses_performance_table_and_site_join():
    engine = make_solar_database()
    try:
        _profile, intent, plan, sql, result = run_question(
            engine,
            "What are the top 4 solar sites with highest performance?",
        )
        assert intent.metric == "PerformanceRatio"
        assert plan.table == "performance_results"
        assert plan.dimension_table == "solar_site_details"
        assert "LIMIT 4" in sql
        assert result["row_count"] == 3
        assert result["rows"][0][0] == "East Solar Park"
    finally:
        engine.dispose()


def test_explicit_bar_chart_request_returns_bar_spec_and_plot():
    engine = make_solar_database()
    try:
        _profile, intent, _plan, _sql, result = run_question(
            engine,
            "Generate a bar chart for solar generation by site",
        )
        spec = suggest_visualization(result, preferred_chart=intent.chart_type)
        figure = create_visualization(result, spec)
        assert spec.chart_type == "bar"
        assert spec.x == "SiteName"
        assert figure.data[0].type == "bar"
    finally:
        engine.dispose()


def test_line_chart_aggregates_generation_over_timestamp():
    engine = make_solar_database()
    try:
        _profile, intent, plan, sql, result = run_question(
            engine,
            "Generate a line chart of solar energy over time",
        )
        spec = suggest_visualization(result, preferred_chart=intent.chart_type)
        figure = create_visualization(result, spec)
        assert plan.dimension_column == "Timestamp"
        assert "GROUP BY \"Timestamp\"" in sql
        assert spec.chart_type == "line"
        assert figure.data[0].type == "scatter"
    finally:
        engine.dispose()


def test_histogram_uses_raw_numeric_generation_values():
    engine = make_solar_database()
    try:
        _profile, intent, plan, _sql, result = run_question(
            engine,
            "Show a histogram of solar energy",
        )
        spec = suggest_visualization(result, preferred_chart=intent.chart_type)
        figure = create_visualization(result, spec)
        assert intent.chart_type == "histogram"
        assert plan.aggregation == "NONE"
        assert spec.chart_type == "histogram"
        assert figure.data[0].type == "histogram"
    finally:
        engine.dispose()


def test_named_table_row_lookup_reads_the_requested_table():
    engine = make_solar_database()
    try:
        _profile, intent, plan, sql, result = run_question(
            engine,
            "Give me all rows from performance table",
        )
        assert intent.intent == "lookup"
        assert plan.table == "performance_results"
        assert "FROM \"performance_results\"" in sql
        assert result["row_count"] == 3
    finally:
        engine.dispose()


def test_database_catalog_question_is_detected_without_llm():
    intent = parse_question_rules(
        "Read all the tables in database",
        schema={"generation_raw": [], "performance_results": []},
    )
    assert intent.intent == "metadata"


def test_performance_ratio_uses_average_not_sum():
    engine = make_solar_database()
    try:
        profile = get_database_profile(engine)
        schema = profile["schema"]
        intent = parse_question_rules(
            "What are the top 4 solar sites with highest performance?",
            schema=schema,
        )
        plan = create_query_plan(intent, schema, profile["relationships"], question="highest performance by site")
        assert plan.aggregation == "AVG"
    finally:
        engine.dispose()


def test_shared_primary_key_relationship_is_inferred_without_declared_fk():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE sites (SiteKey INTEGER PRIMARY KEY, SiteName TEXT)"))
        connection.execute(text("CREATE TABLE readings (ReadingID INTEGER PRIMARY KEY, SiteKey INTEGER, SolarGeneration REAL)"))
    try:
        profile = get_database_profile(engine)
        assert any(
            edge["from_table"] == "readings"
            and edge["to_table"] == "sites"
            and edge["source"] == "inferred_shared_key"
            for edge in profile["relationships"]
        )
    finally:
        engine.dispose()


def test_all_rows_lookup_uses_configured_safe_row_cap():
    from config import MAX_RESULT_ROWS
    intent = parse_question_rules(
        "Give me all rows from performance table",
        schema={"performance_results": [{"name": "id", "type": "INTEGER"}]},
    )
    assert intent.intent == "lookup"
    assert intent.limit == MAX_RESULT_ROWS


def test_generic_measure_column_can_be_resolved_from_unambiguous_subject_table():
    schema = {
        "solar_energy_generation": [
            {"name": "GenerationID", "type": "INTEGER", "primary_key": True},
            {"name": "SiteKey", "type": "INTEGER", "primary_key": False},
            {"name": "Timestamp", "type": "TEXT", "primary_key": False},
            {"name": "Value", "type": "REAL", "primary_key": False},
        ]
    }
    intent = parse_question_rules(
        "What is the total solar energy from solar energy generation?",
        schema=schema,
    )
    assert intent is not None
    assert intent.metric == "Value"


def test_requested_chart_type_is_preserved_for_all_supported_visuals():
    engine = make_solar_database()
    try:
        for question, expected in [
            ("Generate a bar chart for solar generation by site", "bar"),
            ("Generate a line chart for solar energy over time", "line"),
            ("Generate a pie chart for solar generation by site", "pie"),
            ("Show a histogram of solar energy", "histogram"),
        ]:
            _profile, intent, _plan, _sql, result = run_question(engine, question)
            spec = suggest_visualization(result, preferred_chart=intent.chart_type)
            assert intent.chart_type == expected
            assert spec.chart_type == expected
    finally:
        engine.dispose()
