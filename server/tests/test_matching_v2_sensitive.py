from __future__ import annotations

import pytest

from app.core.secrets import clear_secret_cache
from app.modules.matching_v2.sensitive import (
    decrypt_eligibility_payload,
    encrypt_eligibility_payload,
)


def test_eligibility_payload_is_authenticated_and_encrypted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DALIJOB_ELIGIBILITY_ENCRYPTION_KEY", "test-only-key-material")
    clear_secret_cache()
    payload = {"work_authorizations": [{"country": "US", "status": "authorized"}]}

    encrypted = encrypt_eligibility_payload(payload)

    assert "authorized" not in encrypted
    assert decrypt_eligibility_payload(encrypted) == payload
    with pytest.raises(ValueError, match="could not be decrypted"):
        decrypt_eligibility_payload(encrypted[:-1] + ("A" if encrypted[-1] != "A" else "B"))


def test_eligibility_encryption_fails_closed_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DALIJOB_ELIGIBILITY_ENCRYPTION_KEY", raising=False)
    clear_secret_cache()

    with pytest.raises(RuntimeError, match="not configured"):
        encrypt_eligibility_payload({})
