import sqlite3
import sys
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import app

client = TestClient(app)


def test_database_connect_api_does_not_return_connection_url(tmp_path):
    path = tmp_path / "api.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE sample (id INTEGER, value TEXT)")
    connection.execute("INSERT INTO sample VALUES (1, 'ok')")
    connection.commit()
    connection.close()

    try:
        response = client.post(
            "/api/database/connect",
            json={"connection_url": f"sqlite:///{path.as_posix()}"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "connected"
        assert "sample" in payload["database"]["tables"]
        assert "connection_url" not in payload["database"]
    finally:
        client.post("/api/database/reset")
