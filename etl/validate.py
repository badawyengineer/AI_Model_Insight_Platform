"""
validate.py

Validation stage of the ETL pipeline. Re-validates every raw record
against the ExperimentRecord schema (database/schemas.py), which is
the same single source of truth used by the generator. This is
intentional: even though our generator only produces valid records
today, a real pipeline can receive records from many upstream sources,
and validation must never assume the source is trustworthy.

Invalid records are not silently dropped — they're captured with their
validation error so they can be written to a rejects file for audit.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from database.schemas import ExperimentRecord

logger = logging.getLogger(__name__)


def validate_records(
    raw_records: list[dict[str, Any]],
) -> tuple[list[ExperimentRecord], list[dict[str, Any]]]:
    """
    Validate raw dicts against the ExperimentRecord schema.

    Args:
        raw_records: List of raw, unvalidated dicts.

    Returns:
        A tuple of (valid_records, rejected_records) where valid_records
        is a list of ExperimentRecord instances and rejected_records is
        a list of dicts containing the original record plus its
        validation error message, for audit purposes.
    """
    valid_records: list[ExperimentRecord] = []
    rejected_records: list[dict[str, Any]] = []

    for raw in raw_records:
        try:
            record = ExperimentRecord(**raw)
            valid_records.append(record)
        except ValidationError as e:
            rejected_records.append(
                {
                    "raw_record": raw,
                    "validation_error": str(e),
                }
            )
            logger.warning(
                "Rejected record (experiment_id=%s): %s",
                raw.get("experiment_id", "UNKNOWN"),
                e.errors()[0].get("msg", "unknown error"),
            )

    logger.info(
        "Validation complete: %d valid, %d rejected out of %d total",
        len(valid_records),
        len(rejected_records),
        len(raw_records),
    )
    return valid_records, rejected_records
