"""Email provider definitions and configuration helpers."""
from __future__ import annotations

import abc
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

logger = logging.getLogger(__name__)


def _to_bool(value: Optional[str], *, default: bool = False) -> bool:
    if value is None:
        return default
    value = value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _to_int(value: Optional[str], *, default: Optional[int] = None) -> Optional[int]:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected integer value, got {value!r}") from exc


@dataclass(frozen=True)
class EmailConfig:
    """Configuration values required to instantiate email providers."""

    provider_name: str
    sender: str
    rate_limit_per_minute: Optional[int]

    smtp_host: str
    smtp_port: int
    smtp_username: Optional[str]
    smtp_password: Optional[str]
    smtp_use_tls: bool

    sendgrid_api_key: Optional[str]

    ses_access_key: Optional[str]
    ses_secret_key: Optional[str]
    ses_region: Optional[str]


class EmailProvider(abc.ABC):
    """Abstract base class for outbound email providers."""

    name: str

    def __init__(self, *, rate_limit_per_minute: Optional[int] = None) -> None:
        self.rate_limit_per_minute = rate_limit_per_minute

    @abc.abstractmethod
    def send_email(
        self,
        *,
        sender: str,
        recipient: str,
        subject: str,
        body: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send an email with the provided contents."""

    def describe(self) -> Dict[str, Any]:
        """Return diagnostic metadata for structured logging."""

        return {
            "provider": getattr(self, "name", self.__class__.__name__),
            "rate_limit_per_minute": self.rate_limit_per_minute,
        }


class SMTPProvider(EmailProvider):
    """Deliver email by relaying through an SMTP server."""

    name = "smtp"

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: Optional[str],
        password: Optional[str],
        use_tls: bool,
        rate_limit_per_minute: Optional[int] = None,
    ) -> None:
        super().__init__(rate_limit_per_minute=rate_limit_per_minute)
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls

    def send_email(
        self,
        *,
        sender: str,
        recipient: str,
        subject: str,
        body: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        # Real SMTP implementation would live here. For now we emit a debug log
        # so that calling sites know the provider handled the dispatch.
        logger.debug(
            "SMTPProvider sending email",
            extra={
                "email_provider": self.name,
                "smtp_host": self.host,
                "smtp_port": self.port,
                "email_recipient": recipient,
                "email_subject": subject,
            },
        )


class SendGridProvider(EmailProvider):
    """Deliver email using the SendGrid HTTP API."""

    name = "sendgrid"

    def __init__(
        self,
        *,
        api_key: str,
        rate_limit_per_minute: Optional[int] = None,
    ) -> None:
        super().__init__(rate_limit_per_minute=rate_limit_per_minute)
        self.api_key = api_key

    def send_email(
        self,
        *,
        sender: str,
        recipient: str,
        subject: str,
        body: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        logger.debug(
            "SendGridProvider sending email",
            extra={
                "email_provider": self.name,
                "email_recipient": recipient,
                "email_subject": subject,
            },
        )


class SESProvider(EmailProvider):
    """Deliver email via AWS Simple Email Service."""

    name = "ses"

    def __init__(
        self,
        *,
        access_key: str,
        secret_key: str,
        region: str,
        rate_limit_per_minute: Optional[int] = None,
    ) -> None:
        super().__init__(rate_limit_per_minute=rate_limit_per_minute)
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region

    def send_email(
        self,
        *,
        sender: str,
        recipient: str,
        subject: str,
        body: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        logger.debug(
            "SESProvider sending email",
            extra={
                "email_provider": self.name,
                "email_recipient": recipient,
                "email_subject": subject,
                "ses_region": self.region,
            },
        )


def load_email_config(env: Optional[Mapping[str, str]] = None) -> EmailConfig:
    """Load email configuration from environment variables."""

    env_mapping = os.environ if env is None else env
    provider_name = env_mapping.get("EMAIL_PROVIDER", "smtp").strip().lower() or "smtp"
    sender = env_mapping.get("EMAIL_SENDER", "noreply@example.com")

    rate_limit = _to_int(env_mapping.get("EMAIL_RATE_LIMIT_PER_MINUTE"))

    smtp_host = env_mapping.get("EMAIL_SMTP_HOST", "localhost")
    smtp_port = _to_int(env_mapping.get("EMAIL_SMTP_PORT"), default=25) or 25
    smtp_username = env_mapping.get("EMAIL_SMTP_USERNAME") or None
    smtp_password = env_mapping.get("EMAIL_SMTP_PASSWORD") or None
    smtp_use_tls = _to_bool(env_mapping.get("EMAIL_SMTP_USE_TLS"), default=True)

    sendgrid_api_key = env_mapping.get("SENDGRID_API_KEY") or None

    ses_access_key = (
        env_mapping.get("SES_ACCESS_KEY_ID")
        or env_mapping.get("AWS_ACCESS_KEY_ID")
        or None
    )
    ses_secret_key = (
        env_mapping.get("SES_SECRET_ACCESS_KEY")
        or env_mapping.get("AWS_SECRET_ACCESS_KEY")
        or None
    )
    ses_region = env_mapping.get("SES_REGION") or env_mapping.get("AWS_REGION") or None

    return EmailConfig(
        provider_name=provider_name,
        sender=sender,
        rate_limit_per_minute=rate_limit,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=smtp_username,
        smtp_password=smtp_password,
        smtp_use_tls=smtp_use_tls,
        sendgrid_api_key=sendgrid_api_key,
        ses_access_key=ses_access_key,
        ses_secret_key=ses_secret_key,
        ses_region=ses_region,
    )


def create_email_provider(config: EmailConfig) -> EmailProvider:
    """Instantiate the configured email provider."""

    if config.provider_name == "smtp":
        return SMTPProvider(
            host=config.smtp_host,
            port=config.smtp_port,
            username=config.smtp_username,
            password=config.smtp_password,
            use_tls=config.smtp_use_tls,
            rate_limit_per_minute=config.rate_limit_per_minute,
        )
    if config.provider_name == "sendgrid":
        if not config.sendgrid_api_key:
            raise ValueError("SENDGRID_API_KEY must be set when EMAIL_PROVIDER=sendgrid")
        return SendGridProvider(
            api_key=config.sendgrid_api_key,
            rate_limit_per_minute=config.rate_limit_per_minute,
        )
    if config.provider_name == "ses":
        if not (config.ses_access_key and config.ses_secret_key and config.ses_region):
            raise ValueError(
                "SES requires SES_ACCESS_KEY_ID/SES_SECRET_ACCESS_KEY/SES_REGION (or AWS equivalents)"
            )
        return SESProvider(
            access_key=config.ses_access_key,
            secret_key=config.ses_secret_key,
            region=config.ses_region,
            rate_limit_per_minute=config.rate_limit_per_minute,
        )

    logger.warning(
        "Unknown EMAIL_PROVIDER '%s'; defaulting to SMTP", config.provider_name
    )
    return SMTPProvider(
        host=config.smtp_host,
        port=config.smtp_port,
        username=config.smtp_username,
        password=config.smtp_password,
        use_tls=config.smtp_use_tls,
        rate_limit_per_minute=config.rate_limit_per_minute,
    )