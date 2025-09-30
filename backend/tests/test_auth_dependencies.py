import pathlib
import sys
from datetime import datetime, timedelta

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import backend.main as backend_main


def test_get_optional_current_user_missing_cookie_returns_none():
    assert backend_main.get_optional_current_user(None) is None


def test_get_optional_current_user_invalid_token_returns_none():
    assert backend_main.get_optional_current_user("not-a-valid-token") is None


def test_get_optional_current_user_expired_token_returns_none(monkeypatch):
    expired_token = backend_main.create_access_token(
        subject="42", expires_delta=timedelta(minutes=-5)
    )

    def _unexpected_get_user_by_id(_uid: int):
        raise AssertionError("get_user_by_id should not be called for expired tokens")

    monkeypatch.setattr(backend_main, "get_user_by_id", _unexpected_get_user_by_id)

    assert backend_main.get_optional_current_user(expired_token) is None


def test_get_optional_current_user_valid_token_returns_user(monkeypatch):
    user = backend_main.UserOut(
        id=123,
        username="alice",
        role="user",
        created_utc=datetime.utcnow(),
    )

    monkeypatch.setattr(backend_main, "get_user_by_id", lambda uid: user if uid == 123 else None)

    token = backend_main.create_access_token(subject=str(user.id))

    result = backend_main.get_optional_current_user(token)

    assert result is user