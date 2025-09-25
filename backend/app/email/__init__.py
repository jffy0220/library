"""Compatibility layer exposing email utilities within the application package."""

from ...email.config import EmailConfig, load_email_config
from ...email.providers import (
    DevPrintProvider,
    EmailProvider,
    SESProvider,
    SMTPProvider,
    SendGridProvider,
    create_email_provider,
)
from ...email.renderer import render_email_digest, render_reply_notification

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