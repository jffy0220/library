"""Shared configuration for analytics instrumentation."""

from __future__ import annotations

import os
from typing import Any, Dict


def _env_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


ANALYTICS_ENABLED = _env_bool(os.getenv("ANALYTICS_ENABLED", "false"))
ANALYTICS_IP_SALT = os.getenv("ANALYTICS_IP_SALT", "")
APP_VERSION = os.getenv("APP_VERSION")

DB_CONFIG: Dict[str, Any] = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "snippets_db"),
    "user": os.getenv("DB_USER", "snip_user"),
    "password": os.getenv("DB_PASSWORD", "snip_pass"),
}
