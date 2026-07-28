"""
extract.py

Extraction stage of the ETL pipeline. Reads the raw synthetic (or, in a
real deployment, upstream-reported) experiment logs from disk.

Deliberately dumb: this stage does zero validation or cleaning. Its only
job is "get the raw records into Python dicts." Keeping extraction and
validation as separate stages means either can be swapped independently
(e.g. extracting from a database or API later instead of a JSON file)
without touching validation logic.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def extract_raw_records(input_path: str | Path) -> list[dict[str, Any]]:
    """
    Load raw experiment records from a JSON file.

    Args:
        input_path: Path to the raw JSON file (list of experiment dicts).

    Returns:
        List of raw, unvalidated dicts.

    Raises:
        FileNotFoundError: If the input file doesn't exist.
        json.JSONDecodeError: If the file isn't valid JSON.
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(
            f"Raw data file not found at: {input_path}. "
            "Run `python -m generator.generate_experiments` first."
        )

    with open(input_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    if not isinstance(records, list):
        raise ValueError(
            f"Expected a JSON list of records in {input_path}, got {type(records)}"
        )

    logger.info("Extracted %d raw records from %s", len(records), input_path)
    return records
