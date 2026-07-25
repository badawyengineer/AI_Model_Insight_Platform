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
    Fetch the database password from the environment.

    Credentials are never stored in config.yaml. This function is the
    single point where the DB_PASSWORD environment variable is read.

    Raises:
        RuntimeError: If DB_PASSWORD is not set in the environment.
    """
    password = os.environ.get("DB_PASSWORD")
    if not password:
        raise RuntimeError(
            "DB_PASSWORD environment variable is not set. "
            "Set it in your shell or in a local .env file (not committed to git)."
        )
    return password


if __name__ == "__main__":
    # Quick manual sanity check: `python config/config_loader.py`
    cfg = load_config()
    print("Loaded config sections:", list(cfg.keys()))
