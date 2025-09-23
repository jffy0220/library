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

from backend.email_service.providers import (
    EmailProvider,
    SMTPProvider,
    SendGridProvider,
    create_email_provider,
    load_email_config,
)
from backend import main as backend_main


class _FailingProvider(EmailProvider):
    name = "failing"

    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self._exc = exc

    def send_email(
        self,
        *,
        sender: str,
        recipient: str,
        subject: str,
        body: str,
        metadata=None,
    ) -> None:  # type: ignore[override]
        raise self._exc


def test_default_provider_is_smtp():
    config = load_email_config(env={})
    provider = create_email_provider(config)
    assert isinstance(provider, SMTPProvider)
    assert provider.host == "localhost"
    assert provider.port == 25


def test_sendgrid_provider_requires_api_key():
    config = load_email_config(
        env={
            "EMAIL_PROVIDER": "sendgrid",
            "SENDGRID_API_KEY": "sg.test-key",
            "EMAIL_RATE_LIMIT_PER_MINUTE": "42",
        }
    )
    provider = create_email_provider(config)
    assert isinstance(provider, SendGridProvider)
    assert provider.api_key == "sg.test-key"
    assert provider.rate_limit_per_minute == 42


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