from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Union

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, ConfigDict, constr

try:
    from backend import app_context
except ModuleNotFoundError as exc:
    if exc.name != "backend":
        raise
    import app_context  # type: ignore[no-redef]


try:
    from backend.group_filters import normalize_visibility_filter
    from backend.group_service import (
        GROUP_PRIVACY_VALUES,
        GROUP_ROLE_VALUES,
        can_manage_membership,
        can_update_group,
        fetch_group,
        fetch_group_members,
        fetch_group_membership,
        is_invite_only_group,
        is_private_group,
        is_site_admin,
        is_site_moderator,
    )
except ModuleNotFoundError as exc:
    if exc.name != "backend":
        raise
    from group_filters import normalize_visibility_filter  # type: ignore[no-redef]
    from group_service import (  # type: ignore[no-redef]
        GROUP_PRIVACY_VALUES,
        GROUP_ROLE_VALUES,
        can_manage_membership,
        can_update_group,
        fetch_group,
        fetch_group_members,
        fetch_group_membership,
        is_invite_only_group,
        is_private_group,
        is_site_admin,
        is_site_moderator,
    )

router = APIRouter(prefix="/api/groups", tags=["groups"])

INVITE_DEFAULT_HOURS = 24 * 7
INVITE_MAX_HOURS = 24 * 30

class GroupCreate(BaseModel):
    slug: constr(strip_whitespace=True, min_length=3, max_length=80)
    name: constr(strip_whitespace=True, min_length=1, max_length=255)
    description: Optional[str] = None
    privacy_state: Optional[str] = Field(default="public")
    invite_only: Optional[bool] = Field(default=False, alias="inviteOnly")
    model_config = ConfigDict(populate_by_name=True)


class GroupUpdate(BaseModel):
    name: Optional[constr(strip_whitespace=True, min_length=1, max_length=255)] = None
    description: Optional[str] = None
    privacy_state: Optional[str] = None
    invite_only: Optional[bool] = Field(default=None, alias="inviteOnly")
    model_config = ConfigDict(populate_by_name=True)


class GroupOut(BaseModel):
    id: int
    slug: str
    name: str
    description: Optional[str]
    privacy_state: str
    invite_only: bool = Field(alias="inviteOnly")
    created_by_user_id: Optional[int]
    created_utc: datetime

    model_config = ConfigDict(populate_by_name=True)


class GroupMemberOut(BaseModel):
    user_id: int
    username: str
    role: str
    joined_utc: datetime


class MembershipSetRequest(BaseModel):
    role: str


class InviteCreate(BaseModel):
    invited_user_id: Optional[int] = Field(default=None, alias="invitedUserId")
    invited_user_email: Optional[EmailStr] = Field(default=None, alias="invitedUserEmail")
    expires_in_hours: Optional[int] = Field(
        default=INVITE_DEFAULT_HOURS, alias="expiresInHours", ge=1, le=INVITE_MAX_HOURS
    )
    model_config = ConfigDict(populate_by_name=True)


class InviteOut(BaseModel):
    id: int
    group_id: int
    invite_code: str
    status: str
    expires_utc: Optional[datetime]

class GroupListResponse(BaseModel):
    items: List[GroupOut]
    total: int
    page: int
    limit: int

def _normalize_privacy_state(value: Optional[str]) -> str:
    normalized = (value or "public").strip().lower()
    if normalized not in GROUP_PRIVACY_VALUES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid privacy state")
    return normalized


