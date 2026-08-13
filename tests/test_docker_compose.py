"""
test_docker_compose.py

Structural tests for the Milestone 9 Docker setup. These validate what's
possible without pulling base images from a container registry (this
project's CI/sandbox environments may have restricted network egress
that blocks Docker Hub specifically, while still allowing PyPI/GitHub) -
YAML structure, required services/volumes, env var wiring, and that
every Dockerfile referenced actually exists.

Full `docker compose up` / `docker compose build` verification (which
needs registry access) is a manual step - see docker/README.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"


@pytest.fixture(scope="module")
def compose_config() -> dict:
    with open(COMPOSE_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_compose_file_is_valid_yaml(compose_config):
    assert "services" in compose_config
    assert "volumes" in compose_config


def test_expected_services_are_defined(compose_config):
    expected = {
        "postgres",
        "mlflow",
        "app",
        "airflow-init",
        "airflow-webserver",
        "airflow-scheduler",
    }
    assert expected.issubset(compose_config["services"].keys())


def test_expected_named_volumes_are_defined(compose_config):
    expected = {"pgdata", "mlflow_data", "airflow_home"}
    assert expected.issubset(compose_config["volumes"].keys())


def test_every_referenced_dockerfile_exists(compose_config):
    for name, service in compose_config["services"].items():
        build = service.get("build")
        if build is None:
            continue
        dockerfile = REPO_ROOT / build["context"] / build["dockerfile"]
        assert dockerfile.is_file(), f"{name} references missing {dockerfile}"


def test_postgres_service_has_healthcheck(compose_config):
    """airflow-init and app both depend on postgres being healthy, not
    just started - a missing healthcheck would make that depends_on
    condition invalid at 'docker compose config' time."""
    assert "healthcheck" in compose_config["services"]["postgres"]


def test_app_and_airflow_services_get_db_and_mlflow_env(compose_config):
    for service_name in ("app", "airflow-init", "airflow-webserver", "airflow-scheduler"):
        env = compose_config["services"][service_name]["environment"]
        assert "DB_HOST" in env, f"{service_name} must set DB_HOST=postgres (see database/db_connection.py)"
        assert env["DB_HOST"] == "postgres"

    for service_name in ("app", "airflow-init", "airflow-webserver", "airflow-scheduler"):
        env = compose_config["services"][service_name]["environment"]
        assert "MLFLOW_TRACKING_URI" in env
        assert env["MLFLOW_TRACKING_URI"] == "http://mlflow:5000"


def test_airflow_services_share_the_same_environment_block(compose_config):
    """airflow-init/webserver/scheduler use a single YAML anchor
    (&airflow-common-env) so their env vars can't drift apart - this
    confirms the anchor actually resolved to identical content for all
    three after parsing, not just that they look similar in the source."""
    services = compose_config["services"]
    init_env = services["airflow-init"]["environment"]
    webserver_env = services["airflow-webserver"]["environment"]
    scheduler_env = services["airflow-scheduler"]["environment"]
    assert init_env == webserver_env == scheduler_env


def test_no_service_hardcodes_a_password(compose_config):
    """Every password must come from ${DB_PASSWORD}/.env, never a
    literal string in docker-compose.yml."""
    compose_text = COMPOSE_PATH.read_text()
    assert "${DB_PASSWORD" in compose_text
    # crude but effective: no quoted literal that looks like a real
    # hardcoded secret sitting next to PASSWORD/SECRET keys outside of
    # ${...} interpolation syntax
    for line in compose_text.splitlines():
        stripped = line.strip()
        if ("PASSWORD" in stripped or "SECRET_KEY" in stripped) and ":" in stripped:
            value = stripped.split(":", 1)[1].strip()
            assert "${" in value or value == "" or value.startswith("&"), (
                f"Possible hardcoded secret in docker-compose.yml: {stripped!r}"
            )


def test_env_example_has_no_real_secrets_and_matches_compose_vars(compose_config):
    env_example_path = REPO_ROOT / ".env.example"
    assert env_example_path.is_file()
    content = env_example_path.read_text()

    assert "DB_PASSWORD" in content
    assert "AIRFLOW_SECRET_KEY" in content
    # placeholder values should look like placeholders, not real secrets
    for line in content.splitlines():
        if line.startswith("DB_PASSWORD="):
            assert "changeme" in line
        if line.startswith("AIRFLOW_SECRET_KEY="):
            assert "changeme" in line


def test_dockerignore_excludes_generated_artifacts():
    dockerignore_path = REPO_ROOT / ".dockerignore"
    assert dockerignore_path.is_file()
    content = dockerignore_path.read_text()
    for pattern in (".git/", "venv/", "mlruns/", ".env"):
        assert pattern in content
