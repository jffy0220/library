import importlib.metadata
import pathlib
import sys
from datetime import UTC, datetime

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_original_version = importlib.metadata.version


def _patched_version(distribution_name: str) -> str:
    if distribution_name == "email-validator":
        return "2.0.0"
    return _original_version(distribution_name)


importlib.metadata.version = _patched_version  # type: ignore[assignment]

from backend.app.email import (  # noqa: E402  pylint: disable=wrong-import-position
    DevPrintProvider,
    EmailProvider,
    SMTPProvider,
    create_email_provider,
    load_email_config,
)
from backend import main as backend_main  # noqa: E402  pylint: disable=wrong-import-positio


class _FailingProvider(EmailProvider):
    name = "failing"

    def __init__(self, exc: Exception) -> None:
        super().__init__(from_email="noreply@example.com")
        self._exc = exc

    def send_email(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> None:  # type: ignore[override]
        raise self._exc


def test_default_provider_is_dev_print():
    config = load_email_config(env={})
    provider = create_email_provider(config)
    assert isinstance(provider, DevPrintProvider)
    assert provider.from_email == "noreply@example.com"


def test_smtp_provider_configuration():
    config = load_email_config(
        env={
            "EMAIL_PROVIDER": "smtp",
            "SMTP_HOST": "mail.example.com",
            "SMTP_PORT": "2525",
            "SMTP_USER": "mailer",
            "SMTP_PASS": "secret",
            "FROM_EMAIL": "notifications@example.com",
        }
    )
    provider = create_email_provider(config)
    assert isinstance(provider, SMTPProvider)
    assert provider.host == "mail.example.com"
    assert provider.port == 2525
    assert provider.username == "mailer"
    assert provider.from_email == "notifications@example.com"


def test_email_send_errors_propagate():
    original = backend_main.get_email_provider()
    exc = RuntimeError("boom")
    failing = _FailingProvider(exc)
    backend_main.set_email_provider(failing)

    try:
        with pytest.raises(RuntimeError):
            backend_main.send_onboarding_email(
                email="user@example.com",
                username="user",
                token="tok",
                expires_at=datetime.now(UTC),
            )
    finally:
        backend_main.set_email_provider(original)