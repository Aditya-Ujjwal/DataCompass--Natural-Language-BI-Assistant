import sys
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from assistant import run_assistant
from database import configure_database, reset_database_connection


def test_full_assistant_uses_connected_database_catalog_and_joins(tmp_path):
    db_path = tmp_path / "solar_multi_table.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE solar_site_details (SiteKey INTEGER PRIMARY KEY, SiteName TEXT NOT NULL)"))
        connection.execute(text("""
            CREATE TABLE generation_raw (
                GenerationID INTEGER PRIMARY KEY,
                SiteKey INTEGER NOT NULL,
                Timestamp TEXT NOT NULL,
                SolarGeneration REAL NOT NULL,
                FOREIGN KEY (SiteKey) REFERENCES solar_site_details(SiteKey)
            )
        """))
        connection.execute(text("INSERT INTO solar_site_details VALUES (1, 'North Solar Park'), (2, 'East Solar Park')"))
        connection.execute(text("INSERT INTO generation_raw VALUES (1, 1, '2026-01-01', 100), (2, 1, '2026-01-02', 120), (3, 2, '2026-01-01', 80)"))
    engine.dispose()

    try:
        connection_info = configure_database(f"sqlite:///{db_path.as_posix()}")
        assert connection_info["table_count"] == 2

        result = run_assistant("Which Solar Site generates the most solar energy?")

        assert result["status"] == "success"
        assert result["execution"]["rows"] == [["North Solar Park", 220.0]]
        assert 'JOIN "solar_site_details"' in result["sql"]
        assert result["answer_evaluation"]["grounded"] is True
    finally:
        reset_database_connection()
