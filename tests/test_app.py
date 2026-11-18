import sys
from pathlib import Path
from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import app
client = TestClient(app)

def test_home():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Natural Language BI Assistant is running"
    assert data["version"] == "1.0.0"

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "connected"

def test_config_does_not_expose_api_keys():
    response = client.get("/api/config")
    assert response.status_code == 200
    assert "GEMINI_API_KEY" not in response.text
    assert "OPENAI_API_KEY" not in response.text
