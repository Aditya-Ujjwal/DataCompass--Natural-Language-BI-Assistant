from dataclasses import dataclass
import re
import sqlite3

try:
    import sqlglot
    from sqlglot import exp
except ImportError:
    sqlglot = None
    exp = None


@dataclass
class SQLValidationResult:
    is_valid: bool
    message: str
    normalized_sql: str | None = None


def _schema_columns(schema: dict) -> dict[str, set[str]]:
    return {table: {column['name'] for column in columns} for table, columns in schema.items()}


def _fallback_validate(sql: str, schema: dict) -> SQLValidationResult:
    cleaned = sql.strip()
    statements = [part.strip() for part in cleaned.split(";") if part.strip()]
    if len(statements) != 1:
        return SQLValidationResult(False, "Only one SQL statement is allowed.")
    statement = statements[0]
    if not re.match(r"^(SELECT|WITH)\b", statement, re.IGNORECASE):
        return SQLValidationResult(False, "Only read-only SELECT queries are allowed.")
    if re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|ATTACH|DETACH|TRUNCATE)\b", statement, re.IGNORECASE):
        return SQLValidationResult(False, "Potentially destructive SQL operation detected.")
    try:
        conn = sqlite3.connect(":memory:")
        for table, columns in schema.items():
            column_defs = []
            for col in columns:
                name = col["name"].replace('"', '""')
                dtype = str(col.get("type", "TEXT")).upper()
                if not re.fullmatch(r"[A-Z0-9_ ()]+", dtype):
                    dtype = "TEXT"
                column_defs.append(f'"{name}" {dtype}')
            safe_table = str(table).replace('"', '""')
            conn.execute(f'CREATE TABLE "{safe_table}" ({", ".join(column_defs)})')
        conn.execute("EXPLAIN QUERY PLAN " + statement)
        conn.close()
        return SQLValidationResult(True, "SQL validation passed (SQLite parser fallback).", statement + ";")
    except sqlite3.Error as exc:
        message = str(exc)
        if "no such table" in message:
            return SQLValidationResult(False, f"Unknown table: {message.split(':', 1)[-1].strip()}.")
        if "no such column" in message:
            return SQLValidationResult(False, f"Unknown column: {message.split(':', 1)[-1].strip()}.")
        return SQLValidationResult(False, f"SQL syntax/schema error: {message}")


def validate_sql(sql: str, schema: dict, dialect: str = "SQLite") -> SQLValidationResult:
    """Allow a single read-only SELECT using only discovered tables/columns."""
    if not sql or not sql.strip():
        return SQLValidationResult(False, "SQL query is empty.")
    if sqlglot is None:
        if dialect.lower() not in {"sqlite", "sqlite3"}:
            return SQLValidationResult(
                False,
                "SQLGlot is required to validate non-SQLite SQL. Install backend requirements and retry.",
            )
        return _fallback_validate(sql, schema)
    read_dialect = {"sqlite": "sqlite", "postgresql": "postgres", "postgres": "postgres", "mysql": "mysql"}.get(dialect.lower(), "sqlite")
    try:
        statements = sqlglot.parse(sql, read=read_dialect)
    except Exception as exc:
        return SQLValidationResult(False, f"SQL syntax error: {exc}")
    if len(statements) != 1:
        return SQLValidationResult(False, "Only one SQL statement is allowed.")
    statement = statements[0]
    if not isinstance(statement, exp.Query):
        return SQLValidationResult(False, "Only read-only SELECT queries are allowed.")
    known_tables = set(schema)
    table_nodes = list(statement.find_all(exp.Table))
    tables = {table.name for table in table_nodes}
    unknown_tables = tables - known_tables
    if unknown_tables:
        return SQLValidationResult(False, f"Unknown table(s): {', '.join(sorted(unknown_tables))}.")
    schema_columns = _schema_columns(schema)
    aliases = {table.alias_or_name: table.name for table in table_nodes}
    select_aliases = {alias.alias for alias in statement.find_all(exp.Alias) if alias.alias}
    for column in statement.find_all(exp.Column):
        column_name = column.name
        table_name = column.table
        if not table_name and column_name in select_aliases:
            continue
        if not table_name:
            if not any(column_name in schema_columns.get(table, set()) for table in tables):
                return SQLValidationResult(False, f"Unknown column: {column_name}.")
            continue
        actual_table = aliases.get(table_name, table_name)
        if actual_table not in schema_columns:
            return SQLValidationResult(False, f"Unknown table reference: {table_name}.")
        if column_name not in schema_columns[actual_table]:
            return SQLValidationResult(False, f"Unknown column: {actual_table}.{column_name}.")
    return SQLValidationResult(True, "SQL validation passed.", statement.sql(dialect=read_dialect))
