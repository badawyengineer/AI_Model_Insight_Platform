#!/bin/bash
# docker/postgres/init-airflow-db.sh
#
# Runs automatically on first container start (official postgres image
# executes every script in /docker-entrypoint-initdb.d/ once, only when
# the data directory is empty). POSTGRES_DB (set in docker-compose.yml)
# already creates the app's main database; this script adds a second
# database for Airflow's own metadata, so both share one Postgres
# server/container instead of needing two.

set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE airflow'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow')\gexec
EOSQL
