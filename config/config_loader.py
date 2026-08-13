"""
config_loader.py

Single source of truth for loading and validating the platform's YAML
configuration. Every module (generator, etl, database, spark, warehouse)
should import `load_config()` from here instead of parsing YAML itself.

This keeps configuration access consistent and makes it trivial to swap
the config backend later (e.g. env-based overrides) without touching
every module that consumes it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """
    Load the platform YAML configuration file.

    Args:
        config_path: Path to the config YAML file. Defaults to
            `config/config.yaml` relative to this file.

    Returns:
        A nested dictionary representing the parsed configuration.

    Raises:
        FileNotFoundError: If the config file does not exist.
        yaml.YAMLError: If the config file is not valid YAML.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found at: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config or {}


def get_db_password() -> str:
    """
    Fetch the database password, preferring AWS Secrets Manager
    (Milestone 10: Cloud Deployment) and falling back to the plain
    DB_PASSWORD environment variable used by every earlier milestone.

    Credentials are never stored in config.yaml. If DB_PASSWORD_SECRET_ARN
    is set, the password is fetched from that Secrets Manager secret on
    every call (no caching, so a rotated secret takes effect on the next
    call without redeploying anything) via _get_password_from_secrets_manager.
    Otherwise, behavior is unchanged from Milestones 1-9: read
    DB_PASSWORD directly from the environment.

    boto3 is only imported when DB_PASSWORD_SECRET_ARN is actually set,
    so it stays an optional dependency (see requirements-cloud.txt) for
    anyone running locally or in Docker without AWS.

    Raises:
        RuntimeError: If neither DB_PASSWORD_SECRET_ARN nor DB_PASSWORD
            is set in the environment.
    """
    secret_arn = os.environ.get("DB_PASSWORD_SECRET_ARN")
    if secret_arn:
        return _get_password_from_secrets_manager(secret_arn)

    password = os.environ.get("DB_PASSWORD")
    if not password:
        raise RuntimeError(
            "Neither DB_PASSWORD_SECRET_ARN nor DB_PASSWORD is set. "
            "Set DB_PASSWORD in your shell or a local .env file (not "
            "committed to git) for local/Docker use, or DB_PASSWORD_SECRET_ARN "
            "to fetch it from AWS Secrets Manager (see docs/cloud-deployment.md)."
        )
    return password


def _get_password_from_secrets_manager(secret_arn: str) -> str:
    """
    Fetch a secret string from AWS Secrets Manager. Isolated into its own
    function so tests can mock it directly instead of needing real AWS
    credentials or a moto-mocked boto3 client wired through every caller.
    """
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError(
            "DB_PASSWORD_SECRET_ARN is set but boto3 isn't installed. "
            "Install it with: pip install -r requirements-cloud.txt"
        ) from exc

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_arn)
    return response["SecretString"]


if __name__ == "__main__":
    # Quick manual sanity check: `python config/config_loader.py`
    cfg = load_config()
    print("Loaded config sections:", list(cfg.keys()))
