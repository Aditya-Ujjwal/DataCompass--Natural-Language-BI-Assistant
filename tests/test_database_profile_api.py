import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import app as app_module


def test_database_profile_api_lists_all_tables_columns_and_relationships(tmp_path):
    database_path = tmp_path / "profile_api.sqlite"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE sites (SiteKey INTEGER PRIMARY KEY, SiteName TEXT)"))
        connection.execute(text("CREATE TABLE generation (ID INTEGER PRIMARY KEY, SiteKey INTEGER, SolarGeneration REAL, FOREIGN KEY(SiteKey) REFERENCES sites(SiteKey))"))

    with patch("app.get_engine", return_value=engine):
        client = TestClient(app_module.app)
        response = client.get("/api/database/profile")

    assert response.status_code == 200
    profile = response.json()
    assert profile["table_count"] == 2
    names = {table["name"] for table in profile["tables"]}
    assert names == {"sites", "generation"}
    generation = next(table for table in profile["tables"] if table["name"] == "generation")
    assert "SolarGeneration" in {column["name"] for column in generation["columns"]}
    assert any(edge["from_table"] == "generation" and edge["to_table"] == "sites" for edge in profile["relationships"])
    engine.dispose()


def test_database_table_preview_returns_bounded_rows_from_selected_table(tmp_path):
    database_path = tmp_path / "table_preview.sqlite"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE performance_results (PerformanceID INTEGER PRIMARY KEY, SiteName TEXT, PerformanceRatio REAL)"))
        connection.execute(text("INSERT INTO performance_results VALUES (1, 'North Site', 0.91), (2, 'East Site', 0.96), (3, 'West Site', 0.87)"))

    try:
        with patch("app.get_engine", return_value=engine):
            client = TestClient(app_module.app)
            response = client.get("/api/database/tables/performance_results/preview?limit=2")

        assert response.status_code == 200
        preview = response.json()
        assert preview["table"] == "performance_results"
        assert preview["columns"] == ["PerformanceID", "SiteName", "PerformanceRatio"]
        assert preview["row_count"] == 2
        assert preview["truncated"] is True
        assert preview["rows"][0][1] == "North Site"
    finally:
        engine.dispose()


def test_database_table_preview_rejects_unknown_table(tmp_path):
    database_path = tmp_path / "unknown_preview.sqlite"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE known_table (id INTEGER PRIMARY KEY)"))

    try:
        with patch("app.get_engine", return_value=engine):
            client = TestClient(app_module.app)
            response = client.get("/api/database/tables/not_a_table/preview")
        assert response.status_code == 404
    finally:
        engine.dispose()
