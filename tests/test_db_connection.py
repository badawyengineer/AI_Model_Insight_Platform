"""
test_db_connection.py

Tests database/db_connection.py's connection URL building, specifically
the DB_HOST/DB_PORT environment variable overrides added for Milestone 9
(Docker) - the app/airflow containers need to reach Postgres by its
Compose service name ("postgres") instead of config.yaml's "localhost",
without hardcoding that into config.yaml.
"""

from __future__ import annotations

from database.db_connection import build_connection_url

FAKE_CONFIG = {
    "database": {
        "host": "localhost",
        "port": 5432,
        "dbname": "ai_model_insight",
        "user": "postgres",
    }
}


def test_build_connection_url_uses_config_defaults(monkeypatch):
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.delenv("DB_PORT", raising=False)
    monkeypatch.setenv("DB_PASSWORD", "testpw")

    url = build_connection_url(FAKE_CONFIG)
    assert url == "postgresql+psycopg2://postgres:testpw@localhost:5432/ai_model_insight"


def test_build_connection_url_db_host_env_override(monkeypatch):
    """This is the Milestone 9 case: docker-compose.yml sets DB_HOST=postgres."""
    monkeypatch.setenv("DB_HOST", "postgres")
    monkeypatch.delenv("DB_PORT", raising=False)
    monkeypatch.setenv("DB_PASSWORD", "testpw")

    url = build_connection_url(FAKE_CONFIG)
    assert url == "postgresql+psycopg2://postgres:testpw@postgres:5432/ai_model_insight"


def test_build_connection_url_db_port_env_override(monkeypatch):
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.setenv("DB_PORT", "6543")
    monkeypatch.setenv("DB_PASSWORD", "testpw")

    url = build_connection_url(FAKE_CONFIG)
    assert url == "postgresql+psycopg2://postgres:testpw@localhost:6543/ai_model_insight"


def test_build_connection_url_requires_db_password(monkeypatch):
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    try:
        build_connection_url(FAKE_CONFIG)
        assert False, "expected RuntimeError when DB_PASSWORD is unset"
    except RuntimeError as exc:
        assert "DB_PASSWORD" in str(exc)
