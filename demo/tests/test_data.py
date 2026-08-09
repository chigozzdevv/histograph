import csv
from pathlib import Path

import duckdb
from demo.data import prepare_dataset


def test_prepare_dataset_resolves_columns_and_uses_only_prior_steps(tmp_path: Path) -> None:
    raw_path = tmp_path / "momtsim.csv"
    prepared_path = tmp_path / "prepared.parquet"
    manifest_path = tmp_path / "manifest.json"
    rows = [
        [0, "PAYMENT", 10, "account-a", 100, 90, "merchant-a", 0, 10, 0],
        [1, "PAYMENT", 20, "account-a", 90, 70, "merchant-a", 10, 30, 0],
        [25, "TRANSFER", 30, "account-a", 70, 40, "account-b", 0, 30, 1],
        [26, "TRANSFER", 40, "account-a", 40, 0, "account-b", 30, 70, 1],
    ]
    with raw_path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target)
        writer.writerow(
            [
                "step",
                "transactionType",
                "amount",
                "initiator",
                "oldBalInitiator",
                "newBalInitiator",
                "recipient",
                "oldBalRecipient",
                "newBalRecipient",
                "isFraud",
            ]
        )
        writer.writerows(rows)

    manifest = prepare_dataset(raw_path, prepared_path, manifest_path)
    prepared = duckdb.sql(
        "SELECT step, account_velocity_24h, account_velocity_168h "
        "FROM read_parquet(?) ORDER BY step",
        params=[str(prepared_path)],
    ).fetchall()

    assert manifest["statistics"]["rows"] == 4
    assert manifest["statistics"]["fraud_rows"] == 2
    assert prepared == [(0.0, 0, 0), (1.0, 1, 1), (25.0, 1, 2), (26.0, 1, 3)]


def test_prepare_dataset_accepts_paysim_style_headers(tmp_path: Path) -> None:
    raw_path = tmp_path / "paysim.csv"
    prepared_path = tmp_path / "prepared.parquet"
    manifest_path = tmp_path / "manifest.json"
    raw_path.write_text(
        "step,type,amount,nameOrig,oldbalanceOrg,newbalanceOrig,nameDest,"
        "oldbalanceDest,newbalanceDest,isFraud\n"
        "1,TRANSFER,50,C1,100,50,C2,0,50,1\n",
        encoding="utf-8",
    )

    manifest = prepare_dataset(raw_path, prepared_path, manifest_path)

    assert manifest["resolved_columns"]["initiator"] == "nameOrig"
    assert manifest["statistics"]["rows"] == 1
