from sqlalchemy import create_engine
import pandas as pd

from utils.connections import _require_env


def get_engine():
    """SQLAlchemy engine for the docker-compose Postgres (general user, write access)."""
    user = _require_env("user")
    password = _require_env("password")
    host = _require_env("host")
    port = _require_env("port")
    database = _require_env("database")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
    return create_engine(url)


def write_dataframe(df: pd.DataFrame, table_name: str, schema: str = "public", if_exists: str = "replace") -> str:
    engine = get_engine()
    try:
        df.to_sql(table_name, engine, schema=schema, if_exists=if_exists, index=False)
        return f"{len(df)} rows written to {schema}.{table_name}"
    finally:
        engine.dispose()


def read_dataframe(table_name: str, schema: str = "public", limit: int | None = None) -> pd.DataFrame:
    engine = get_engine()
    try:
        query = f'SELECT * FROM "{schema}"."{table_name}"'
        if limit is not None:
            query += f" LIMIT {limit}"
        return pd.read_sql(query, engine)
    finally:
        engine.dispose()