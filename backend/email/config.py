"""Email configuration helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional
import os


@dataclass(frozen=True)
class EmailConfig:
    """Configuration for outbound email delivery."""

    provider_name: str
    from_email: str
    smtp_host: str
    smtp_port: int
    smtp_username: Optional[str]
    smtp_password: Optional[str]
    smtp_use_tls: bool
    app_base_url: str
    max_attempts: int
    backoff_seconds: float


def _to_bool(value: Optional[str], *, default: bool) -> bool:
    if value is None:
        return default
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


def _to_int(value: Optional[str], *, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise ValueError(f"Expected integer value, got {value!r}") from exc


def _to_float(value: Optional[str], *, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise ValueError(f"Expected float value, got {value!r}") from exc


def load_email_config(env: Optional[Mapping[str, str]] = None) -> EmailConfig:
    """Load :class:`EmailConfig` from environment variables."""

    env_mapping = os.environ if env is None else env

    provider_name = (env_mapping.get("EMAIL_PROVIDER") or "dev").strip().lower() or "dev"
    from_email = env_mapping.get("FROM_EMAIL", "noreply@example.com")

    smtp_host = env_mapping.get("SMTP_HOST", "localhost")
    smtp_port = _to_int(env_mapping.get("SMTP_PORT"), default=587)
    smtp_username = env_mapping.get("SMTP_USER") or None
    smtp_password = env_mapping.get("SMTP_PASS") or None
    smtp_use_tls = _to_bool(env_mapping.get("SMTP_USE_TLS"), default=True)

    app_base_url = env_mapping.get("APP_BASE_URL", "http://localhost:5173")

    max_attempts = max(1, _to_int(env_mapping.get("EMAIL_MAX_ATTEMPTS"), default=3))
    backoff_seconds = max(0.0, _to_float(env_mapping.get("EMAIL_RETRY_BACKOFF"), default=2.0))

    return EmailConfig(
        provider_name=provider_name,
        from_email=from_email,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=smtp_username,
        smtp_password=smtp_password,
        smtp_use_tls=smtp_use_tls,
        app_base_url=app_base_url.rstrip("/"),
        max_attempts=max_attempts,
        backoff_seconds=backoff_seconds,
    )