import hashlib
import json
from typing import Any


def stable_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()
