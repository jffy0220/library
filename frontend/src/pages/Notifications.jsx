import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { listNotifications, markNotificationsRead } from '../api'
import { useNotifications } from '../hooks/useNotifications'

const PAGE_SIZE = 20

const TYPE_TITLES = {
  reply_to_snippet: 'New reply to your snippet',
  reply_to_comment: 'New reply to your comment',
  mention: 'You were mentioned',
  vote_on_your_snippet: 'New vote on your snippet',
  moderation_update: 'Moderation update',
  system: 'System notification'
}

function mapNotification(item) {
  if (!item || typeof item !== 'object') return item
  return {
    id: item.id,
    type: item.type,
    title: item.title ?? item.Title ?? null,
    body: item.body ?? item.Body ?? null,
    isRead: item.isRead ?? item.is_read ?? false,
    createdAt: item.createdAt ?? item.created_at ?? null,
    snippetId: item.snippetId ?? item.snippet_id ?? null,
    commentId: item.commentId ?? item.comment_id ?? null,
    actorUserId: item.actorUserId ?? item.actor_user_id ?? null,
    actorUsername:
      item.actorUsername ??
      item.actor_username ??
      item.actorName ??
      item.actor_name ??
      item.actor?.username ??
      item.actor?.displayName ??
      null
  }
}

function formatTimeAgo(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const now = Date.now()
  let diffInSeconds = Math.round((date.getTime() - now) / 1000)
  const divisions = [
    { amount: 60, unit: 'second' },
    { amount: 60, unit: 'minute' },
    { amount: 24, unit: 'hour' },
    { amount: 7, unit: 'day' },
    { amount: 4.34524, unit: 'week' },
    { amount: 12, unit: 'month' },
    { amount: Infinity, unit: 'year' }
  ]
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  for (const division of divisions) {
    if (Math.abs(diffInSeconds) < division.amount) {
      return rtf.format(diffInSeconds, division.unit)
    }
    diffInSeconds = Math.round(diffInSeconds / division.amount)
  }
  return rtf.format(diffInSeconds, 'year')
}

function buildNotificationLink(notification) {
  if (notification.commentId && notification.snippetId) {
    return `/snippet/${notification.snippetId}#comment-${notification.commentId}`
  }
  if (notification.snippetId) {
    return `/snippet/${notification.snippetId}`
  }
  return '/'
}

function getInitials(notification) {
  const source = notification.actorUsername || ''
  if (source.trim()) {
    return source
      .trim()
      .split(/\s+/)
      .map((part) => part[0])
      .join('')
      .slice(0, 2)
      .toUpperCase()
  }
  if (notification.actorUserId) {
    return String(notification.actorUserId).slice(-2).padStart(2, '0')
  }
  if (notification.type) {
    return (TYPE_TITLES[notification.type] || notification.type)
      .trim()
      .charAt(0)
      .toUpperCase()
  }
  return '•'
}

