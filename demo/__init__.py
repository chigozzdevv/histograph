"""Reproducible reference ML environment for Histograph."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_ROOT = ROOT / "data"
RAW_DATA = DATA_ROOT / "raw" / "synthetic_mobile_money_transaction_dataset.csv"
PROCESSED_DATA = DATA_ROOT / "processed" / "momtsim_features.parquet"
DATA_MANIFEST = DATA_ROOT / "processed" / "manifest.json"
ARTIFACT_ROOT = ROOT / "artifacts"
MODEL_ARTIFACT = ARTIFACT_ROOT / "mobile_money_fraud.joblib"
MODEL_MANIFEST = ARTIFACT_ROOT / "model_manifest.json"
