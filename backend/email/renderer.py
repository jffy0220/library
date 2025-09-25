"""Rendering helpers for email notifications."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Tuple

from ..schemas.notifications import NotificationType

_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates"
_PLACEHOLDER_PATTERN = re.compile(r"{{\s*(\w+)\s*}}")


def _load_template(template: str) -> str:
    path = _TEMPLATE_PATH / template
    return path.read_text(encoding="utf-8")


def _render_template(template: str, context: Dict[str, Any]) -> str:
    source = _load_template(template)

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = context.get(key, "")
        return "" if value is None else str(value)

    return _PLACEHOLDER_PATTERN.sub(_replace, source)


def _render_subject_body(base_template: str, context: Dict[str, Any]) -> Tuple[str, str, str]:
    subject = _render_template(f"{base_template}_subject.txt.j2", context)
    text_body = _render_template(f"{base_template}_body.txt.j2", context)
    html_body = _render_template(f"{base_template}_body.html.j2", context)
    return subject.strip(), text_body.strip(), html_body.strip()


def render_reply_notification(
    notification_type: NotificationType, context: Dict[str, Any]
) -> Tuple[str, str, str]:
    base = "reply_to_comment" if notification_type == NotificationType.REPLY_TO_COMMENT else "reply_to_snippet"
    return _render_subject_body(base, context)


class EmailRenderer:
    """Compatibility wrapper for legacy imports."""

    def render_subject_body(
        self, base_template: str, context: Dict[str, Any]
    ) -> Tuple[str, str, str]:
        return _render_subject_body(base_template, context)