"""
run_mlops_pipeline.py

End-to-end Milestone 7 demonstration. Runs every experiment config in
mlops/experiments/configs/, extracts the resulting MLflow run metadata,
and pushes it through the *existing* ETL -> staging -> warehouse
pipeline built in Milestones 3-5 (nothing here re-implements those
stages - it only calls them).

Usage:
    python -m mlops.pipeline.run_mlops_pipeline
    python -m mlops.pipeline.run_mlops_pipeline --skip-training   # reuse existing MLflow runs
    python -m mlops.pipeline.run_mlops_pipeline --skip-db         # train + extract + ETL only, no Postgres needed
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml

from config.config_loader import load_config
from etl.run_etl import run_etl
from mlops.experiments.train import train_one_config
from mlops.mlflow.extract_runs import extract_runs, write_records
from mlops.mlflow.tracking import init_mlflow

logger = logging.getLogger(__name__)


def run_all_experiments(project_config: dict) -> list[str]:
    configs_dir = Path(project_config["mlops"]["configs_dir"])
    config_files = sorted(configs_dir.glob("*.yaml"))
    if not config_files:
        raise FileNotFoundError(f"No experiment configs found under {configs_dir}")

    run_ids = []
    for config_file in config_files:
        with open(config_file, "r", encoding="utf-8") as f:
            exp_config = yaml.safe_load(f)
        logger.info("=== Running experiment: %s ===", exp_config["name"])
        run_id = train_one_config(exp_config, project_config)
        run_ids.append(run_id)

    logger.info("Completed %d/%d experiment run(s)", len(run_ids), len(config_files))
    return run_ids


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    parser = argparse.ArgumentParser(description="Run the full Milestone 7 MLOps pipeline.")
    parser.add_argument(
        "--skip-training", action="store_true",
        help="Skip running new experiments; extract metadata from existing MLflow runs only.",
    )
    parser.add_argument(
        "--skip-db", action="store_true",
        help="Stop after the ETL step - don't touch PostgreSQL staging/warehouse.",
    )
    args = parser.parse_args()

    project_config = load_config()
    init_mlflow(project_config)

    if not args.skip_training:
        logger.info("=== STEP 1/4: RUN ML EXPERIMENTS ===")
        run_all_experiments(project_config)
    else:
        logger.info("=== STEP 1/4: SKIPPED (--skip-training) ===")

    logger.info("=== STEP 2/4: EXTRACT MLFLOW RUN METADATA ===")
    records = extract_runs(project_config)
    write_records(records, project_config["mlops"]["mlflow_raw_output_path"])

    logger.info("=== STEP 3/4: RUN EXISTING ETL (synthetic + mlflow merged) ===")
    run_etl(extra_sources=[project_config["mlops"]["mlflow_raw_output_path"]])

    if args.skip_db:
        logger.info("=== STEP 4/4: SKIPPED (--skip-db) ===")
        return

    logger.info("=== STEP 4/4: LOAD INTO EXISTING STAGING + WAREHOUSE ===")
    # Imported lazily so `--skip-db` never requires a reachable Postgres
    # / DB_PASSWORD env var just to import this module.
    from database.load_staging import run as load_staging_run
    from warehouse.build_dim_date import run as build_dim_date_run
    from warehouse.transform_load import run as transform_load_run

    load_staging_run()
    build_dim_date_run()
    transform_load_run()

    logger.info("=== MILESTONE 7 PIPELINE COMPLETE ===")


if __name__ == "__main__":
    main()