def _ensure_group(conn, group_id: int) -> Dict[str, Any]:
    group = fetch_group(conn, group_id=group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return group


def _load_member_detail(conn, group_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT gm.group_id, gm.user_id, gm.role, gm.joined_utc, u.username
            FROM group_memberships gm
            JOIN users u ON u.id = gm.user_id
            WHERE gm.group_id = %s AND gm.user_id = %s
            LIMIT 1
            """,
            (group_id, user_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _coerce_member(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "user_id": row["user_id"],
        "username": row.get("username"),
        "role": row["role"],
        "joined_utc": row["joined_utc"],
    }


def _coerce_invite(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "group_id": row["group_id"],
        "invite_code": row["invite_code"],
        "status": row["status"],
        "expires_utc": row.get("expires_utc"),
    }


def _ensure_group_visibility(
    group: Dict[str, Any],
    viewer: Optional[Any],
    membership: Optional[Dict[str, Any]],
) -> None:
    if viewer and is_site_moderator(viewer):
        return
    if membership:
        return
    viewer_id = getattr(viewer, "id", None)
    if viewer_id and group.get("created_by_user_id") == viewer_id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Membership required to view this group",
    )


def _get_user_email(conn, user_id: int) -> Optional[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
    if not row:
        return None
    email = row[0]
    return email.lower() if email else None


def _validate_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized not in GROUP_ROLE_VALUES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
    return normalized


def _generate_invite_code() -> str:
    return secrets.token_urlsafe(16)


@router.get("/", response_model=GroupListResponse)
def list_groups(
    request: Request,
    q: Optional[str] = Query(default=None, alias="q"),
    visibility: Optional[Union[str, Sequence[str]]] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    page: int = Query(default=1, ge=1),
    current_user: Optional[Any] = Depends(app_context.get_optional_current_user),
):
    raw_visibility_values = [value for value in request.query_params.getlist("visibility") if value is not None]
    normalized_visibility = normalize_visibility_filter(
        raw_visibility_values if raw_visibility_values else visibility
    )

    if "private" in normalized_visibility:
        can_view_private = bool(current_user and (is_site_moderator(current_user) or is_site_admin(current_user)))
        if not can_view_private:
            normalized_visibility = [item for item in normalized_visibility if item != "private"]

    if not normalized_visibility:
        return GroupListResponse(items=[], total=0, page=page, limit=limit)

    with app_context.get_conn() as conn:
        params: List[Any] = []
        where_clauses: List[str] = []

        placeholders = ", ".join(["%s"] * len(normalized_visibility))
        where_clauses.append(f"privacy_state IN ({placeholders})")
        params.extend(normalized_visibility)

        search = (q or "").strip()
        if search:
            where_clauses.append("(LOWER(name) LIKE %s OR LOWER(description) LIKE %s)")
            pattern = f"%{search.lower()}%"
            params.extend([pattern, pattern])

        where_sql = ""
        if where_clauses:
            where_sql = " WHERE " + " AND ".join(where_clauses)

        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM groups{where_sql}", params)
            total = cur.fetchone()[0]

        offset = (page - 1) * limit
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                f"""
                SELECT id, slug, name, description, privacy_state, invite_only, created_by_user_id, created_utc
                FROM groups{where_sql}
                ORDER BY LOWER(name)
                LIMIT %s OFFSET %s
                """,
                (*params, limit, offset),
            )
            rows = cur.fetchall()

    items = [GroupOut(**dict(row)) for row in rows]
    return GroupListResponse(items=items, total=total, page=page, limit=limit)

@router.post("/", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
def create_group(payload: GroupCreate, current_user: Any = Depends(app_context.get_current_user)):
    slug = payload.slug.strip().lower()
    name = payload.name.strip()
    description = payload.description.strip() if payload.description else None
    privacy_state = _normalize_privacy_state(payload.privacy_state)
    invite_only = bool(payload.invite_only)

    with app_context.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO groups (slug, name, description, privacy_state, invite_only, created_by_user_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, slug, name, description, privacy_state, invite_only, created_by_user_id, created_utc
                    """,
                    (slug, name, description, privacy_state, invite_only, current_user.id),
                )
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Group slug already exists")
            row = cur.fetchone()
            if row is None:
                raise HTTPException(status_code=500, detail="Unable to create group")

            cur.execute(
                """
                INSERT INTO group_memberships (group_id, user_id, role, added_by_user_id)
                VALUES (%s, %s, 'owner', %s)
                ON CONFLICT (group_id, user_id) DO NOTHING
                """,
                (row["id"], current_user.id, current_user.id),
            )
            conn.commit()

    return GroupOut(**dict(row))


@router.patch("/{group_id}", response_model=GroupOut)
def update_group(
    group_id: int,
    payload: GroupUpdate,
    current_user: Any = Depends(app_context.get_current_user),
):
    updates: Dict[str, Any] = {}
    if payload.name is not None:
        trimmed = payload.name.strip()
        if not trimmed:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name cannot be empty")
        updates["name"] = trimmed
    if payload.description is not None:
        updates["description"] = payload.description.strip() or None
    if payload.privacy_state is not None:
        updates["privacy_state"] = _normalize_privacy_state(payload.privacy_state)
    if payload.invite_only is not None:
        updates["invite_only"] = bool(payload.invite_only)

    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No changes provided")

    with app_context.get_conn() as conn:
        group = _ensure_group(conn, group_id)
        membership = fetch_group_membership(conn, group_id, current_user.id)
        actor_role = membership["role"] if membership else None
        if not can_update_group(current_user.role, actor_role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this group")

        set_clause = ", ".join(f"{field} = %s" for field in updates.keys())
        values = list(updates.values())
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                f"UPDATE groups SET {set_clause} WHERE id = %s RETURNING id, slug, name, description, privacy_state, invite_only, created_by_user_id, created_utc",
                (*values, group_id),
            )
            row = cur.fetchone()
            conn.commit()

    if row is None:
        raise HTTPException(status_code=500, detail="Unable to load updated group")
    return GroupOut(**dict(row))


@router.get("/{group_id}/members", response_model=List[GroupMemberOut])
def list_group_members(
    group_id: int,
    current_user: Optional[Any] = Depends(app_context.get_optional_current_user),
):
    with app_context.get_conn() as conn:
        group = _ensure_group(conn, group_id)
        membership = None
        if current_user:
            membership = fetch_group_membership(conn, group_id, current_user.id)
        _ensure_group_visibility(group, current_user, membership)

        members = fetch_group_members(conn, group_id)

    return [GroupMemberOut(**_coerce_member(row)) for row in members]


@router.put("/{group_id}/members/{user_id}", response_model=GroupMemberOut)
def upsert_group_member(
    group_id: int,
    user_id: int,
    payload: MembershipSetRequest,
    current_user: Any = Depends(app_context.get_current_user),
):
    desired_role = _validate_role(payload.role)

    with app_context.get_conn() as conn:
        group = _ensure_group(conn, group_id)
        actor_membership = fetch_group_membership(conn, group_id, current_user.id)
        actor_role = actor_membership["role"] if actor_membership else None
        target_membership = fetch_group_membership(conn, group_id, user_id)
        target_role = target_membership["role"] if target_membership else None

        if not can_manage_membership(current_user.role, actor_role, target_role, desired_role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to manage memberships")

        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT id, username FROM users WHERE id = %s", (user_id,))
            if cur.fetchone() is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

            cur.execute(
                """
                INSERT INTO group_memberships (group_id, user_id, role, added_by_user_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (group_id, user_id) DO UPDATE
                SET role = EXCLUDED.role,
                    added_by_user_id = EXCLUDED.added_by_user_id
                """,
                (group_id, user_id, desired_role, current_user.id),
            )

            cur.execute(
                """
                SELECT gm.group_id, gm.user_id, gm.role, gm.joined_utc, u.username
                FROM group_memberships gm
                JOIN users u ON u.id = gm.user_id
                WHERE gm.group_id = %s AND gm.user_id = %s
                """,
                (group_id, user_id),
            )
            detail = cur.fetchone()
            conn.commit()

    if detail is None:
        raise HTTPException(status_code=500, detail="Unable to load membership")
    return GroupMemberOut(**_coerce_member(dict(detail)))


@router.delete("/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_group_member(
    group_id: int,
    user_id: int,
    current_user: Any = Depends(app_context.get_current_user),
):
    with app_context.get_conn() as conn:
        group = _ensure_group(conn, group_id)
        actor_membership = fetch_group_membership(conn, group_id, current_user.id)
        actor_role = actor_membership["role"] if actor_membership else None
        target_membership = fetch_group_membership(conn, group_id, user_id)
        target_role = target_membership["role"] if target_membership else None

        if target_role is None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        if not can_manage_membership(current_user.role, actor_role, target_role, None):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to manage memberships")

        if target_role == "owner":
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM group_memberships WHERE group_id = %s AND role = 'owner'",
                    (group_id,),
                )
                owner_count = cur.fetchone()[0]
            if owner_count <= 1:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove the last group owner")

        with conn.cursor() as cur:
            cur.execute("DELETE FROM group_memberships WHERE group_id = %s AND user_id = %s", (group_id, user_id))
            conn.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/{group_id}/join", response_model=GroupMemberOut)
def join_group(
    group_id: int,
    current_user: Any = Depends(app_context.get_current_user),
):
    with app_context.get_conn() as conn:
        group = _ensure_group(conn, group_id)
        existing_membership = fetch_group_membership(conn, group_id, current_user.id)
        if existing_membership:
            detail = _load_member_detail(conn, group_id, current_user.id)
            if detail is None:
                detail = {
                    "group_id": group_id,
                    "user_id": current_user.id,
                    "role": existing_membership["role"],
                    "joined_utc": existing_membership.get("joined_utc", datetime.utcnow()),
                    "username": current_user.username,
                }
            return GroupMemberOut(**_coerce_member(detail))

        if is_invite_only_group(group):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This group can only be joined by invitation",
            )

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO group_memberships (group_id, user_id, role, added_by_user_id)
                VALUES (%s, %s, 'viewer', %s)
                ON CONFLICT (group_id, user_id) DO NOTHING
                """,
                (group_id, current_user.id, current_user.id),
            )
            conn.commit()

        detail = _load_member_detail(conn, group_id, current_user.id)
        if detail is None:
            raise HTTPException(status_code=500, detail="Unable to load membership")

    return GroupMemberOut(**_coerce_member(detail))


@router.post("/{group_id}/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def create_group_invite(
    group_id: int,
    payload: InviteCreate,
    current_user: Any = Depends(app_context.get_current_user),
):
    invited_user_id = payload.invited_user_id
    invited_email = payload.invited_user_email.lower() if payload.invited_user_email else None
    expires_hours = payload.expires_in_hours or INVITE_DEFAULT_HOURS

    with app_context.get_conn() as conn:
        group = _ensure_group(conn, group_id)
        actor_membership = fetch_group_membership(conn, group_id, current_user.id)
        actor_role = actor_membership["role"] if actor_membership else None

        if not can_manage_membership(current_user.role, actor_role, None, "viewer"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to invite members")

        if invited_user_id is None and invited_email is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide an invite target")

        existing_membership = None
        if invited_user_id is not None:
            existing_membership = fetch_group_membership(conn, group_id, invited_user_id)
            if existing_membership:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already a member")

        invited_email_value = invited_email
        if invited_user_id is not None and invited_email_value is None:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT email FROM users WHERE id = %s", (invited_user_id,))
                user_row = cur.fetchone()
            if user_row:
                invited_email_value = user_row["email"].lower() if user_row["email"] else None

        expires_at = datetime.utcnow() + timedelta(hours=expires_hours)

        attempt = 0
        invite_row: Optional[Dict[str, Any]] = None
        while attempt < 5 and invite_row is None:
            attempt += 1
            invite_code = _generate_invite_code()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                    cur.execute(
                        """
                        INSERT INTO group_invites (
                            group_id,
                            invited_by_user_id,
                            invited_user_id,
                            invited_user_email,
                            invite_code,
                            expires_utc
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id, group_id, invite_code, status, expires_utc
                        """,
                        (group_id, current_user.id, invited_user_id, invited_email_value, invite_code, expires_at),
                    )
                    invite_row = dict(cur.fetchone())
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                continue

        if invite_row is None:
            raise HTTPException(status_code=500, detail="Unable to generate invite")

        conn.commit()

    return InviteOut(**_coerce_invite(invite_row))


@router.post("/invites/{invite_code}/accept", response_model=GroupMemberOut)
def accept_group_invite(
    invite_code: str,
    current_user: Any = Depends(app_context.get_current_user),
):
    now = datetime.utcnow()

    with app_context.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT gi.id, gi.group_id, gi.invited_by_user_id, gi.invited_user_id, gi.invited_user_email,
                       gi.status, gi.expires_utc
                FROM group_invites gi
                WHERE gi.invite_code = %s
                FOR UPDATE
                """,
                (invite_code,),
            )
            invite_row = cur.fetchone()
        if invite_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")

        invite = dict(invite_row)
        if invite["status"] != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite is not active")

        expires_at = invite.get("expires_utc")
        if expires_at and expires_at < now:
            with conn.cursor() as cur:
                cur.execute("UPDATE group_invites SET status = 'expired' WHERE id = %s", (invite["id"],))
                conn.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite has expired")

        if invite.get("invited_user_id") and invite["invited_user_id"] != current_user.id and not is_site_admin(current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invite was issued to a different user")

        invited_email = invite.get("invited_user_email")
        if invited_email:
            user_email = _get_user_email(conn, current_user.id)
            if user_email != invited_email.lower():
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invite was issued to a different email address")

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO group_memberships (group_id, user_id, role, added_by_user_id)
                VALUES (%s, %s, 'viewer', %s)
                ON CONFLICT (group_id, user_id) DO NOTHING
                """,
                (invite["group_id"], current_user.id, invite["invited_by_user_id"]),
            )
            cur.execute(
                """
                UPDATE group_invites
                SET status = 'accepted',
                    accepted_utc = NOW(),
                    invited_user_id = COALESCE(invited_user_id, %s)
                WHERE id = %s
                """,
                (current_user.id, invite["id"]),
            )
            cur.execute(
                """
                SELECT gm.group_id, gm.user_id, gm.role, gm.joined_utc, u.username
                FROM group_memberships gm
                JOIN users u ON u.id = gm.user_id
                WHERE gm.group_id = %s AND gm.user_id = %s
                """,
                (invite["group_id"], current_user.id),
            )
            membership_row = cur.fetchone()
            conn.commit()

    if membership_row is None:
        raise HTTPException(status_code=500, detail="Unable to load membership")

    return GroupMemberOut(**_coerce_member(dict(membership_row)))


@router.get("/{group_id}/snippets", response_model=app_context.get_snippet_list_response_model())
def list_group_snippets(
    group_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current_user: Optional[Any] = Depends(app_context.get_optional_current_user),
):
    with app_context.get_conn() as conn:
        group = _ensure_group(conn, group_id)
        membership = None
        if current_user:
            membership = fetch_group_membership(conn, group_id, current_user.id)
        _ensure_group_visibility(group, current_user, membership)

        offset = max((page - 1) * limit, 0)
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT COUNT(*) FROM snippets WHERE group_id = %s", (group_id,))
            total_row = cur.fetchone()
            total = int(total_row[0]) if total_row else 0

            cur.execute(
                """
                SELECT s.id, s.created_utc, s.date_read, s.book_name, s.book_author, s.page_number, s.chapter, s.verse,
                       s.text_snippet, s.thoughts, s.created_by_user_id, s.group_id, s.visibility,
                       u.username AS created_by_username
                FROM snippets s
                LEFT JOIN users u ON u.id = s.created_by_user_id
                WHERE s.group_id = %s
                ORDER BY s.created_utc DESC
                LIMIT %s OFFSET %s
                """,
                (group_id, limit, offset),
            )
            rows = cur.fetchall()

        snippet_model = app_context.get_snippet_model()
        snippets = [snippet_model(**dict(row)) for row in rows]
        tag_map = app_context.fetch_tags_for_snippets(conn, [snippet.id for snippet in snippets])

        for snippet in snippets:
            snippet.tags = tag_map.get(snippet.id, [])

        next_page = page + 1 if offset + len(snippets) < total else None

    response_model = app_context.get_snippet_list_response_model()
    return response_model(items=snippets, total=total, next_page=next_page)


@router.get("/{group_id}/discussions", response_model=List[app_context.get_comment_model()])
def list_group_discussions(
    group_id: int,
    limit: int = Query(50, ge=1, le=200),
    current_user: Optional[Any] = Depends(app_context.get_optional_current_user),
):
    with app_context.get_conn() as conn:
        group = _ensure_group(conn, group_id)
        membership = None
        viewer_id: Optional[int] = None
        if current_user:
            viewer_id = current_user.id
            membership = fetch_group_membership(conn, group_id, current_user.id)
        _ensure_group_visibility(group, current_user, membership)

        viewer_param = viewer_id
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT c.id, c.snippet_id, c.user_id, u.username, c.content, c.created_utc, c.group_id,
                       COALESCE(SUM(CASE WHEN v.vote = 1 THEN 1 ELSE 0 END), 0) AS upvotes,
                       COALESCE(SUM(CASE WHEN v.vote = -1 THEN 1 ELSE 0 END), 0) AS downvotes,
                       CASE
                           WHEN %s IS NULL THEN 0
                           ELSE COALESCE((
                               SELECT vote FROM comment_votes WHERE comment_id = c.id AND user_id = %s
                           ), 0)
                       END AS user_vote
                FROM comments c
                JOIN users u ON u.id = c.user_id
                LEFT JOIN comment_votes v ON v.comment_id = c.id
                WHERE c.group_id = %s
                GROUP BY c.id, c.snippet_id, c.user_id, u.username, c.content, c.created_utc, c.group_id
                ORDER BY c.created_utc DESC
                LIMIT %s
                """,
                (viewer_param, viewer_param, group_id, limit),
            )
            rows = cur.fetchall()

    comment_model = app_context.get_comment_model()
    return [comment_model(**dict(row)) for row in rows]