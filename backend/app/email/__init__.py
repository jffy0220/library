"""Compatibility layer exposing email utilities within the application package."""

from ...mail.config import EmailConfig, load_email_config
from ...mail.providers import (
    DevPrintProvider,
    EmailProvider,
    SESProvider,
    SMTPProvider,
    SendGridProvider,
    create_email_provider,
)
from ...mail.renderer import render_email_digest, render_reply_notification

__all__ = [
    "DevPrintProvider",
    "EmailConfig",
    "EmailProvider",
    "SESProvider",
    "SMTPProvider",
    "SendGridProvider",
    "create_email_provider",
    "load_email_config",
    "render_email_digest",
    "render_reply_notification",
]