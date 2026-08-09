import hashlib
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from demo.provenance import (
    DATASET_API,
    DATASET_BYTES,
    DATASET_CITATION,
    DATASET_FILENAME,
    DATASET_LICENSE,
    DATASET_LICENSE_URL,
    DATASET_PAGE,
    DATASET_SHA256,
    DATASET_VERSION,
)


def download_dataset(destination: Path, source_url: str | None = None) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    resolved_url = source_url or os.getenv("HISTOGRAPH_DEMO_DATA_URL") or _resolve_download_url()
    request = Request(resolved_url, headers={"User-Agent": "histograph-demo/0.1"})
    digest = hashlib.sha256()
    size = 0
    partial = destination.with_suffix(f"{destination.suffix}.partial")
    try:
        with urlopen(request, timeout=60) as response, partial.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
    except (HTTPError, URLError, TimeoutError) as error:
        partial.unlink(missing_ok=True)
        raise RuntimeError(
            f"Unable to download MoMTSim data from {resolved_url}: {error}"
        ) from error
    checksum = digest.hexdigest()
    if size != DATASET_BYTES or checksum != DATASET_SHA256:
        partial.unlink(missing_ok=True)
        raise RuntimeError(
            "Downloaded dataset did not match the pinned version: "
            f"expected {DATASET_BYTES} bytes and {DATASET_SHA256}, got {size} bytes and "
            f"{checksum}"
        )
    partial.replace(destination)
    return {
        "source_url": resolved_url,
        "source_page": DATASET_PAGE,
        "source_version": DATASET_VERSION,
        "filename": destination.name,
        "bytes": size,
        "sha256": checksum,
        "license": DATASET_LICENSE,
        "license_url": DATASET_LICENSE_URL,
        "citation": DATASET_CITATION,
    }


def _resolve_download_url() -> str:
    headers = {
        "Accept": "application/vnd.mendeley-public-dataset.1+json",
        "User-Agent": "histograph-demo/0.1",
    }
    request = Request(DATASET_API, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "Could not resolve the public Mendeley file URL. Set HISTOGRAPH_DEMO_DATA_URL "
            f"to the download URL for {DATASET_FILENAME} from {DATASET_PAGE}."
        ) from error

    files = (
        payload
        if isinstance(payload, list)
        else payload.get("files")
        if isinstance(payload, dict)
        else None
    )
    if not isinstance(files, list):
        raise RuntimeError("Mendeley dataset metadata did not include a files list")
    for item in files:
        if not isinstance(item, dict) or item.get("filename") != DATASET_FILENAME:
            continue
        url = item.get("download_url")
        if isinstance(url, str):
            return url
        content_details = item.get("content_details")
        if isinstance(content_details, dict) and isinstance(
            content_details.get("download_url"), str
        ):
            return content_details["download_url"]
    raise RuntimeError(f"Mendeley metadata did not expose a download URL for {DATASET_FILENAME}")
