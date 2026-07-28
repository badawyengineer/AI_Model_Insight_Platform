"""
clean.py

Cleaning stage of the ETL pipeline. Takes validated ExperimentRecord
objects and:
  1. Deduplicates by experiment_id (keeps first occurrence).
  2. Handles missing metric values on records where they're NOT expected
     to be missing (i.e. SUCCESS/FAILED records with null metrics — a
     genuine data quality issue, unlike RUNNING/KILLED which are
     legitimately incomplete by design).

The missing-value strategy is config-driven (etl.missing_value_strategy
in config.yaml): "median" imputes with the column median (computed per
status group so we don't blend failed-run metrics into success-run
medians), "drop" removes the offending rows, "flag" leaves the value
null but adds a boolean `_imputed_flag` style marker via a dedicated
quality column.
"""

from __future__ import annotations

import logging

import pandas as pd

from database.schemas import ExperimentRecord

logger = logging.getLogger(__name__)

# Metrics that should be present for SUCCESS/FAILED runs (not expected
# to be missing there — only legitimately null for RUNNING/KILLED).
METRIC_COLUMNS = ["accuracy", "precision", "recall", "f1_score", "loss", "validation_loss"]
STATUSES_EXPECTING_METRICS = {"success", "failed"}


def records_to_dataframe(records: list[ExperimentRecord]) -> pd.DataFrame:
    """Convert validated ExperimentRecord objects into a flat pandas DataFrame."""
    rows = [r.model_dump() for r in records]
    df = pd.DataFrame(rows)
    df["status"] = df["status"].apply(lambda s: s.value if hasattr(s, "value") else s)
    return df


def deduplicate(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop duplicate experiment_id rows, keeping the first occurrence."""
    before = len(df)
    df = df.drop_duplicates(subset="experiment_id", keep="first").reset_index(drop=True)
    removed = before - len(df)
    if removed:
        logger.info("Removed %d duplicate records by experiment_id", removed)
    return df, removed


def handle_missing_metrics(df: pd.DataFrame, strategy: str) -> tuple[pd.DataFrame, int]:
    """
    Handle unexpected missing metrics on SUCCESS/FAILED rows.

    Returns:
        Tuple of (cleaned_df, affected_row_count).
    """
    expecting_mask = df["status"].isin(STATUSES_EXPECTING_METRICS)
    missing_mask = df[METRIC_COLUMNS].isna().any(axis=1) & expecting_mask
    affected = int(missing_mask.sum())

    if affected == 0:
        logger.info("No unexpected missing metrics found on SUCCESS/FAILED records")
        return df, 0

    logger.info(
        "Found %d SUCCESS/FAILED records with unexpected missing metrics "
        "(strategy=%s)",
        affected,
        strategy,
    )

    if strategy == "drop":
        df = df.loc[~missing_mask].reset_index(drop=True)

    elif strategy == "median":
        for status_val in STATUSES_EXPECTING_METRICS:
            status_mask = df["status"] == status_val
            for col in METRIC_COLUMNS:
                median_val = df.loc[status_mask, col].median()
                fill_mask = status_mask & df[col].isna()
                df.loc[fill_mask, col] = median_val

    elif strategy == "flag":
        df["data_quality_flag"] = missing_mask
        # leave the nulls as-is; downstream consumers can filter on the flag

    else:
        raise ValueError(
            f"Unknown missing_value_strategy: {strategy!r}. "
            "Expected one of: 'median', 'drop', 'flag'."
        )

    return df, affected


def clean_records(records: list[ExperimentRecord], missing_value_strategy: str) -> pd.DataFrame:
    """
    Full cleaning pipeline: records -> DataFrame -> dedup -> missing value handling.
    """
    df = records_to_dataframe(records)
    df, _ = deduplicate(df)
    df, _ = handle_missing_metrics(df, missing_value_strategy)
    return df
