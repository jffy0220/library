"""Email provider implementations used by the application."""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Optional

from .config import EmailConfig

logger = logging.getLogger(__name__)


class EmailProvider:
    """Base provider for outbound email delivery."""

    name = "base"

    def __init__(self, *, from_email: str) -> None:
        self.from_email = from_email

    def send_email(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> None:
        raise NotImplementedError

    def describe(self) -> Dict[str, str]:
        return {"email_provider": self.name, "email_sender": self.from_email}


class DevPrintProvider(EmailProvider):
    """Development provider that logs messages instead of sending them."""

    name = "dev"

    def send_email(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> None:  # pragma: no cover - trivial logging
        logger.info(
            "Dev email dispatch",
            extra={
                "email_recipient": to,
                "email_subject": subject,
                "email_sender": self.from_email,
            },
        )


class SMTPProvider(EmailProvider):
    """Simple SMTP-based provider for production use."""

    name = "smtp"

    def __init__(
        self,
        *,
        from_email: str,
        host: str,
        port: int,
        username: Optional[str],
        password: Optional[str],
        use_tls: bool,
    ) -> None:
        super().__init__(from_email=from_email)
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls

    def _build_message(self, to: str, subject: str, html_body: str, text_body: str) -> str:
        message = MIMEMultipart("alternative")
        message["From"] = self.from_email
        message["To"] = to
        message["Subject"] = subject
        message.attach(MIMEText(text_body, "plain", "utf-8"))
        message.attach(MIMEText(html_body, "html", "utf-8"))
        return message.as_string()

    def send_email(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> None:
        payload = self._build_message(to, subject, html_body, text_body)
        with smtplib.SMTP(self.host, self.port, timeout=30) as client:
            if self.use_tls:
                client.starttls()
            if self.username and self.password:
                client.login(self.username, self.password)
            client.sendmail(self.from_email, [to], payload)


class SendGridProvider(EmailProvider):
    name = "sendgrid"

    def __init__(self, *, from_email: str, api_key: str) -> None:
        super().__init__(from_email=from_email)
        self.api_key = api_key

    def send_email(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> None:
        raise NotImplementedError("SendGrid provider is not configured in this environment")


class SESProvider(EmailProvider):
    name = "ses"

    def __init__(self, *, from_email: str, region: str) -> None:
        super().__init__(from_email=from_email)
        self.region = region

    def send_email(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> None:
        raise NotImplementedError("SES provider is not configured in this environment")


def create_email_provider(config: EmailConfig) -> EmailProvider:
    provider = (config.provider_name or "dev").strip().lower()
    if provider == "smtp":
        return SMTPProvider(
            from_email=config.from_email,
            host=config.smtp_host,
            port=config.smtp_port,
            username=config.smtp_username,
            password=config.smtp_password,
            use_tls=config.smtp_use_tls,
        )
    if provider == "sendgrid":
        return SendGridProvider(from_email=config.from_email, api_key="")
    if provider == "ses":
        return SESProvider(from_email=config.from_email, region="")
    return DevPrintProvider(from_email=config.from_email)


__all__ = [
    "EmailProvider",
    "DevPrintProvider",
    "SMTPProvider",
    "SendGridProvider",
    "SESProvider",
    "create_email_provider",
]