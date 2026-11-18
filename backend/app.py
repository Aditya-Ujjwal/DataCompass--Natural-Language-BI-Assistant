from uuid import uuid4
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from api_models import AskRequest, AskResponse, DatabaseConnectRequest
from assistant import run_assistant, _known_values
from business_context import load_business_context
from config import APP_NAME, APP_VERSION, LLM_PROVIDER, GEMINI_MODEL, OPENAI_MODEL, CORS_ORIGINS
from conversation import resolve_follow_up_locally
from database import (
    configure_database,
    get_database_info,
    get_engine,
    initialize_database,
    reset_database_connection,
    using_demo_database,
)
from schema import get_database_schema, get_database_profile, preview_table

@asynccontextmanager
async def lifespan(application: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="A self-hosted natural-language business intelligence assistant.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# In-memory sessions and runtime DB connections are for a single-user/local
# self-hosted deployment. For multi-user hosted deployments, add authentication,
# per-user connection isolation, and a secret manager before exposing the API.
SESSIONS: dict[str, list[dict]] = {}


@app.get("/", tags=["system"])
def home():
    return {"message": f"{APP_NAME} is running", "version": APP_VERSION}


@app.get("/health", tags=["system"])
def health():
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception:
        return {"status": "error", "database": "unavailable"}


@app.get("/api/config", tags=["system"])
def get_config():
    model = GEMINI_MODEL if LLM_PROVIDER == "gemini" else OPENAI_MODEL if LLM_PROVIDER == "openai" else None
    return {
        "app_name": APP_NAME,
        "version": APP_VERSION,
        "provider": LLM_PROVIDER,
        "model": model,
        "database": get_database_info(),
        "llm_key_configured": bool(__import__("config").GEMINI_API_KEY) if LLM_PROVIDER == "gemini" else bool(__import__("config").OPENAI_API_KEY),
    }


@app.get("/api/database", tags=["database"])
def database_info():
    try:
        info = get_database_info()
        profile = get_database_profile(get_engine())
        return {
            **info,
            "tables": [table["name"] for table in profile["tables"]],
            "table_count": profile["table_count"],
            "relationship_count": len(profile["relationships"]),
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail="The selected database is unavailable.") from exc


@app.get("/api/database/profile", tags=["database"])
def database_profile():
    """Return the complete discovered catalog: all tables, columns and joins."""
    try:
        profile = get_database_profile(get_engine())
        return {key: value for key, value in profile.items() if key != "schema"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not read the connected database catalog.") from exc


@app.get("/api/database/tables/{table_name}/preview", tags=["database"])
def database_table_preview(
    table_name: str,
    limit: int = Query(default=5, ge=1, le=20),
):
    """Return a small read-only sample from a table selected in Database Explorer."""
    try:
        return preview_table(get_engine(), table_name, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not preview this table. Check database permissions and table availability.") from exc


@app.post("/api/database/connect", tags=["database"])
def connect_database(request: DatabaseConnectRequest):
    try:
        result = configure_database(request.connection_url)
        SESSIONS.clear()
        return {"status": "connected", "database": result}
    except Exception as exc:
        # Never echo the connection URL or credentials back to the browser.
        detail = str(exc)
        if "password" in detail.lower() or "@" in detail:
            detail = "Connection failed. Check the database URL, credentials, driver, network access, and permissions."
        raise HTTPException(status_code=400, detail=detail) from exc


@app.post("/api/database/reset", tags=["database"])
def reset_database():
    try:
        result = reset_database_connection()
        SESSIONS.clear()
        return {"status": "connected", "database": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Could not restore the sample database.") from exc


@app.get("/api/schema", tags=["system"])
def get_schema():
    try:
        return get_database_schema(get_engine())
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not inspect the selected database schema.") from exc


@app.get("/api/context", tags=["system"])
def get_context():
    profile = get_database_profile(get_engine())
    if using_demo_database():
        context = load_business_context()
    else:
        schema = profile["schema"]
        context = {
            "database_description": "User-connected database. All accessible tables, columns, and foreign-key relationships are discovered automatically.",
            "tables": {table: "Discovered database table." for table in schema},
            "columns": {f"{table}.{column['name']}": f"Column type: {column.get('type', 'unknown')}" for table, columns in schema.items() for column in columns},
            "metrics": {}, "business_rules": [], "terminology": {},
        }
    context["database_profile"] = {key: value for key, value in profile.items() if key != "schema"}
    return context


@app.get("/api/session/{session_id}", tags=["session"])
def get_session(session_id: str):
    return {"session_id": session_id, "messages": SESSIONS.get(session_id, [])}


@app.delete("/api/session/{session_id}", tags=["session"])
def clear_session(session_id: str):
    SESSIONS.pop(session_id, None)
    return {"status": "cleared", "session_id": session_id}


@app.post("/ask", response_model=AskResponse, tags=["assistant"])
def ask(request: AskRequest):
    session_id = request.session_id or str(uuid4())
    history = SESSIONS.setdefault(session_id, [])
    try:
        engine = get_engine()
        schema = get_database_schema(engine)
        values = _known_values(engine, schema)
        all_values = [value for vals in values.values() for value in vals]
        resolved_question = resolve_follow_up_locally(request.question, history, all_values)
        result = run_assistant(resolved_question)
    except Exception as exc:
        return {
            "status": "error",
            "question": request.question,
            "message": "The request could not be processed. Check the selected database connection and schema.",
            "stage": "database_orchestration",
            "session_id": session_id,
        }

    result["question"] = request.question
    result["resolved_question"] = resolved_question
    result["session_id"] = session_id
    if result.get("status") == "success":
        history.append({
            "question": request.question,
            "resolved_question": resolved_question,
            "answer": result.get("answer", ""),
        })
        del history[:-20]
    return result
