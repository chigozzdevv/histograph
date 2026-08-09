# Histograph reference ML environment

This environment is a reproducible mobile-money fraud demonstration, not a credit-scoring product
and not a model intended for financial decisions. Fraud works well here because outcomes can be
delayed, releases can change feature contracts or decision thresholds, and recall, precision, and
false-positive costs are easy to explain.

## What is real

- The source is the versioned **Synthetic Mobile Money Transaction Dataset**, not hand-written demo
  rows. Small generated fixtures are used only in tests.
- DuckDB prepares the 149 MB CSV directly into compressed Parquet.
- Model selection compares logistic regression and histogram gradient boosting.
- The split is chronological: 55% train, a 24-hour outcome gap, validation through 75%, another
  24-hour gap, then test. No random train/test split is used.
- The decision threshold is chosen on validation data under a maximum 5% false-positive rate.
- Scenario rows come only from the held-out test period.
- DataHub contains the model-to-feature-to-source relationships and ownership. Histograph telemetry
  remains in ClickHouse; DataHub is not used as a telemetry database.

## Prepare the environment

```bash
uv sync --locked --dev --extra demo
uv run --extra demo python -m demo download-data
uv run --extra demo python -m demo prepare-data
uv run --extra demo python -m demo train
```

If Mendeley does not expose a public file URL to the API, download
`synthetic_mobile_money_transaction_dataset.csv` from the source page and either place it at
`demo/data/raw/` or pass its file URL with `--source-url`. The downloader never silently replaces
the source with another dataset.

Training writes `demo/artifacts/model_manifest.json`. A scenario is marked viable only if the model
beats prevalence, the released feature distribution moves, and held-out performance degrades by at
least 5% on recall, F1, or false-positive rate. The feature-release runner refuses a non-viable
artifact by default.

## Add the DataHub graph

Start DataHub using the root instructions, load `infra/datahub/.env`, then emit the dataset, feature
table, features, model, relationships, and technical ownership:

```bash
uvx --python 3.13 --from acryl-datahub==1.6.0 \
  python -m demo.bootstrap_datahub
```

The bootstrap prints the exact URNs. The API model registration stores the emitted model URN, and
investigations derive it from that registration. A caller cannot substitute an arbitrary URN.

## Run the release scenarios

Start the Histograph databases and API:

```bash
./scripts/compose.sh up -d postgres clickhouse redis
uv run uvicorn histograph.api.main:app --app-dir server/src
```

In another terminal, run the primary feature-release scenario:

```bash
uv run --extra demo python -m demo run-feature-release
```

To exercise the approved DataHub write-back path, start the API with
`HISTOGRAPH_DATAHUB_MCP_MUTATIONS_ENABLED=true` and add `--write-back`. Only the final
post-recovery investigation is saved; the pre-rollback probable-cause investigation remains
read-only.

The runner replays the exact same held-out rows three times:

1. healthy feature contract (`amount × 1`);
2. released feature contract (`amount × 100`);
3. rollback recovery (`amount × 1`).

It ingests the upstream change event, computes feature PSI, selects the largest directional
performance degradation, opens incidents, investigates with live DataHub lineage, records rollback,
runs a fresh recovery window, persists the verification checks, reinvestigates, and resolves only
after recovery.

Run the independent model-release scenario with:

```bash
uv run --extra demo python -m demo run-model-canary
```

That scenario serves v1 at 90% and v2 at 10%, runs both versions on the same held-out rows in the
same 15-minute window, and raises an incident when the v2 decision-threshold release loses recall.

## What “caused by the release” means

Histograph reports evidence in increasing strength:

1. **Detected:** a deterministic monitor crossed its threshold.
2. **Correlated/probable:** the release occurred before the signal and the changed asset is in the
   registered model's DataHub lineage, or the candidate lost against a same-window reference.
3. **Confirmed:** controlled inputs isolate the released behavior, the implicated release is rolled
   back, and a fresh recovery check passes.

Without DataHub, the same telemetry can prove degradation but cannot safely choose which upstream
release to roll back. Use `--skip-investigation` to show that boundary. The focused
`test_datahub_enabled_vs_disabled_ablation_changes_the_operational_decision` regression test proves
that enabling the graph changes the recommendation from “gather evidence” to “request approval to
roll back the lineage-matched release.”

## Reproducibility and limitations

- Generated data, prepared data, and model artifacts are ignored by Git; manifests include source
  and prepared-file SHA-256 hashes.
- The source is synthetic and has a much higher fraud prevalence than many deployed systems.
- The unit-change and threshold-change releases are deliberate failure injections.
- The replay demonstrates the incident-response system. It does not establish that this classifier
  is suitable, fair, calibrated, or lawful for real users.

See [`MODEL_CARD.md`](MODEL_CARD.md) and [`data/README.md`](data/README.md).
