# docker/mlflow.Dockerfile
#
# Milestone 9: a standalone MLflow tracking server, so training runs
# (from the `app` container) and the MLflow UI are both reachable over
# the network instead of writing to a local sqlite file only visible
# inside one container.
#
# Deliberately NOT based on the app image - the tracking server itself
# never needs torch/torchvision/pandas, just mlflow + a Postgres driver
# for its backend store. Keeping it separate makes this image small and
# fast to build/rebuild independently of app code changes.

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "mlflow>=2.10" "psycopg2-binary>=2.9"

EXPOSE 5000

# --backend-store-uri and --default-artifact-root are provided via
# command in docker-compose.yml (they reference the Postgres service
# name and a named volume path, both Compose-specific), not baked in
# here, so this image stays reusable outside Compose too.
