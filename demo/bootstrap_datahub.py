"""Emit the reference model, feature, source dataset, ownership, and relationships.

Run this module with the pinned DataHub SDK rather than adding the large ingestion SDK
to Histograph's runtime dependencies:

uvx --python 3.13 --from acryl-datahub==1.6.0 python -m demo.bootstrap_datahub
"""

import json
import os
from importlib import import_module

from demo.datahub_metadata import (
    ACCOUNT_VELOCITY_FEATURE_URN,
    AMOUNT_FEATURE_URN,
    FEATURE_TABLE_URN,
    MODEL_URN,
    OWNER_URN,
    RAW_DATASET_URN,
)
from demo.provenance import DATASET_DOI, DATASET_PAGE, DATASET_VERSION


def main() -> None:
    mcp_module = import_module("datahub.emitter.mcp")
    emitter_module = import_module("datahub.emitter.rest_emitter")
    schema = import_module("datahub.metadata.schema_classes")
    MetadataChangeProposalWrapper = mcp_module.MetadataChangeProposalWrapper
    DatahubRestEmitter = emitter_module.DatahubRestEmitter
    DatasetPropertiesClass = schema.DatasetPropertiesClass
    MLFeaturePropertiesClass = schema.MLFeaturePropertiesClass
    MLFeatureDataTypeClass = schema.MLFeatureDataTypeClass
    MLFeatureTablePropertiesClass = schema.MLFeatureTablePropertiesClass
    MLModelPropertiesClass = schema.MLModelPropertiesClass
    OwnerClass = schema.OwnerClass
    OwnershipClass = schema.OwnershipClass
    emitter = DatahubRestEmitter(
        gms_server=os.getenv("HISTOGRAPH_DATAHUB_GMS_URL", "http://localhost:8080"),
        token=os.getenv("HISTOGRAPH_DATAHUB_GMS_TOKEN"),
    )
    emitter.test_connection()
    assets = {
        RAW_DATASET_URN: DatasetPropertiesClass(
            name="MoMTSim synthetic mobile-money transactions",
            description=(
                "Synthetic transaction data used only for the Histograph reliability demo. "
                f"Source DOI {DATASET_DOI}, dataset version {DATASET_VERSION}."
            ),
            externalUrl=DATASET_PAGE,
            customProperties={
                "license": "CC BY 4.0",
                "datasetVersion": str(DATASET_VERSION),
            },
        ),
        ACCOUNT_VELOCITY_FEATURE_URN: MLFeaturePropertiesClass(
            description=(
                "Count of transactions initiated by the account during steps [t-24, t-1]."
            ),
            dataType=MLFeatureDataTypeClass.CONTINUOUS,
            sources=[RAW_DATASET_URN],
            customProperties={
                "windowHours": "24",
                "excludesCurrentStep": "true",
                "owner": "risk-data-platform",
            },
        ),
        AMOUNT_FEATURE_URN: MLFeaturePropertiesClass(
            description="Transaction amount in the feature contract's declared currency unit.",
            dataType=MLFeatureDataTypeClass.CONTINUOUS,
            sources=[RAW_DATASET_URN],
            customProperties={"owner": "risk-data-platform"},
        ),
        FEATURE_TABLE_URN: MLFeatureTablePropertiesClass(
            description="Reference mobile-money transaction features for fraud detection.",
            mlFeatures=[AMOUNT_FEATURE_URN, ACCOUNT_VELOCITY_FEATURE_URN],
        ),
        MODEL_URN: MLModelPropertiesClass(
            name="mobile-money-fraud-detection",
            description=(
                "Reference binary fraud classifier for demonstrating release-aware ML "
                "incident response. It is not a financial decision system."
            ),
            type="BINARY_CLASSIFICATION",
            mlFeatures=[AMOUNT_FEATURE_URN, ACCOUNT_VELOCITY_FEATURE_URN],
            customProperties={
                "purpose": "Histograph reliability demonstration",
                "productionUse": "prohibited",
            },
        ),
    }
    for urn, aspect in assets.items():
        emitter.emit_mcp(MetadataChangeProposalWrapper(entityUrn=urn, aspect=aspect))
        emitter.emit_mcp(
            MetadataChangeProposalWrapper(
                entityUrn=urn,
                aspect=OwnershipClass(owners=[OwnerClass(owner=OWNER_URN, type="TECHNICAL_OWNER")]),
            )
        )
    print(
        json.dumps(
            {
                "status": "emitted",
                "model_urn": MODEL_URN,
                "changed_feature_urn": AMOUNT_FEATURE_URN,
                "feature_urns": [AMOUNT_FEATURE_URN, ACCOUNT_VELOCITY_FEATURE_URN],
                "feature_table_urn": FEATURE_TABLE_URN,
                "source_dataset_urn": RAW_DATASET_URN,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
