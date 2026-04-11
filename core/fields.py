"""Custom model fields for Quaterdeck."""

from __future__ import annotations

import base64
import hashlib
from typing import TYPE_CHECKING, Any

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

if TYPE_CHECKING:
    from django.db.backends.base.base import BaseDatabaseWrapper
    from django.db.models.expressions import Expression


def _fernet() -> Fernet:
    """Build a Fernet instance keyed from Django's SECRET_KEY."""
    raw = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


class EncryptedCharField(models.TextField):
    """TextField whose value is transparently encrypted at rest using Fernet."""

    def from_db_value(
        self,
        value: str | None,
        expression: Expression,  # noqa: ARG002
        connection: BaseDatabaseWrapper,  # noqa: ARG002
    ) -> str | None:
        if value is None:
            return None
        try:
            return _fernet().decrypt(value.encode()).decode()
        except (InvalidToken, Exception):
            # Return ciphertext as-is if decryption fails (e.g. key rotation).
            return value

    def get_prep_value(self, value: Any) -> str | None:
        if value is None or value == "":
            return value
        return _fernet().encrypt(value.encode()).decode()
