from __future__ import annotations

from typing import Any
from datetime import date, datetime, time as time_value
from decimal import Decimal

from sqlalchemy import MetaData, Table, inspect, select
from sqlalchemy.engine import Engine


def _table_names(inspector) -> list[tuple[str, str]]:
    """Return accessible base tables and views (views are queryable too)."""
    names: list[tuple[str, str]] = [(name, "table") for name in inspector.get_table_names()]
    try:
        names.extend((name, "view") for name in inspector.get_view_names())
    except Exception:
        pass
    # Preserve order while removing duplicates.
    seen: set[str] = set()
    return [(name, kind) for name, kind in names if not (name in seen or seen.add(name))]


def get_database_schema(engine: Engine) -> dict[str, list[dict[str, Any]]]:
    """Discover every accessible table/view, column type, PK and FK metadata."""
    inspector = inspect(engine)
    schema: dict[str, list[dict[str, Any]]] = {}

    for table_name, _kind in _table_names(inspector):
        raw_columns = inspector.get_columns(table_name)
        try:
            pk_columns = set((inspector.get_pk_constraint(table_name) or {}).get("constrained_columns") or [])
        except Exception:
            pk_columns = set()

        foreign_key_by_column: dict[str, list[dict[str, str]]] = {}
        try:
            foreign_keys = inspector.get_foreign_keys(table_name) or []
        except Exception:
            foreign_keys = []
        for fk in foreign_keys:
            local_columns = fk.get("constrained_columns") or []
            remote_columns = fk.get("referred_columns") or []
            remote_table = fk.get("referred_table")
            if not remote_table:
                continue
            for index, local_column in enumerate(local_columns):
                if index < len(remote_columns):
                    foreign_key_by_column.setdefault(local_column, []).append({
                        "table": remote_table,
                        "column": remote_columns[index],
                    })

        columns: list[dict[str, Any]] = []
        for column in raw_columns:
            name = column["name"]
            columns.append({
                "name": name,
                "type": str(column.get("type", "UNKNOWN")),
                "nullable": bool(column.get("nullable", True)),
                "primary_key": name in pk_columns,
                "foreign_keys": foreign_key_by_column.get(name, []),
            })
        schema[table_name] = columns

    return schema


def get_database_relationships(
    engine: Engine,
    schema: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, str]]:
    """Discover declared foreign keys and infer safe, obvious *_id/*_key links.

    Inferred relationships are only added when the same key column exists in
    exactly two tables and at least one side marks it as a primary key. This
    avoids guessing joins from arbitrary same-named columns.
    """
    schema = schema or get_database_schema(engine)
    relationships: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for table_name, columns in schema.items():
        for column in columns:
            for fk in column.get("foreign_keys", []):
                edge = (table_name, column["name"], fk["table"], fk["column"])
                if fk["table"] in schema and edge not in seen:
                    seen.add(edge)
                    relationships.append({
                        "from_table": edge[0],
                        "from_column": edge[1],
                        "to_table": edge[2],
                        "to_column": edge[3],
                        "source": "foreign_key",
                    })

    # Carefully infer simple key links for SQLite databases without declared FKs.
    key_locations: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for table_name, columns in schema.items():
        for column in columns:
            col_name = str(column["name"])
            lower = col_name.lower()
            if lower.endswith(("_id", "_key", "id", "key")) and lower not in {"id", "key"}:
                key_locations.setdefault(lower, []).append((table_name, column))

    for key_name, locations in key_locations.items():
        if len(locations) < 2:
            continue
        primary_locations = [location for location in locations if location[1].get("primary_key")]
        if len(primary_locations) == 1:
            # One dimension-table PK can safely link to several fact tables.
            parent_table, parent_column = primary_locations[0]
            for child_table, child_column in locations:
                if child_table == parent_table:
                    continue
                edge = (child_table, child_column["name"], parent_table, parent_column["name"])
                reverse = (parent_table, parent_column["name"], child_table, child_column["name"])
                if edge in seen or reverse in seen:
                    continue
                seen.add(edge)
                relationships.append({
                    "from_table": edge[0], "from_column": edge[1],
                    "to_table": edge[2], "to_column": edge[3],
                    "source": "inferred_shared_key",
                })
        elif len(locations) == 2 and any(column.get("primary_key") for _, column in locations):
            (left_table, left_column), (right_table, right_column) = locations
            edge = (left_table, left_column["name"], right_table, right_column["name"])
            reverse = (right_table, right_column["name"], left_table, left_column["name"])
            if edge in seen or reverse in seen:
                continue
            seen.add(edge)
            relationships.append({
                "from_table": edge[0], "from_column": edge[1],
                "to_table": edge[2], "to_column": edge[3],
                "source": "inferred_shared_key",
            })

    return relationships


