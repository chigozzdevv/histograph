CREATE TABLE IF NOT EXISTS {database}.predictions (
    prediction_id String,
    model String,
    version String,
    environment String,
    deployment Nullable(String),
    observed_at DateTime64(3, 'UTC'),
    predicted_class Nullable(String),
    score Nullable(Float64),
    features_json String,
    tags_json String,
    latency_ms Nullable(Float64),
    error_state Nullable(String)
) ENGINE = MergeTree
ORDER BY (model, version, observed_at, prediction_id)
