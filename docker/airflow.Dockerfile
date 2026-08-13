# docker/airflow.Dockerfile
#
# Milestone 9: extends the official Airflow image with this project's
# own dependencies (torch, mlflow, ...) installed directly into it.
#
# This is a deliberate change from the bare-metal setup described in
# orchestration/README.md, where Airflow and the project intentionally
# use *separate* venvs so a plain host install of Airflow never needs
# to carry torch/mlflow. Inside Docker that reasoning doesn't apply:
# every service is already isolated in its own container regardless of
# what's installed inside it, so there's nothing to protect by keeping
# a second image around just to run "python3" - it only adds an extra
# image to build and keep in sync. The DAG file itself is unchanged:
# it still shells out to a configurable PYTHON_BIN, which here simply
# resolves to this image's own interpreter.

FROM apache/airflow:2.10.5-python3.12

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*
USER airflow

COPY --chown=airflow:root requirements.txt /opt/airflow/project-requirements.txt
RUN pip install --no-cache-dir -r /opt/airflow/project-requirements.txt

# The DAG file itself. The rest of the project code is bind-mounted at
# runtime (see docker-compose.yml's `app` volume, shared with the
# airflow services) rather than copied here, so code changes don't
# require rebuilding this image.
COPY orchestration/dags/ai_model_insight_pipeline_dag.py /opt/airflow/dags/
