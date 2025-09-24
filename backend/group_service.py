from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import psycopg2.extras

GROUP_PRIVACY_VALUES = {"public", "private", "unlisted"}
GROUP_ROLE_VALUES = {"owner", "moderator", "member"}
SITE_MODERATOR_ROLES = {"moderator", "admin"}
SITE_ADMIN_ROLES = {"admin"}

_ROLE_PRIORITY = {"member": 1, "moderator": 2, "owner": 3}


@dataclass
class GroupRecord:
    id: int
    slug: str
    name: str
    description: Optional[str]
    privacy_state: str
    invite_only: bool
    created_by_user_id: Optional[int]
    created_utc: Any


@dataclass
class MembershipRecord:
    group_id: int
    user_id: int
    role: str
    joined_utc: Any


def fetch_group(conn, *, group_id: Optional[int] = None, slug: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if group_id is None and slug is None:
        raise ValueError("Either group_id or slug must be provided")

    clauses: List[str] = []
    params: List[Any] = []
    if group_id is not None:
        clauses.append("id = %s")
        params.append(group_id)
    if slug is not None:
        clauses.append("slug = %s")
        params.append(slug)

    query = (
        "SELECT id, slug, name, description, privacy_state, invite_only, created_by_user_id, created_utc "
        "FROM groups WHERE " + " OR ".join(clauses) + " LIMIT 1"
    )

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
    return dict(row) if row else None


def fetch_group_membership(conn, group_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT group_id, user_id, role, joined_utc
            FROM group_memberships
            WHERE group_id = %s AND user_id = %s
            LIMIT 1
            """,
            (group_id, user_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def fetch_group_members(conn, group_id: int) -> List[Dict[str, Any]]:
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT gm.group_id, gm.user_id, gm.role, gm.joined_utc, u.username
            FROM group_memberships gm
            JOIN users u ON u.id = gm.user_id
            WHERE gm.group_id = %s
            ORDER BY LOWER(u.username)
            """,
            (group_id,),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def is_private_group(group: Dict[str, Any]) -> bool:
    return group.get("privacy_state") == "private"

def is_invite_only_group(group: Dict[str, Any]) -> bool:
    return bool(group.get("invite_only"))

def is_site_moderator(user: Any) -> bool:
    return getattr(user, "role", None) in SITE_MODERATOR_ROLES


def is_site_admin(user: Any) -> bool:
    return getattr(user, "role", None) in SITE_ADMIN_ROLES


def can_update_group(actor_site_role: Optional[str], actor_group_role: Optional[str]) -> bool:
    if actor_site_role in SITE_ADMIN_ROLES:
        return True
    if actor_site_role in SITE_MODERATOR_ROLES:
        return True
    if actor_group_role in {"owner", "moderator"}:
        return True
    return False


def _is_actor_group_moderator(actor_site_role: Optional[str], actor_group_role: Optional[str]) -> bool:
    if actor_site_role in SITE_ADMIN_ROLES:
        return True
    if actor_site_role in SITE_MODERATOR_ROLES:
        return True
    if actor_group_role in {"owner", "moderator"}:
        return True
    return False


def can_manage_membership(
    actor_site_role: Optional[str],
    actor_group_role: Optional[str],
    target_group_role: Optional[str],
    desired_role: Optional[str],
) -> bool:
    """Return True if the acting user can change the membership."""
    if actor_site_role in SITE_ADMIN_ROLES:
        return True

    if actor_group_role == "owner":
        return True

    actor_is_moderator = _is_actor_group_moderator(actor_site_role, actor_group_role)
    if not actor_is_moderator:
        return False

    # Moderators cannot assign or remove owners.
    if target_group_role == "owner":
        return False
    if desired_role == "owner":
        return False
    return True


def membership_role_priority(role: Optional[str]) -> int:
    if role is None:
        return 0
    return _ROLE_PRIORITY.get(role, 0)