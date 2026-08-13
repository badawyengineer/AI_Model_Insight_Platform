# docker/app.Dockerfile
#
# Milestone 9: the "app" image. Contains this project's full code and
# dependencies (torch, torchvision, mlflow, pandas, sqlalchemy, ...).
# Every pipeline stage (generator, ETL, database staging, warehouse,
# mlops training/extraction) runs from this same image via
# `docker compose run --rm app python -m <module>` - there's no
# per-stage image, matching how the stages already share one venv
# when run outside Docker.
#
# Not a long-running service: docker-compose.yml defines `app` with no
# default command, meant to be invoked with `docker compose run`.

FROM python:3.12-slim

# libpq for psycopg2-binary's runtime dependency, build-essential for
# any package that needs to compile from source on an unusual platform.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only requirements first so dependency installation is cached
# across rebuilds that only change application code.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the actual project code.
COPY . .

# Directories the pipeline writes to at runtime; declared here so they
# exist even before any named volume is mounted over them.
RUN mkdir -p raw_data clean_data logs models

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# No CMD/ENTRYPOINT on purpose - every stage is invoked explicitly, e.g.:
#   docker compose run --rm app python -m generator.generate_experiments
#   docker compose run --rm app python -m mlops.experiments.train --config ...
#   docker compose run --rm app python -m warehouse.transform_load
