import os

from utils.database import DataBaseUtil


def _require_env(name: str) -> str:
    """Read an environment variable and fail early with a clear error message
    if it's missing, instead of a bare KeyError buried inside a node function.
    """
    value = os.environ.get(name)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_schema_db() -> DataBaseUtil:
    """Connection used to read database metadata (schema, sample data).
    Uses the general-purpose DB user, not the restricted AI user.
    """
    conn_details = {
        "host": _require_env("host"),
        "port": int(_require_env("port")),
        "user": _require_env("user"),
        "password": _require_env("password"),
        "dbname": _require_env("database"),
    }
    return DataBaseUtil(conn_details)


def get_execution_db() -> DataBaseUtil:
    """Connection used to actually execute the generated SQL.
    Uses the restricted, read-only AI user.
    """
    conn_details = {
        "host": _require_env("host"),
        "port": int(_require_env("port")),
        "database": _require_env("database"),
        "user": _require_env("ai_user"),
        "password": _require_env("ai_password"),
    }
    return DataBaseUtil(conn_details)