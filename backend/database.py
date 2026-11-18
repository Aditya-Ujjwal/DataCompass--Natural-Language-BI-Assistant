"""Runtime database connections for the local BI assistant.

The demo database is writable only for first-time sample-data setup. Queries
issued by the assistant are separately restricted to read-only SELECT SQL.
A user-supplied database connection is held in process memory and is not
written to .env or returned by the API.
"""
from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL, make_url
from urllib.parse import quote

from config import DATABASE_URL as CONFIG_DATABASE_URL

PROJECT_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_DIR / "data" / "bi.db"
DEFAULT_DATABASE_URL = CONFIG_DATABASE_URL
_DEMO_DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"


def _matches_demo_database(connection_url: str) -> bool:
    try:
        url = make_url(connection_url)
        if url.get_backend_name() != "sqlite" or not url.database:
            return False
        candidate = Path(url.database).expanduser().resolve()
        return candidate == DATABASE_PATH.resolve()
    except Exception:
        return False


_DEFAULT_IS_DEMO = _matches_demo_database(DEFAULT_DATABASE_URL)
_lock = RLock()
_engine: Engine | None = None
_current_url = DEFAULT_DATABASE_URL
_is_demo = _DEFAULT_IS_DEMO
_display_name = "Sample sales database" if _DEFAULT_IS_DEMO else "Configured database"


def _normalise_url(connection_url: str) -> str:
    raw = (connection_url or "").strip()
    if not raw:
        raise ValueError("Enter a SQLAlchemy database connection URL.")
    try:
        url = make_url(raw)
    except Exception as exc:
        raise ValueError("The database URL is not valid. Check its format and URL-encode special characters in credentials.") from exc

    backend = url.get_backend_name().lower()
    driver = url.drivername.lower()
    if backend not in {"sqlite", "postgresql", "mysql"}:
        raise ValueError("Supported databases are SQLite, PostgreSQL, and MySQL.")

    # Use drivers declared in requirements.txt instead of depending on optional
    # system-wide drivers that may not be installed.
    if backend == "postgresql" and driver == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    if backend == "mysql" and driver == "mysql":
        url = url.set(drivername="mysql+pymysql")

    if backend == "sqlite":
        database = url.database
        if not database:
            raise ValueError("For SQLite, provide a database file path, e.g. sqlite:///C:/data/sales.db.")
        if database not in {":memory:"} and not database.startswith("file:"):
            path = Path(database).expanduser()
            if not path.is_absolute():
                path = (Path.cwd() / path).resolve()
            if not path.exists() or not path.is_file():
                raise ValueError(f"SQLite database file does not exist: {path}")

    return url.render_as_string(hide_password=False)


def _make_engine(connection_url: str, read_only: bool = False) -> Engine:
    url = make_url(connection_url)
    backend = url.get_backend_name().lower()
    options: dict[str, Any] = {"pool_pre_ping": True, "future": True}
    if backend == "sqlite":
        options["connect_args"] = {"check_same_thread": False, "timeout": 15}
        if read_only and url.database not in {None, ":memory:"} and not url.database.startswith("file:"):
            path = Path(url.database).expanduser().resolve()
            uri_database = "file:" + quote(path.as_posix(), safe="/:\\")
            url = URL.create("sqlite", database=uri_database, query={"mode": "ro", "uri": "true"})
    try:
        return create_engine(url, **options)
    except ModuleNotFoundError as exc:
        raise ValueError(
            "The database driver is not installed. Reinstall backend requirements: "
            "python -m pip install -r backend/requirements.txt"
        ) from exc


def get_engine() -> Engine:
    """Return the currently selected SQLAlchemy engine."""
    global _engine
    with _lock:
        if _engine is None:
            if _is_demo:
                DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _engine = _make_engine(_current_url, read_only=not _is_demo)
        return _engine


def using_demo_database() -> bool:
    return _is_demo


def get_database_info() -> dict[str, Any]:
    """Return safe connection metadata; never return credentials or full URL."""
    engine = get_engine()
    backend = engine.dialect.name.lower()
    dialect_names = {"sqlite": "SQLite", "postgresql": "PostgreSQL", "mysql": "MySQL"}
    if _is_demo:
        name = "Sample sales database"
    elif backend == "sqlite":
        database = make_url(_current_url).database or "SQLite database"
        name = Path(database.replace("file:", "")).name or "SQLite database"
    else:
        parsed = make_url(_current_url)
        name = parsed.database or f"{dialect_names.get(backend, backend)} database"
    return {
        "connected": True,
        "is_demo": _is_demo,
        "database_type": dialect_names.get(backend, backend),
        "dialect": backend,
        "display_name": name,
        "driver": engine.dialect.driver,
    }


def configure_database(connection_url: str) -> dict[str, Any]:
    """Test and activate a user-selected database connection in memory."""
    global _engine, _current_url, _is_demo, _display_name
    safe_url = _normalise_url(connection_url)
    candidate = _make_engine(safe_url, read_only=True)
    try:
        with candidate.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
        from schema import get_database_schema
        discovered = get_database_schema(candidate)
        if not discovered:
            raise ValueError("Connected successfully, but no accessible tables were found. Check the database and schema permissions.")
    except Exception:
        candidate.dispose()
        raise

    with _lock:
        old_engine = _engine
        _engine = candidate
        _current_url = safe_url
        _is_demo = False
        _display_name = get_database_info()["display_name"]
        if old_engine is not None:
            old_engine.dispose()

    return {**get_database_info(), "tables": list(discovered.keys()), "table_count": len(discovered)}


def reset_database_connection() -> dict[str, Any]:
    """Switch back to the bundled demo database."""
    global _engine, _current_url, _is_demo, _display_name
    with _lock:
        old_engine = _engine
        _engine = None
        _current_url = DEFAULT_DATABASE_URL
        _is_demo = _DEFAULT_IS_DEMO
        _display_name = "Sample sales database" if _DEFAULT_IS_DEMO else "Configured database"
        if old_engine is not None:
            old_engine.dispose()
    initialize_database()
    from schema import get_database_schema
    tables = list(get_database_schema(get_engine()).keys())
    return {**get_database_info(), "tables": tables, "table_count": len(tables)}


def initialize_database() -> None:
    """Create and seed only the bundled demo database; never modify user DBs."""
    if not using_demo_database():
        return
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city TEXT NOT NULL,
                product TEXT NOT NULL,
                revenue REAL NOT NULL,
                sale_date TEXT NOT NULL
            )
        """))
        row_count = connection.execute(text("SELECT COUNT(*) FROM sales")).scalar_one()
        if row_count == 0:
            connection.execute(text("""
                INSERT INTO sales (city, product, revenue, sale_date) VALUES
                ('Delhi', 'Laptop', 120000, '2026-01-15'),
                ('Mumbai', 'Laptop', 95000, '2026-01-20'),
                ('Bangalore', 'Phone', 80000, '2026-02-03'),
                ('Delhi', 'Phone', 70000, '2026-02-10'),
                ('Mumbai', 'Tablet', 60000, '2026-02-18')
            """))


def test_connection() -> bool:
    with get_engine().connect() as connection:
        return connection.execute(text("SELECT 1")).scalar_one() == 1
