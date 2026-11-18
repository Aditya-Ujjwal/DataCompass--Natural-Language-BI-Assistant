import sys
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from assistant import run_assistant
from database import configure_database, reset_database_connection


QUESTIONS = {
    "compare": "Compare actual solar generation against expected solar generation for each site.",
    "energy_loss": "Which solar sites have experienced the highest total energy loss?",
    "deviation": "What is the average performance deviation for each solar site, and which site has the worst deviation?",
    "status": "How many performance records fall under Normal, Warning, and Critical categories?",
    "streak": "Which solar site has recorded the longest continuous underperformance streak?",
    "persistent": "How many persistently underperforming records does each solar site have?",
    "ratio": "Compare the average performance ratio across all solar sites and identify the best-performing site.",
    "critical": "Show me the 10 most recent Critical performance records, including site ID, timestamp, actual generation, expected generation, performance deviation, and energy loss.",
}


def _create_solar_db(path: Path) -> None:
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE performance_results (
                PerformanceID INTEGER PRIMARY KEY,
                CampusKey INTEGER,
                SiteKey INTEGER NOT NULL,
                Timestamp TEXT NOT NULL,
                ActualGeneration REAL,
                ExpectedGeneration REAL,
                Residual REAL,
                PerformanceDeviation REAL,
                PerformanceRatio REAL,
                PerformanceStatus TEXT,
                UnderperformanceStreak INTEGER,
                PersistentUnderperformance INTEGER,
                EnergyLoss REAL
            )
        """))
        conn.execute(text("""
            CREATE TABLE generation_raw (
                GenerationID INTEGER PRIMARY KEY,
                SiteKey INTEGER,
                Timestamp TEXT,
                SolarGeneration REAL
            )
        """))
        conn.execute(text("""
            CREATE TABLE solar_sites (
                SiteKey INTEGER PRIMARY KEY,
                CampusKey INTEGER,
                SiteName TEXT
            )
        """))
        conn.execute(text("INSERT INTO solar_sites VALUES (1, 1, 'North'), (2, 1, 'East'), (3, 2, 'South')"))
        conn.execute(text("""
            INSERT INTO performance_results VALUES
            (1, 1, 1, '2026-11-01T10:00:00', 80, 100, -20, -20, 0.80, 'Critical', 4, 1, 20),
            (2, 1, 1, '2026-11-02T10:00:00', 90, 100, -10, -10, 0.90, 'Normal', 0, 0, 10),
            (3, 1, 2, '2026-11-01T10:00:00', 50, 100, -50, -50, 0.50, 'Critical', 8, 1, 50),
            (4, 1, 2, '2026-11-02T10:00:00', 70, 100, -30, -30, 0.70, 'Warning', 3, 1, 30),
            (5, 2, 3, '2026-11-01T10:00:00', 100, 100, 0, 0, 1.00, 'Warning', 2, 0, 0),
            (6, 2, 3, '2026-11-02T10:00:00', 110, 100, 10, 10, 1.10, 'Normal', 0, 0, 0)
        """))
        conn.execute(text("""
            INSERT INTO generation_raw VALUES
            (1, 1, '2026-11-01T10:00:00', 80),
            (2, 2, '2026-11-02T10:00:00', 50),
            (3, 3, '2026-11-03T10:00:00', 100)
        """))
    engine.dispose()


def test_solarpulse_question_templates_use_correct_metrics_and_charts(tmp_path):
    db_path = tmp_path / "solarpulse_analytics.db"
    _create_solar_db(db_path)
    try:
        configure_database(f"sqlite:///{db_path.as_posix()}")

        compare = run_assistant(QUESTIONS["compare"])
        assert compare["status"] == "success", compare
        assert compare["query_plan"]["table"] == "performance_results"
        assert compare["execution"]["columns"] == ["SiteName", "TotalActualGeneration", "TotalExpectedGeneration"]
        assert compare["visualization"]["chart_type"] == "bar"
        assert compare["visualization"]["series"] == ["TotalExpectedGeneration"]
        assert compare["execution"]["row_count"] == 3
        assert compare["answer_evaluation"]["grounded"] is True

        energy = run_assistant(QUESTIONS["energy_loss"])
        assert energy["status"] == "success", energy
        assert energy["query_plan"]["metric_column"] == "EnergyLoss"
        assert energy["sql"] and "EnergyLoss" in energy["sql"] and "SolarGeneration" not in energy["sql"]
        assert energy["execution"]["rows"][0][0] == "East"
        assert energy["visualization"]["chart_type"] == "bar"
        assert energy["answer_evaluation"]["grounded"] is True

        deviation = run_assistant(QUESTIONS["deviation"])
        assert deviation["status"] == "success", deviation
        assert deviation["query_plan"]["aggregation"] == "AVG"
        assert deviation["execution"]["rows"][0][0] == "East"
        assert deviation["visualization"]["chart_type"] == "bar"
        assert deviation["answer_evaluation"]["grounded"] is True

        statuses = run_assistant(QUESTIONS["status"])
        assert statuses["status"] == "success", statuses
        assert statuses["visualization"]["chart_type"] == "pie"
        status_counts = {row[0]: row[1] for row in statuses["execution"]["rows"]}
        assert status_counts == {"Normal": 2, "Warning": 2, "Critical": 2}
        assert statuses["answer_evaluation"]["grounded"] is True

        streak = run_assistant(QUESTIONS["streak"])
        assert streak["status"] == "success", streak
        assert streak["query_plan"]["aggregation"] == "MAX"
        assert streak["execution"]["rows"][0] == ["East", 8]
        assert streak["answer_evaluation"]["grounded"] is True

        persistent = run_assistant(QUESTIONS["persistent"])
        assert persistent["status"] == "success", persistent
        assert persistent["query_plan"]["aggregation"] == "COUNT"
        assert persistent["execution"]["rows"][0] == ["East", 2]
        assert persistent["visualization"]["chart_type"] == "bar"
        assert persistent["answer_evaluation"]["grounded"] is True

        ratio = run_assistant(QUESTIONS["ratio"])
        assert ratio["status"] == "success", ratio
        assert ratio["query_plan"]["aggregation"] == "AVG"
        assert ratio["execution"]["rows"][0][0] == "South"
        assert ratio["execution"]["row_count"] == 3
        assert ratio["visualization"]["chart_type"] == "bar"
        assert ratio["answer_evaluation"]["grounded"] is True

        critical = run_assistant(QUESTIONS["critical"])
        assert critical["status"] == "success", critical
        assert critical["query_plan"]["table"] == "performance_results"
        assert "PerformanceStatus" in critical["sql"]
        assert "Critical" in critical["sql"]
        assert critical["execution"]["row_count"] == 2
        assert all(row[-1] == "Critical" for row in critical["execution"]["rows"])
        assert critical["visualization"]["chart_type"] == "table"
        assert critical["answer_evaluation"]["grounded"] is True

        trend = run_assistant("Generate a line chart for solar generation over time")
        assert trend["status"] == "success", trend
        assert trend["visualization"]["chart_type"] == "line"
        assert trend["execution"]["row_count"] == 3
        assert trend["answer_evaluation"]["grounded"] is True

        all_performance = run_assistant("Give me all the rows from the performance table")
        assert all_performance["status"] == "success", all_performance
        assert all_performance["query_plan"]["table"] == "performance_results"
        assert all_performance["execution"]["row_count"] == 6
        assert all_performance["visualization"]["chart_type"] == "table"
        assert all_performance["answer_evaluation"]["grounded"] is True
    finally:
        reset_database_connection()


def test_chart_answer_grounding_accepts_rounded_performance_values():
    from answer_evaluation import basic_groundedness_check

    result = basic_groundedness_check(
        "Site 3 has the highest average performance ratio at 1.05.",
        {
            "status": "success",
            "columns": ["SiteKey", "AveragePerformanceRatio"],
            "rows": [[3, 1.051234]],
            "row_count": 1,
        },
    )
    assert result.grounded is True
