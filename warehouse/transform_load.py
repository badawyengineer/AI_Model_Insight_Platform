"""
transform_load.py

Transforms data from staging.experiments into the star schema warehouse:
  1. Ensures all warehouse tables exist.
  2. Upserts distinct dimension values (DimModel, DimDataset, DimHardware,
     DimFramework, DimResearcher, DimExperiment) — idempotent via
     ON CONFLICT DO NOTHING on each dimension's natural/unique key.
  3. Re-reads the dimension tables to build surrogate-key lookup maps.
  4. Builds FactTrainingRun rows by joining staging data against those
     lookup maps (in pandas) and derives date_key from each run's
     timestamp.
  5. Truncates and reloads FactTrainingRun (fact table is derived from
     staging + dims, so it's safe/expected to fully rebuild each run).

Assumes warehouse.dim_date has already been populated via
`python -m warehouse.build_dim_date` (run that first).

Usage:
    python -m warehouse.transform_load
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from config.config_loader import load_config
from database.db_connection import get_engine
from warehouse.warehouse_models import Base

logger = logging.getLogger(__name__)


def _setup_logging(level: str, log_file: str) -> None:
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )


def read_staging(engine, schema_name: str) -> pd.DataFrame:
    df = pd.read_sql(f"SELECT * FROM {schema_name}.experiments", con=engine)
    logger.info("Read %d rows from staging.experiments", len(df))
    return df


def upsert_dimension(
    engine,
    schema_name: str,
    table_name: str,
    conflict_columns: list[str],
    df: pd.DataFrame,
) -> None:
    """
    Generic upsert helper: loads `df` into a temp table, then
    INSERT ... ON CONFLICT (conflict_columns) DO NOTHING into the real
    dimension table. Surrogate keys are left to the DB's autoincrement.
    """
    tmp_table = f"_{table_name}_tmp"
    df.to_sql(tmp_table, con=engine, schema=schema_name, if_exists="replace", index=False)

    cols = ", ".join(df.columns)
    conflict_cols = ", ".join(conflict_columns)

    with engine.connect() as conn:
        conn.execute(
            text(
                f"""
                INSERT INTO {schema_name}.{table_name} ({cols})
                SELECT {cols} FROM {schema_name}.{tmp_table}
                ON CONFLICT ({conflict_cols}) DO NOTHING
                """
            )
        )
        conn.execute(text(f"DROP TABLE {schema_name}.{tmp_table}"))
        conn.commit()

    logger.info("Upserted into %s.%s", schema_name, table_name)


def build_and_load_dimensions(engine, schema_name: str, staging_df: pd.DataFrame) -> None:
    dim_model = staging_df[["model_name"]].drop_duplicates()
    upsert_dimension(engine, schema_name, "dim_model", ["model_name"], dim_model)

    dim_dataset = staging_df[["dataset"]].drop_duplicates().rename(columns={"dataset": "dataset_name"})
    upsert_dimension(engine, schema_name, "dim_dataset", ["dataset_name"], dim_dataset)

    dim_hardware = staging_df[["gpu", "cpu", "ram_gb"]].drop_duplicates()
    upsert_dimension(engine, schema_name, "dim_hardware", ["gpu", "cpu", "ram_gb"], dim_hardware)

    dim_framework = staging_df[["framework", "optimizer", "scheduler"]].drop_duplicates()
    upsert_dimension(
        engine, schema_name, "dim_framework", ["framework", "optimizer", "scheduler"], dim_framework
    )

    dim_researcher = (
        staging_df[["researcher"]].drop_duplicates().rename(columns={"researcher": "researcher_name"})
    )
    upsert_dimension(engine, schema_name, "dim_researcher", ["researcher_name"], dim_researcher)

    experiment_cols = ["experiment_id", "learning_rate", "batch_size", "epochs"]
    # source/mlflow_run_id/mlflow_experiment_name were added in Milestone 7.
    # Guard with a column check so this keeps working unmodified against
    # any staging table that predates the migration.
    for optional_col in ("source", "mlflow_run_id", "mlflow_experiment_name"):
        if optional_col in staging_df.columns:
            experiment_cols.append(optional_col)
    dim_experiment = staging_df[experiment_cols].drop_duplicates(subset="experiment_id")
    upsert_dimension(engine, schema_name, "dim_experiment", ["experiment_id"], dim_experiment)


def fetch_dim_lookup(
    engine, schema_name: str, table_name: str, key_col: str, natural_cols: list[str]
) -> pd.DataFrame:
    cols = ", ".join([key_col] + natural_cols)
    return pd.read_sql(f"SELECT {cols} FROM {schema_name}.{table_name}", con=engine)


def build_fact_dataframe(engine, schema_name: str, staging_df: pd.DataFrame) -> pd.DataFrame:
    df = staging_df.copy()

    model_lookup = fetch_dim_lookup(engine, schema_name, "dim_model", "model_key", ["model_name"])
    df = df.merge(model_lookup, on="model_name", how="left")

    dataset_lookup = fetch_dim_lookup(engine, schema_name, "dim_dataset", "dataset_key", ["dataset_name"])
    df = df.merge(dataset_lookup, left_on="dataset", right_on="dataset_name", how="left")

    hardware_lookup = fetch_dim_lookup(
        engine, schema_name, "dim_hardware", "hardware_key", ["gpu", "cpu", "ram_gb"]
    )
    df = df.merge(hardware_lookup, on=["gpu", "cpu", "ram_gb"], how="left")

    framework_lookup = fetch_dim_lookup(
        engine, schema_name, "dim_framework", "framework_key", ["framework", "optimizer", "scheduler"]
    )
    df = df.merge(framework_lookup, on=["framework", "optimizer", "scheduler"], how="left")

    researcher_lookup = fetch_dim_lookup(
        engine, schema_name, "dim_researcher", "researcher_key", ["researcher_name"]
    )
    df = df.merge(researcher_lookup, left_on="researcher", right_on="researcher_name", how="left")

    experiment_lookup = fetch_dim_lookup(
        engine, schema_name, "dim_experiment", "experiment_key", ["experiment_id"]
    )
    df = df.merge(experiment_lookup, on="experiment_id", how="left")

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date_key"] = df["timestamp"].dt.strftime("%Y%m%d").astype(int)

    fk_cols = ["model_key", "dataset_key", "hardware_key", "framework_key", "researcher_key", "experiment_key"]
    missing_fk = df[fk_cols].isna().any(axis=1)
    if missing_fk.any():
        logger.warning("%d rows have unresolved dimension keys and will be dropped", int(missing_fk.sum()))
        df = df.loc[~missing_fk]

    fact_columns = {
        "experiment_key": "experiment_key",
        "model_key": "model_key",
        "dataset_key": "dataset_key",
        "hardware_key": "hardware_key",
        "framework_key": "framework_key",
        "researcher_key": "researcher_key",
        "date_key": "date_key",
        "training_time_sec": "training_time_sec",
        "inference_time_ms": "inference_time_ms",
        "model_size_mb": "model_size_mb",
        "energy_consumption_kwh": "energy_consumption_kwh",
        "accuracy": "accuracy",
        "precision": "precision",
        "recall": "recall",
        "f1_score": "f1_score",
        "loss": "loss",
        "validation_loss": "validation_loss",
        "status": "status",
        "timestamp": "run_timestamp",
    }
    fact_df = df[list(fact_columns.keys())].rename(columns=fact_columns)

    for key_col in [
        "experiment_key", "model_key", "dataset_key",
        "hardware_key", "framework_key", "researcher_key", "date_key",
    ]:
        fact_df[key_col] = fact_df[key_col].astype(int)

    return fact_df


def load_fact_table(engine, schema_name: str, fact_df: pd.DataFrame) -> int:
    with engine.connect() as conn:
        conn.execute(text(f"TRUNCATE TABLE {schema_name}.fact_training_run RESTART IDENTITY"))
        conn.commit()

    fact_df.to_sql(
        "fact_training_run",
        con=engine,
        schema=schema_name,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=1000,
    )
    logger.info("Loaded %d rows into %s.fact_training_run", len(fact_df), schema_name)
    return len(fact_df)


def run() -> None:
    config = load_config()
    _setup_logging(
        level=config.get("logging", {}).get("level", "INFO"),
        log_file=config.get("logging", {}).get("log_file", "logs/pipeline.log"),
    )

    logger.info("=== WAREHOUSE TRANSFORM & LOAD START ===")

    staging_schema = config["database"]["staging_schema"]
    warehouse_schema = config["database"]["warehouse_schema"]
    engine = get_engine(config)

    with engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {warehouse_schema}"))
        conn.commit()
    Base.metadata.create_all(engine)

    staging_df = read_staging(engine, staging_schema)
    if staging_df.empty:
        logger.error("staging.experiments is empty. Run database.load_staging first. Aborting.")
        return

    build_and_load_dimensions(engine, warehouse_schema, staging_df)
    fact_df = build_fact_dataframe(engine, warehouse_schema, staging_df)
    row_count = load_fact_table(engine, warehouse_schema, fact_df)

    logger.info("=== WAREHOUSE TRANSFORM & LOAD COMPLETE: %d fact rows loaded ===", row_count)


if __name__ == "__main__":
    run()
