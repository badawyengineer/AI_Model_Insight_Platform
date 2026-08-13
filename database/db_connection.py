"""
db_connection.py

Single source of truth for creating a SQLAlchemy engine connected to the
project's PostgreSQL database. Connection parameters (dbname, user) come
from config.yaml; host/port default to config.yaml but can be overridden
by DB_HOST/DB_PORT (Milestone 9: Docker Compose service names); the
password is read exclusively from the DB_PASSWORD environment variable —
it is never stored in any config file or committed to git.

Every module that needs a database connection (staging loader, warehouse
loader, future analytics scripts) should import `get_engine()` from here
rather than building its own connection string.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import Engine, create_engine

from config.config_loader import get_db_password, load_config

logger = logging.getLogger(__name__)


def build_connection_url(config: dict | None = None) -> str:
    """
    Build a PostgreSQL SQLAlchemy connection URL from config.yaml +
    environment variables.

    DB_PASSWORD is always required from the environment (see
    get_db_password). DB_HOST and DB_PORT are optional environment
    overrides on top of config.yaml's database.host/port - added for
    Milestone 9 (Docker), where the app container must reach Postgres
    by its Compose service name (e.g. "postgres") instead of
    "localhost", without hardcoding that into config.yaml. Local/bare-
    metal setups that don't set these env vars are unaffected.
    """
    config = config or load_config()
    db_cfg = config["database"]
    password = get_db_password()
    host = os.environ.get("DB_HOST", db_cfg["host"])
    port = os.environ.get("DB_PORT", db_cfg["port"])

    return (
        f"postgresql+psycopg2://{db_cfg['user']}:{password}"
        f"@{host}:{port}/{db_cfg['dbname']}"
    )


def get_engine(config: dict | None = None, echo: bool = False) -> Engine:
    """
    Create (but do not connect yet — SQLAlchemy engines are lazy) a
    SQLAlchemy Engine for the project's PostgreSQL database.

    Args:
        config: Optional pre-loaded config dict. Loads from config.yaml if omitted.
        echo: If True, SQLAlchemy logs every SQL statement (useful for debugging).

    Returns:
        A SQLAlchemy Engine instance.
    """
    url = build_connection_url(config)
    engine = create_engine(url, echo=echo, future=True)
    logger.info("Created SQLAlchemy engine for database")
    return engine


def test_connection(engine: Engine) -> bool:
    """Quick liveness check: SELECT 1 against the given engine."""
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection test succeeded")
        return True
    except Exception as e:
        logger.error("Database connection test failed: %s", e)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    eng = get_engine()
    ok = test_connection(eng)
    print("Connection OK" if ok else "Connection FAILED")
