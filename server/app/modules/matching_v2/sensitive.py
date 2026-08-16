from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.secrets import get_provider_secret


ENCRYPTION_VERSION = "aes256-gcm.v1"


def _key() -> bytes:
    material = get_provider_secret("DALIJOB_ELIGIBILITY_ENCRYPTION_KEY")
    if not material:
        raise RuntimeError("Eligibility encryption key is not configured.")
    return hashlib.sha256(material.encode("utf-8")).digest()


def encrypt_eligibility_payload(payload: dict) -> str:
    nonce = os.urandom(12)
    plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(_key()).encrypt(nonce, plaintext, ENCRYPTION_VERSION.encode("ascii"))
    return ":".join(
        (
            ENCRYPTION_VERSION,
            base64.urlsafe_b64encode(nonce).decode("ascii"),
            base64.urlsafe_b64encode(ciphertext).decode("ascii"),
        )
    )


def eligibility_payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "hmac-sha256:" + hmac.new(_key(), canonical, hashlib.sha256).hexdigest()


def decrypt_eligibility_payload(value: str) -> dict:
    try:
        version, nonce_text, ciphertext_text = value.split(":", 2)
        if version != ENCRYPTION_VERSION:
            raise ValueError("Unsupported eligibility encryption version.")
        plaintext = AESGCM(_key()).decrypt(
            base64.urlsafe_b64decode(nonce_text),
            base64.urlsafe_b64decode(ciphertext_text),
            version.encode("ascii"),
        )
        decoded = json.loads(plaintext)
    except Exception as exc:
        raise ValueError("Eligibility payload could not be decrypted.") from exc
    if not isinstance(decoded, dict):
        raise ValueError("Eligibility payload is not an object.")
    return decoded
