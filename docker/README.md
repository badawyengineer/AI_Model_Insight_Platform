# Milestone 9 — Containerization (Docker)

One-command local spin-up of the whole platform: PostgreSQL, an MLflow
tracking server, the app image (generator/ETL/database/warehouse/mlops),
and Airflow (webserver + scheduler) — instead of the manual "install
Postgres, create a venv, install Airflow in a second venv" setup from
Milestones 1-8.

## Images

| Image | Dockerfile | Contains |
|---|---|---|
| `app` | `docker/app.Dockerfile` | This project's full code + deps (torch, mlflow, sqlalchemy, ...). Every pipeline stage runs from this one image. |
| `mlflow` | `docker/mlflow.Dockerfile` | A standalone MLflow tracking server — deliberately lightweight (no torch), just `mlflow` + a Postgres driver. |
| `airflow-*` | `docker/airflow.Dockerfile` | The official `apache/airflow` image with this project's `requirements.txt` installed directly into it. |

`postgres` uses the official `postgres:16` image unmodified, with an init
script (`docker/postgres/init-airflow-db.sh`) that creates a second
`airflow` database alongside the app's `ai_model_insight` one, so a
single Postgres container serves both.

## Design notes

- **The `app` image has no default command.** It's meant to be invoked
  per-stage with `docker compose run --rm app python -m <module>`,
  matching how every stage already works outside Docker — there's no
  hidden "run everything" entrypoint to keep in sync with the actual
  pipeline stages.
- **The `mlflow` image is intentionally separate from `app`.** The
  tracking server itself never needs torch/pandas, so keeping it
  minimal means it builds/rebuilds fast and independently of app code
  changes.
- **Airflow gets the project's dependencies installed directly into its
  own image**, unlike the bare-metal setup in `orchestration/README.md`
  (which deliberately keeps Airflow and the project in separate venvs
  so a plain host install of Airflow never carries torch). Inside
  Docker that reasoning doesn't apply — every service is already
  isolated in its own container regardless of what's installed inside
  it, so there's no benefit to a second image just to get a bare
  `python3`, only the extra maintenance of keeping it in sync.
- **`DB_HOST`/`DB_PORT` environment variable overrides** were added to
  `database/db_connection.py` for this milestone — Postgres is reachable
  by its Compose service name (`postgres`), not `localhost`, and
  `config.yaml` shouldn't hardcode an environment-specific value.
  Bare-metal setups that don't set these env vars are unaffected.

## Quick start

```bash
cp .env.example .env
# edit .env: set a real DB_PASSWORD, and generate a real AIRFLOW_SECRET_KEY:
#   python -c "import secrets; print(secrets.token_hex(30))"

docker compose up -d postgres mlflow
```

Wait for Postgres to report healthy (`docker compose ps`), then run the
pipeline stage by stage, exactly like the non-Docker instructions in the
root `README.md` — just prefixed with `docker compose run --rm app`:

```bash
docker compose run --rm app python -m generator.generate_experiments
docker compose run --rm app python -m mlops.experiments.train --config mlops/experiments/configs/exp01_baseline.yaml
# ...(repeat for exp02-exp06, or use mlops.pipeline.run_mlops_pipeline)
docker compose run --rm app python -m mlops.mlflow.extract_runs
docker compose run --rm app python -m etl.run_etl --include-mlflow
docker compose run --rm app python -m database.load_staging
docker compose run --rm app python -m warehouse.build_dim_date
docker compose run --rm app python -m warehouse.transform_load
docker compose run --rm app python -m warehouse.apply_analytics
```

Or run the whole thing in one shot:

```bash
docker compose run --rm app python -m mlops.pipeline.run_mlops_pipeline
docker compose run --rm app python -m warehouse.apply_analytics
```

Then bring up Airflow to schedule it instead of running commands by hand:

```bash
docker compose up -d airflow-init airflow-webserver airflow-scheduler
```

Open the UIs:
- **Airflow**: http://localhost:8080 (login: `admin` / `admin` — change
  this for anything beyond local testing)
- **MLflow**: http://localhost:5000
- **Postgres**: `localhost:5432` (or whatever `DB_PORT` you set), reachable
  with any Postgres client using the credentials in your `.env`

## Tearing down

```bash
docker compose down          # stop containers, keep data (named volumes)
docker compose down -v       # stop containers AND delete all data (fresh start)
```

## Tests

`tests/test_docker_compose.py` validates the compose file's structure
(services, volumes, env wiring, that every referenced Dockerfile exists)
without needing container-registry access. `tests/test_db_connection.py`
covers the `DB_HOST`/`DB_PORT` override logic directly. Both run with
plain `pytest` — no Docker required:

```bash
pytest tests/test_docker_compose.py tests/test_db_connection.py -v
```

Actually building/running the containers (`docker compose build` /
`docker compose up`) needs a real Docker install with access to Docker
Hub to pull the `python`, `postgres`, and `apache/airflow` base images —
verify that step yourself in an environment with normal internet access.
