import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb

from demo.provenance import (
    DATASET_CITATION,
    DATASET_DOI,
    DATASET_LICENSE,
    DATASET_LICENSE_URL,
    DATASET_PAGE,
    DATASET_VERSION,
)

_COLUMN_CANDIDATES = {
    "step": ("step",),
    "transaction_type": ("transactionType", "type"),
    "amount": ("amount",),
    "initiator": ("initiator", "startingClient", "nameOrig"),
    "old_balance_initiator": ("oldBalInitiator", "oldBalStartingClient", "oldbalanceOrg"),
    "new_balance_initiator": ("newBalInitiator", "newBalStartingClient", "newbalanceOrig"),
    "recipient": ("recipient", "destinationClient", "nameDest"),
    "old_balance_recipient": (
        "oldBalRecipient",
        "oldBalDestinationClient",
        "oldbalanceDest",
    ),
    "new_balance_recipient": (
        "newBalRecipient",
        "newBalDestinationClient",
        "newbalanceDest",
    ),
    "is_fraud": ("isFraud", "is_fraud"),
}


def prepare_dataset(raw_path: Path, output_path: Path, manifest_path: Path) -> dict[str, Any]:
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw dataset not found: {raw_path}")
    columns = _resolve_columns(raw_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()
    try:
        query = _feature_query(raw_path, columns)
        escaped_output = str(output_path).replace("'", "''")
        connection.execute(
            f"COPY ({query}) TO '{escaped_output}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        stats = connection.execute(
            """
            SELECT
                count(*) AS rows,
                sum(is_fraud) AS fraud_rows,
                min(step) AS min_step,
                max(step) AS max_step,
                avg(is_fraud) AS fraud_prevalence
            FROM read_parquet(?)
            """,
            [str(output_path)],
        ).fetchone()
    finally:
        connection.close()
    if stats is None:
        raise RuntimeError("Prepared dataset statistics were unavailable")
    manifest = {
        "dataset": {
            "name": "Synthetic Mobile Money Transaction Dataset",
            "doi": DATASET_DOI,
            "version": DATASET_VERSION,
            "source_page": DATASET_PAGE,
            "citation": DATASET_CITATION,
            "license": DATASET_LICENSE,
            "license_url": DATASET_LICENSE_URL,
            "raw_sha256": _sha256(raw_path),
        },
        "resolved_columns": columns,
        "prepared_file": output_path.name,
        "prepared_sha256": _sha256(output_path),
        "statistics": {
            "rows": int(stats[0]),
            "fraud_rows": int(stats[1]),
            "min_step": float(stats[2]),
            "max_step": float(stats[3]),
            "fraud_prevalence": float(stats[4]),
        },
        "feature_semantics": {
            "account_velocity_24h": (
                "prior transactions initiated by the account in steps [t-24, t-1]"
            ),
            "account_velocity_168h": (
                "prior transactions initiated by the account in steps [t-168, t-1]; "
                "retained as a diagnostic alternative window"
            ),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def _resolve_columns(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8-sig") as source:
        header = next(csv.reader(source))
    by_lower = {name.lower(): name for name in header}
    resolved: dict[str, str] = {}
    missing = []
    for target, candidates in _COLUMN_CANDIDATES.items():
        source_name = next(
            (
                by_lower[candidate.lower()]
                for candidate in candidates
                if candidate.lower() in by_lower
            ),
            None,
        )
        if source_name is None:
            missing.append(f"{target} ({', '.join(candidates)})")
        else:
            resolved[target] = source_name
    if missing:
        raise ValueError("Dataset is missing required columns: " + "; ".join(missing))
    return resolved


def _feature_query(raw_path: Path, columns: dict[str, str]) -> str:
    escaped_path = str(raw_path).replace("'", "''")

    def column(name: str) -> str:
        return '"' + columns[name].replace('"', '""') + '"'

    return f"""
        WITH normalized AS (
            SELECT
                CAST({column("step")} AS DOUBLE) AS step,
                CAST({column("transaction_type")} AS VARCHAR) AS transaction_type,
                CAST({column("amount")} AS DOUBLE) AS amount,
                CAST({column("initiator")} AS VARCHAR) AS initiator,
                CAST({column("old_balance_initiator")} AS DOUBLE) AS old_balance_initiator,
                CAST({column("new_balance_initiator")} AS DOUBLE) AS new_balance_initiator,
                CAST({column("recipient")} AS VARCHAR) AS recipient,
                CAST({column("old_balance_recipient")} AS DOUBLE) AS old_balance_recipient,
                CAST({column("new_balance_recipient")} AS DOUBLE) AS new_balance_recipient,
                CAST({column("is_fraud")} AS INTEGER) AS is_fraud
            FROM read_csv_auto('{escaped_path}', header = true, sample_size = -1)
        )
        SELECT
            *,
            old_balance_initiator - new_balance_initiator AS initiator_balance_delta,
            new_balance_recipient - old_balance_recipient AS recipient_balance_delta,
            count(*) OVER (
                PARTITION BY initiator ORDER BY step
                RANGE BETWEEN 24 PRECEDING AND 1 PRECEDING
            ) AS account_velocity_24h,
            count(*) OVER (
                PARTITION BY initiator ORDER BY step
                RANGE BETWEEN 168 PRECEDING AND 1 PRECEDING
            ) AS account_velocity_168h,
            count(*) OVER (
                PARTITION BY recipient ORDER BY step
                RANGE BETWEEN 24 PRECEDING AND 1 PRECEDING
            ) AS recipient_velocity_24h
        FROM normalized
    """


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
