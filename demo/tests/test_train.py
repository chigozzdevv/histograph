import csv
from pathlib import Path

import joblib
from demo.data import prepare_dataset
from demo.train import train_reference_model


def test_reference_training_uses_temporal_partitions_and_persists_artifact(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "momtsim.csv"
    prepared_path = tmp_path / "prepared.parquet"
    data_manifest_path = tmp_path / "data-manifest.json"
    artifact_path = tmp_path / "fraud.joblib"
    model_manifest_path = tmp_path / "model-manifest.json"
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
        for step in range(800):
            for offset in range(4):
                account = f"account-{(step + offset) % 20}"
                amount = float(20 + ((step * 17 + offset * 31) % 500))
                fraud = int(amount > 390 or (step + offset) % 29 == 0)
                old_balance = 2_000.0
                writer.writerow(
                    [
                        step,
                        "TRANSFER" if offset % 2 else "PAYMENT",
                        amount,
                        account,
                        old_balance,
                        old_balance - amount,
                        f"recipient-{offset % 8}",
                        500.0,
                        500.0 + amount,
                        fraud,
                    ]
                )

    prepare_dataset(raw_path, prepared_path, data_manifest_path)
    manifest = train_reference_model(
        prepared_path,
        artifact_path,
        model_manifest_path,
        max_rows=3_200,
    )
    artifact = joblib.load(artifact_path)

    boundaries = manifest["split_boundaries"]
    assert boundaries["train_end"] < boundaries["validation_start"]
    assert boundaries["validation_end"] < boundaries["test_start"]
    assert manifest["split_rows"]["train"] >= 100
    assert manifest["split_rows"]["validation"] >= 100
    assert manifest["split_rows"]["test"] >= 100
    assert manifest["selected_estimator"] in {
        "logistic_regression",
        "hist_gradient_boosting",
    }
    assert artifact["threshold"] == manifest["threshold"]
    assert artifact["features"] == manifest["features"]
    assert artifact_path.with_name("replay.parquet").exists()
    assert manifest["replay"]["rows"] == manifest["split_rows"]["test"]
