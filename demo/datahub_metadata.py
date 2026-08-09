"""Canonical DataHub identities used by the reference environment."""

RAW_DATASET_URN = "urn:li:dataset:(urn:li:dataPlatform:duckdb,momtsim.transactions,PROD)"
FEATURE_TABLE_URN = (
    "urn:li:mlFeatureTable:(urn:li:dataPlatform:feast,mobile_money_transaction_features)"
)
ACCOUNT_VELOCITY_FEATURE_URN = (
    "urn:li:mlFeature:(mobile_money_transaction_features,account_velocity_24h)"
)
AMOUNT_FEATURE_URN = "urn:li:mlFeature:(mobile_money_transaction_features,amount)"
MODEL_URN = "urn:li:mlModel:(urn:li:dataPlatform:mlflow,mobile-money-fraud-detection,PROD)"
OWNER_URN = "urn:li:corpuser:histograph-demo"
