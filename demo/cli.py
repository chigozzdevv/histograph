import argparse
import json
from pathlib import Path
from typing import Any

from demo import (
    DATA_MANIFEST,
    MODEL_ARTIFACT,
    MODEL_MANIFEST,
    PROCESSED_DATA,
    RAW_DATA,
)
from demo.data import prepare_dataset
from demo.download import download_dataset
from demo.scenario import run_feature_release_scenario, run_model_canary_scenario
from demo.train import train_reference_model


def main() -> None:
    parser = argparse.ArgumentParser(description="Histograph reference ML environment")
    subparsers = parser.add_subparsers(dest="command", required=True)

    download_parser = subparsers.add_parser("download-data")
    download_parser.add_argument("--output", type=Path, default=RAW_DATA)
    download_parser.add_argument("--source-url")

    prepare_parser = subparsers.add_parser("prepare-data")
    prepare_parser.add_argument("--input", type=Path, default=RAW_DATA)
    prepare_parser.add_argument("--output", type=Path, default=PROCESSED_DATA)
    prepare_parser.add_argument("--manifest", type=Path, default=DATA_MANIFEST)

    train_parser = subparsers.add_parser("train")
    train_parser.add_argument("--input", type=Path, default=PROCESSED_DATA)
    train_parser.add_argument("--artifact", type=Path, default=MODEL_ARTIFACT)
    train_parser.add_argument("--manifest", type=Path, default=MODEL_MANIFEST)
    train_parser.add_argument("--max-rows", type=int, default=400_000)

    feature_parser = subparsers.add_parser("run-feature-release")
    _scenario_arguments(feature_parser)
    feature_parser.add_argument(
        "--allow-nonviable",
        action="store_true",
        help="Run for diagnosis even when the trained scenario failed its viability gates",
    )

    canary_parser = subparsers.add_parser("run-model-canary")
    _scenario_arguments(canary_parser)

    arguments = parser.parse_args()
    result: dict[str, Any]
    if arguments.command == "download-data":
        result = download_dataset(arguments.output, arguments.source_url)
    elif arguments.command == "prepare-data":
        result = prepare_dataset(arguments.input, arguments.output, arguments.manifest)
    elif arguments.command == "train":
        result = train_reference_model(
            arguments.input,
            arguments.artifact,
            arguments.manifest,
            max_rows=arguments.max_rows,
        )
    elif arguments.command == "run-feature-release":
        result = run_feature_release_scenario(
            arguments.api_url,
            arguments.input,
            arguments.artifact,
            sample_size=arguments.sample_size,
            investigate=not arguments.skip_investigation,
            write_back=arguments.write_back,
            allow_nonviable=arguments.allow_nonviable,
        )
    else:
        result = run_model_canary_scenario(
            arguments.api_url,
            arguments.input,
            arguments.artifact,
            sample_size=arguments.sample_size,
            investigate=not arguments.skip_investigation,
            write_back=arguments.write_back,
        )
    print(json.dumps(result, indent=2, sort_keys=True))


def _scenario_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--input", type=Path, default=PROCESSED_DATA)
    parser.add_argument("--artifact", type=Path, default=MODEL_ARTIFACT)
    parser.add_argument("--sample-size", type=int, default=500)
    parser.add_argument(
        "--skip-investigation",
        action="store_true",
        help="Run telemetry and detection without DataHub; causal attribution remains unavailable",
    )
    parser.add_argument(
        "--write-back",
        action="store_true",
        help=(
            "Persist the final post-recovery investigation in DataHub (requires mutations enabled)"
        ),
    )
