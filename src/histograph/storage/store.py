import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError


@dataclass(frozen=True)
class StoredArtifact:
    object_key: str
    sha256: str
    content_type: str
    size_bytes: int


class ArtifactStore:
    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        region: str,
        access_key_id: str | None,
        secret_access_key: str | None,
    ):
        self._bucket = bucket
        self._client: BaseClient = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

    async def ensure_bucket(self) -> None:
        await asyncio.to_thread(self._ensure_bucket)

    async def put_json(self, object_key: str, value: Any) -> StoredArtifact:
        payload = json.dumps(
            value,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        ).encode()
        digest = hashlib.sha256(payload).hexdigest()
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=object_key,
            Body=payload,
            ContentType="application/json",
            Metadata={"sha256": digest},
        )
        return StoredArtifact(
            object_key=object_key,
            sha256=digest,
            content_type="application/json",
            size_bytes=len(payload),
        )

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            self._client.create_bucket(Bucket=self._bucket)
