"""Minimal stub of the `email_validator` package for local testing."""
from __future__ import annotations

from dataclasses import dataclass


class EmailNotValidError(ValueError):
    """Exception raised when an email address fails validation."""


@dataclass
class ValidatedEmail:
    email: str
    original_email: str


def validate_email(email: str, allow_smtputf8: bool = True, allow_empty: bool = False) -> ValidatedEmail:
    if not email and allow_empty:
        return ValidatedEmail(email="", original_email="")
    if not email or "@" not in email:
        raise EmailNotValidError("Invalid email address")
    return ValidatedEmail(email=email, original_email=email)