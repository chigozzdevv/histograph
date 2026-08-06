import base64
import json
import secrets
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from histograph.security.errors import SecretDecryptionError, SecurityConfigurationError


@dataclass(frozen=True)
class EncryptionKey:
    key_id: str
    key: bytes


class EnvelopeCipher:
    def __init__(self, keys: tuple[EncryptionKey, ...]):
        if not keys:
            raise SecurityConfigurationError("At least one encryption key is required")
        if len({key.key_id for key in keys}) != len(keys):
            raise SecurityConfigurationError("Encryption key identifiers must be unique")
        if any(len(key.key) != 32 for key in keys):
            raise SecurityConfigurationError("Encryption keys must decode to exactly 32 bytes")
        self._keys = {key.key_id: key.key for key in keys}
        self._active = keys[0]

    @classmethod
    def from_config(cls, value: str) -> "EnvelopeCipher":
        parsed: list[EncryptionKey] = []
        for entry in value.split(","):
            key_id, separator, encoded = entry.strip().partition(":")
            if not separator or not key_id or not encoded:
                raise SecurityConfigurationError(
                    "Encryption keys must use key-id:base64-key format"
                )
            try:
                key = base64.urlsafe_b64decode(encoded.encode())
            except ValueError as error:
                raise SecurityConfigurationError(
                    f"Encryption key {key_id} is not valid base64"
                ) from error
            parsed.append(EncryptionKey(key_id=key_id, key=key))
        return cls(tuple(parsed))

    def encrypt(self, plaintext: str, *, context: str) -> str:
        data_key = AESGCM.generate_key(bit_length=256)
        data_nonce = secrets.token_bytes(12)
        wrap_nonce = secrets.token_bytes(12)
        associated_data = context.encode()
        ciphertext = AESGCM(data_key).encrypt(data_nonce, plaintext.encode(), associated_data)
        wrapped_key = AESGCM(self._active.key).encrypt(
            wrap_nonce,
            data_key,
            associated_data + self._active.key_id.encode(),
        )
        envelope = {
            "version": 1,
            "key_id": self._active.key_id,
            "wrap_nonce": _encode(wrap_nonce),
            "wrapped_key": _encode(wrapped_key),
            "data_nonce": _encode(data_nonce),
            "ciphertext": _encode(ciphertext),
        }
        return json.dumps(envelope, separators=(",", ":"), sort_keys=True)

    def decrypt(self, envelope: str, *, context: str) -> str:
        try:
            payload = json.loads(envelope)
            if payload.get("version") != 1:
                raise SecretDecryptionError("Unsupported secret envelope version")
            key_id = payload["key_id"]
            key = self._keys.get(key_id)
            if key is None:
                raise SecretDecryptionError(f"Encryption key {key_id} is unavailable")
            associated_data = context.encode()
            data_key = AESGCM(key).decrypt(
                _decode(payload["wrap_nonce"]),
                _decode(payload["wrapped_key"]),
                associated_data + key_id.encode(),
            )
            plaintext = AESGCM(data_key).decrypt(
                _decode(payload["data_nonce"]),
                _decode(payload["ciphertext"]),
                associated_data,
            )
            return plaintext.decode()
        except SecretDecryptionError:
            raise
        except (InvalidTag, KeyError, TypeError, ValueError, UnicodeDecodeError) as error:
            raise SecretDecryptionError("Secret envelope could not be authenticated") from error


def generate_encryption_key(key_id: str = "local-v1") -> str:
    encoded = base64.urlsafe_b64encode(AESGCM.generate_key(bit_length=256)).decode()
    return f"{key_id}:{encoded}"


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode()


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode())
