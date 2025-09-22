import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.group_service import can_manage_membership, can_update_group


def test_admin_can_assign_owner_role():
    assert can_manage_membership("admin", None, "moderator", "owner")


def test_moderator_cannot_promote_to_owner():
    assert not can_manage_membership("moderator", "moderator", "member", "owner")


def test_owner_can_demote_moderator():
    assert can_manage_membership("user", "owner", "moderator", "member")


def test_member_cannot_promote_anyone():
    assert not can_manage_membership("user", "member", "member", "moderator")


def test_moderator_cannot_remove_owner():
    assert not can_manage_membership("moderator", "moderator", "owner", None)


def test_site_moderator_can_update_group_without_membership():
    assert can_update_group("moderator", None)


def test_regular_member_cannot_update_group():
    assert not can_update_group("user", "member")