def get_database_profile(engine: Engine) -> dict[str, Any]:
    """Build a complete metadata catalog for the connected database.

    This deliberately profiles structure and relationships, not row contents.
    That gives the assistant knowledge of all tables without copying potentially
    sensitive records into prompts or the browser.
    """
    schema = get_database_schema(engine)
    relationships = get_database_relationships(engine, schema)
    inspector = inspect(engine)
    kinds = dict(_table_names(inspector))

    tables = []
    for table_name, columns in schema.items():
        tables.append({
            "name": table_name,
            "kind": kinds.get(table_name, "table"),
            "column_count": len(columns),
            "columns": columns,
        })

    return {
        "database_type": engine.dialect.name,
        "dialect": engine.dialect.name,
        "table_count": len(tables),
        "tables": tables,
        "relationships": relationships,
        "schema": schema,
    }


def print_database_schema(engine: Engine) -> None:
    """Print a human-readable catalog for debugging and student learning."""
    profile = get_database_profile(engine)
    print(f"Database dialect: {profile['database_type']}")
    print(f"Discovered {profile['table_count']} tables/views")
    for table in profile["tables"]:
        print(f"\n{table['kind'].title()}: {table['name']}")
        for column in table["columns"]:
            flags = []
            if column["primary_key"]:
                flags.append("PRIMARY KEY")
            if column["foreign_keys"]:
                flags.append("FOREIGN KEY")
            suffix = f" ({', '.join(flags)})" if flags else ""
            print(f"  - {column['name']} | {column['type']}{suffix}")
    if profile["relationships"]:
        print("\nRelationships:")
        for edge in profile["relationships"]:
            print(
                f"  - {edge['from_table']}.{edge['from_column']} -> "
                f"{edge['to_table']}.{edge['to_column']} ({edge['source']})"
            )


def _preview_json_value(value: Any) -> Any:
    """Convert common DB-driver values to JSON-safe values."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime, date, time_value)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def preview_table(engine: Engine, table_name: str, limit: int = 5) -> dict[str, Any]:
    """Return a small, read-only preview of one discovered table or view.

    This is an explicit user-triggered preview, not a full table download.
    SQLAlchemy reflects and quotes the discovered table/column identifiers.
    """
    schema = get_database_schema(engine)
    if table_name not in schema:
        raise KeyError(f"Table or view '{table_name}' was not found in the connected database catalog.")

    safe_limit = max(1, min(int(limit), 20))
    reflected = Table(table_name, MetaData(), autoload_with=engine)
    statement = select(reflected).limit(safe_limit + 1)

    with engine.connect() as connection:
        result = connection.execute(statement)
        columns = list(result.keys())
        fetched = result.fetchmany(safe_limit + 1)

    truncated = len(fetched) > safe_limit
    rows = [
        [_preview_json_value(value) for value in row]
        for row in fetched[:safe_limit]
    ]
    return {
        "table": table_name,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "preview_limit": safe_limit,
        "truncated": truncated,
    }
