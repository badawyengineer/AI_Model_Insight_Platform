"""
test_secrets_manager.py

Tests config_loader.get_db_password()'s Milestone 10 addition: fetching
the DB password from AWS Secrets Manager when DB_PASSWORD_SECRET_ARN is
set, instead of the plain DB_PASSWORD environment variable used by every
earlier milestone.

Uses moto to mock AWS Secrets Manager - no real AWS account, credentials,
or network access required. boto3/moto are optional dependencies (see
requirements-cloud.txt); this whole module is skipped if they're not
installed, since Secrets Manager integration itself is optional.
"""

from __future__ import annotations

import os

import pytest

boto3 = pytest.importorskip("boto3")
pytest.importorskip("moto", reason="moto is an optional dependency - see requirements-cloud.txt")

from moto import mock_aws

from config.config_loader import get_db_password


@pytest.fixture
def secretsmanager_client(monkeypatch):
    """A moto-mocked Secrets Manager client. moto intercepts boto3 calls
    entirely, so no real AWS credentials or network access are used."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        yield boto3.client("secretsmanager", region_name="us-east-1")


def test_get_db_password_fetches_from_secrets_manager(secretsmanager_client, monkeypatch):
    secret = secretsmanager_client.create_secret(
        Name="ai-model-insight/db-password", SecretString="super-secret-real-password"
    )

    monkeypatch.setenv("DB_PASSWORD_SECRET_ARN", secret["ARN"])
    monkeypatch.delenv("DB_PASSWORD", raising=False)

    assert get_db_password() == "super-secret-real-password"


def test_get_db_password_secrets_manager_arn_takes_priority_over_plain_env_var(
    secretsmanager_client, monkeypatch
):
    """If both are set, Secrets Manager wins - it's the more specific,
    more secure source, and matches the Milestone 10 cloud setup where
    DB_PASSWORD might still be set to something stale locally."""
    secret = secretsmanager_client.create_secret(
        Name="ai-model-insight/db-password", SecretString="from-secrets-manager"
    )

    monkeypatch.setenv("DB_PASSWORD_SECRET_ARN", secret["ARN"])
    monkeypatch.setenv("DB_PASSWORD", "stale-local-value")

    assert get_db_password() == "from-secrets-manager"


def test_get_db_password_falls_back_to_plain_env_var_without_arn(monkeypatch):
    """No DB_PASSWORD_SECRET_ARN set at all -> exact Milestone 1-9 behavior."""
    monkeypatch.delenv("DB_PASSWORD_SECRET_ARN", raising=False)
    monkeypatch.setenv("DB_PASSWORD", "plain-local-password")

    assert get_db_password() == "plain-local-password"


def test_get_db_password_raises_on_nonexistent_secret(secretsmanager_client, monkeypatch):
    fake_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:does-not-exist"
    monkeypatch.setenv("DB_PASSWORD_SECRET_ARN", fake_arn)

    with pytest.raises(Exception):  # moto raises botocore's ResourceNotFoundException
        get_db_password()
