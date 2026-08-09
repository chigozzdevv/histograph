# Model card: mobile-money-fraud-detection

## Intended use

This model is a reference workload for Histograph's release detection, investigation, incident
lifecycle, and recovery verification. It must not be used to approve, decline, score, or otherwise
make decisions about real people or transactions.

## Data and task

The task is binary transaction-fraud classification using the Synthetic Mobile Money Transaction
Dataset, version 2. The registered positive prediction class is `fraud`; the positive actual value
is `1`. Dataset attribution and license details are in [`data/README.md`](data/README.md).

Features include amount, transaction type, origin and recipient balances, balance deltas, and prior
account/recipient transaction velocities. Velocity windows exclude the current step to prevent
same-row leakage.

## Evaluation design

- chronological split, not random split;
- 24-hour label-delay gap between train and validation;
- another 24-hour gap between validation and test;
- candidate selection by validation average precision;
- decision threshold selected on validation under a maximum 5% false-positive rate;
- final healthy and injected-release results evaluated on held-out test rows;
- feature ablation, score PSI, feature PSI, and directional metric comparisons written to the
  generated `model_manifest.json`.

No fixed metric is claimed in this checked-in card because the dataset and model artifacts are not
committed. Run training and use the checksummed generated manifest as the evidence for that run.

## Failure injections

The primary scenario simulates an uncoordinated feature-unit conversion that scales `amount` by
100 without updating the model contract. The second scenario changes only the canary's decision
threshold. Both use identical held-out rows across control and candidate behavior, so input-row
composition is controlled.

## Limitations and risks

- Synthetic behavior and fraud prevalence do not represent a specific production system.
- Average precision, recall, and false-positive rate do not establish fairness or calibration.
- A controlled replay supports causal diagnosis of the injected failure; it does not eliminate all
  confounding in a real incident.
- DataHub lineage narrows candidate causes but is only as accurate and current as the metadata
  emitted by the owning teams.
