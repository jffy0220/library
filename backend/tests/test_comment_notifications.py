from backend.main import _build_comment_notifications, _extract_mentions
from backend.app.schemas.notifications import NotificationType


def test_extract_mentions_dedupes_and_skips_email():
    text = "@Alice thanks! @bob, check this out. Also hi @alice. email me at test@example.com"
    mentions = _extract_mentions(text)
    assert {name.lower() for name in mentions} == {"alice", "bob"}


def test_build_comment_notifications_includes_expected_events():
    events = _build_comment_notifications(
        actor_id=2,
        snippet_owner_id=1,
        snippet_id=11,
        comment_id=101,
        parent_comment_user_id=3,
        mention_user_ids={4, 1, 2},
        allowed_mention_user_ids={1, 3, 4},
    )
    assert [event.type for event in events] == [
        NotificationType.REPLY_TO_SNIPPET,
        NotificationType.REPLY_TO_COMMENT,
        NotificationType.MENTION,
        NotificationType.MENTION,
    ]
    payloads = [(event.user_id, event.type) for event in events]
    assert payloads[0] == (1, NotificationType.REPLY_TO_SNIPPET)
    assert payloads[1] == (3, NotificationType.REPLY_TO_COMMENT)
    # Mentions should include explicit mention of snippet owner and other user, but skip actor
    assert payloads[2:] == [
        (1, NotificationType.MENTION),
        (4, NotificationType.MENTION),
    ]


def test_build_comment_notifications_skips_self_targets():
    events = _build_comment_notifications(
        actor_id=5,
        snippet_owner_id=5,
        snippet_id=9,
        comment_id=44,
        parent_comment_user_id=5,
        mention_user_ids={5},
        allowed_mention_user_ids={5},
    )
    assert events == []


def test_build_comment_notifications_filters_mentions_to_allowed_participants():
    events = _build_comment_notifications(
        actor_id=7,
        snippet_owner_id=None,
        snippet_id=22,
        comment_id=303,
        parent_comment_user_id=None,
        mention_user_ids={4, 6},
        allowed_mention_user_ids={4},
    )
    assert [event.user_id for event in events] == [4]