function NotificationCard({ notification, onMarkRead, marking }) {
  const link = useMemo(() => buildNotificationLink(notification), [notification])
  const timeAgo = useMemo(() => formatTimeAgo(notification.createdAt), [notification.createdAt])
  const initials = useMemo(() => getInitials(notification), [notification])
  const title = notification.title || TYPE_TITLES[notification.type] || 'Notification'

  return (
    <div className={`notification-card card shadow-sm mb-3 ${notification.isRead ? 'notification-card--read' : ''}`}>
      <div className="card-body d-flex gap-3">
        <div className="notification-card__avatar" aria-hidden="true">
          {initials}
        </div>
        <div className="flex-grow-1">
          <div className="d-flex justify-content-between align-items-start gap-3">
            <div>
              <h3 className="h6 mb-1">{title}</h3>
              {notification.body && <p className="mb-2 small text-body-secondary">{notification.body}</p>}
              <div className="d-flex gap-3 align-items-center flex-wrap small text-muted">
                {timeAgo && <span>{timeAgo}</span>}
                <Link className="fw-semibold" to={link}>
                  View details
                </Link>
              </div>
            </div>
            {!notification.isRead && (
              <button
                className="btn btn-sm btn-outline-primary"
                type="button"
                onClick={() => onMarkRead(notification.id)}
                disabled={marking}
              >
                {marking ? 'Marking…' : 'Mark read'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function NotificationsPage() {
  const [items, setItems] = useState([])
  const [nextCursor, setNextCursor] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [marking, setMarking] = useState({})
  const [markingAll, setMarkingAll] = useState(false)
  const { refresh } = useNotifications({ pollIntervalMs: 0, enabled: true })

  useEffect(() => {
    let ignore = false
    setLoading(true)
    setError(null)
    ;(async () => {
      try {
        const data = await listNotifications({ limit: PAGE_SIZE })
        if (ignore) return
        const normalized = Array.isArray(data?.items) ? data.items.map(mapNotification) : []
        setItems(normalized)
        const cursor = data?.nextCursor ?? data?.next_cursor ?? null
        setNextCursor(cursor || null)
      } catch (err) {
        if (!ignore) {
          console.error('Failed to load notifications', err)
          setError('We were unable to load your notifications. Please try again later.')
        }
      } finally {
        if (!ignore) setLoading(false)
      }
    })()
    return () => {
      ignore = true
    }
  }, [])

  const loadMore = async () => {
    if (!nextCursor || loadingMore) return
    setLoadingMore(true)
    setError(null)
    try {
      const data = await listNotifications({ limit: PAGE_SIZE, cursor: nextCursor })
      const normalized = Array.isArray(data?.items) ? data.items.map(mapNotification) : []
      setItems((prev) => [...prev, ...normalized])
      const cursor = data?.nextCursor ?? data?.next_cursor ?? null
      setNextCursor(cursor || null)
    } catch (err) {
      console.error('Failed to load more notifications', err)
      setError('Unable to load more notifications. Please try again.')
    } finally {
      setLoadingMore(false)
    }
  }

  const handleMark = async (ids) => {
    const uniqueIds = Array.from(new Set(ids)).filter(Boolean)
    if (uniqueIds.length === 0) return
    setActionError(null)
    try {
      const response = await markNotificationsRead(uniqueIds)
      const updatedIds = response?.updatedIds ?? response?.updated_ids ?? []
      if (Array.isArray(updatedIds) && updatedIds.length > 0) {
        setItems((prev) =>
          prev.map((item) => (updatedIds.includes(item.id) ? { ...item, isRead: true } : item))
        )
      } else {
        setItems((prev) =>
          prev.map((item) => (uniqueIds.includes(item.id) ? { ...item, isRead: true } : item))
        )
      }
      await refresh()
    } catch (err) {
      console.error('Failed to mark notifications as read', err)
      setActionError('Failed to mark notifications as read. Please try again.')
      throw err
    }
  }

  const handleMarkSingle = async (id) => {
    if (!id || marking[id]) return
    setMarking((prev) => ({ ...prev, [id]: true }))
    try {
      await handleMark([id])
    } catch {
      // error already handled
    } finally {
      setMarking((prev) => ({ ...prev, [id]: false }))
    }
  }

  const handleMarkAll = async () => {
    const unreadIds = items.filter((item) => !item.isRead).map((item) => item.id)
    if (unreadIds.length === 0 || markingAll) return
    setMarkingAll(true)
    try {
      await handleMark(unreadIds)
    } catch {
      // handled inside
    } finally {
      setMarkingAll(false)
    }
  }

  const unreadCount = items.filter((item) => !item.isRead).length

  return (
    <div className="notifications-page" data-testid="notifications-page">
      <div className="d-flex justify-content-between align-items-center mb-4 flex-wrap gap-3">
        <div>
          <h1 className="h3 mb-1">Notifications</h1>
          <p className="text-muted mb-0">Stay up to date with replies, mentions, and more.</p>
        </div>
        <div className="d-flex flex-wrap gap-2">
          <Link className="btn btn-outline-secondary" to="/settings/notifications">
            Notification settings
          </Link>
          <button
            className="btn btn-outline-primary"
            type="button"
            onClick={handleMarkAll}
            disabled={unreadCount === 0 || markingAll}
          >
            {markingAll ? 'Marking…' : unreadCount === 0 ? 'All caught up' : 'Mark all as read'}
          </button>
        </div>
      </div>
      {actionError && <div className="alert alert-danger">{actionError}</div>}
      {error && !loading && <div className="alert alert-danger">{error}</div>}
      {loading ? (
        <div className="text-center py-5 text-muted">Loading notifications…</div>
      ) : items.length === 0 ? (
        <div className="text-center py-5 text-muted">You're all caught up!</div>
      ) : (
        <div>
          {items.map((notification) => (
            <NotificationCard
              key={notification.id}
              notification={notification}
              onMarkRead={handleMarkSingle}
              marking={Boolean(marking[notification.id])}
            />
          ))}
          {nextCursor && (
            <div className="text-center mt-3">
              <button
                className="btn btn-outline-secondary"
                type="button"
                onClick={loadMore}
                disabled={loadingMore}
              >
                {loadingMore ? 'Loading…' : 'Load more'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}