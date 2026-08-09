import json
from contextlib import AbstractContextManager
from typing import Any

from demo import download
from demo.provenance import DATASET_FILENAME


class FakeResponse(AbstractContextManager):
    def __init__(self, payload: Any):
        self._payload = json.dumps(payload).encode()

    def read(self, size: int = -1) -> bytes:
        return self._payload

    def __exit__(self, exc_type, exc_value, traceback):
        return None


def test_public_mendeley_file_list_resolves_the_pinned_file(monkeypatch) -> None:
    monkeypatch.setattr(
        download,
        "urlopen",
        lambda request, timeout: FakeResponse(
            [
                {
                    "filename": DATASET_FILENAME,
                    "content_details": {
                        "download_url": "https://data.mendeley.com/public-files/pinned"
                    },
                }
            ]
        ),
    )

    assert download._resolve_download_url() == ("https://data.mendeley.com/public-files/pinned")
