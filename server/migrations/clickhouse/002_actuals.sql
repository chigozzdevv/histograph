CREATE TABLE IF NOT EXISTS {database}.actuals (
    prediction_id String,
    actual String,
    observed_at DateTime64(3, 'UTC'),
    metadata_json String
) ENGINE = MergeTree
ORDER BY (prediction_id, observed_at)
