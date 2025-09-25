import React, { useCallback, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { useNotifications } from '../hooks/useNotifications'
import { useNotificationPreferences } from '../hooks/useNotificationPreferences'

const NOTIFICATION_PREF_KEYS = {
  reply_to_snippet: 'replyToSnippet',
  reply_to_comment: 'replyToComment',
  mention: 'mention',
  vote_on_your_snippet: 'voteOnYourSnippet',
  moderation_update: 'moderationUpdate',
  system: 'system'
}

const TOAST_MESSAGES = {
  reply_to_snippet: (actor) => `New reply from ${actor}.`,
  reply_to_comment: (actor) => `${actor} replied to your comment.`,
  mention: (actor) => `${actor} mentioned you in a discussion.`,
  vote_on_your_snippet: (actor) => `${actor} reacted to your snippet.`,
  moderation_update: () => 'There is an update on your moderation report.',
  system: () => 'There is an update from Book Snippets.'
}

export default function Navbar() {
  const navigate = useNavigate()
  const { user, logout, loading } = useAuth()
  const isModerator = user && (user.role === 'moderator' || user.role === 'admin')
  const [toastNotification, setToastNotification] = useState(null)
  const [showToast, setShowToast] = useState(false)
  const { preferences } = useNotificationPreferences()

  const isToastEnabled = useCallback(
    (notification) => {
      if (!notification?.type) return true
      const key = NOTIFICATION_PREF_KEYS[notification.type]
      if (!key) return true
      if (!preferences) return true
      const value = preferences[key]
      if (typeof value === 'boolean') {
        return value
      }
      const fallbackKey = key.replace(/[A-Z]/g, (match) => `_${match.toLowerCase()}`)
      if (typeof preferences[fallbackKey] === 'boolean') {
        return preferences[fallbackKey]
      }
      return true
    },
    [preferences]
  )

  const handleNewNotification = useCallback((notification) => {
    if (!notification || !isToastEnabled(notification)) return
    setToastNotification(notification)
    setShowToast(true)
  }, [isToastEnabled])

  const handleDismissToast = useCallback(() => {
    setShowToast(false)
  }, [])

  const handleViewNotifications = useCallback(() => {
    setShowToast(false)
  }, [])

  const handleToastKeyDown = useCallback((event) => {
    if (event.key === 'Escape') {
      event.stopPropagation()
      setShowToast(false)
    }
  }, [])

  const { unreadCount, loading: notificationsLoading } = useNotifications({
    enabled: Boolean(user),
    onNewNotification: handleNewNotification
  })

  const hasUnreadNotifications = !notificationsLoading && unreadCount > 0
  const unreadBadge = unreadCount > 99 ? '99+' : unreadCount
  const actorName = toastNotification?.actorName
  const toastActor = useMemo(() => {
    if (typeof actorName === 'string' && actorName.trim()) {
      return actorName.trim()
    }
    return 'someone'
  }, [actorName])

  const toastMessage = useMemo(() => {
    const type = toastNotification?.type
    if (type && TOAST_MESSAGES[type]) {
      return TOAST_MESSAGES[type](toastActor)
    }
    return `New update from ${toastActor}.`
  }, [toastNotification, toastActor])

  const onLogout = async () => {
    try {
      await logout()
    } finally {
      navigate('/login', { replace: true })
    }
  }

  return (
    <>
      <header className="app-navbar">
        <div className="app-navbar__container">
          <Link className="app-navbar__brand" to="/">
            <span className="app-navbar__badge">BS</span>
            <span>Book Snippets</span>
          </Link>
          <div className="app-navbar__actions">
            {user ? (
              <>
                <div className="app-navbar__links">
                  <Link
                    className="btn btn-sm btn-outline-light"
                    to="/groups"
                    data-testid="nav-groups"
                    title={'Explore your groups'}
                  >
                    Groups
                  </Link>
                  <Link className="btn btn-sm btn-primary" to="/new">
                    Share snippet
                  </Link>
                  <Link className="btn btn-sm btn-outline-light" to="/settings/notifications">
                    Settings
                  </Link>
                  {isModerator && (
                    <Link className="btn btn-sm btn-outline-info" to="/moderation">
                      Moderation
                    </Link>
                  )}
                </div>
                <div className="app-navbar__cta">
                  <Link
                    className="app-navbar__notifications"
                    to="/notifications"
                    aria-label={
                      hasUnreadNotifications
                        ? `Notifications: ${unreadBadge} unread`
                        : 'Notifications'
                    }
                  >
                    <span className="app-navbar__bell" aria-hidden="true">
                      🔔
                    </span>
                    {hasUnreadNotifications && (
                      <span className="app-navbar__notifications-badge" aria-hidden="true">
                        {unreadBadge}
                      </span>
                    )}
                  </Link>
                  <div className="app-navbar__user" title={user.username}>
                    <span className="app-navbar__avatar">{(user.username || '?').slice(0, 2).toUpperCase()}</span>
                    <span className="app-navbar__username">{user.username}</span>
                  </div>
                  <button className="btn btn-sm btn-outline-light" type="button" onClick={onLogout}>
                    Logout
                  </button>
                </div>
              </>
            ) : loading ? (
              <div className="app-navbar__cta text-white-50 small">Loading…</div>
            ) : (
              <div className="app-navbar__cta">
                <Link className="btn btn-sm btn-outline-light" to="/login">
                  Sign in
                </Link>
                <Link className="btn btn-sm btn-primary" to="/register">
                  Join now
                </Link>
              </div>
            )}
          </div>
        </div>
      </header>
      {user && toastNotification && (
        <div className="toast-container position-fixed bottom-0 end-0 p-3" style={{ zIndex: 1100 }}>
          <div
            className={`toast text-bg-dark ${showToast ? 'show' : 'hide'}`}
            role="status"
            aria-live="polite"
            aria-atomic="true"
            aria-hidden={!showToast}
            tabIndex={0}
            onKeyDown={handleToastKeyDown}
          >
            <div className="toast-header text-bg-dark border-0">
              <span className="me-auto fw-semibold text-white">Notifications</span>
              <button
                type="button"
                className="btn-close btn-close-white"
                aria-label="Close"
                onClick={handleDismissToast}
              />
            </div>
            <div className="toast-body">
              <p className="mb-3">{toastMessage}</p>
              <Link className="btn btn-sm btn-primary" to="/notifications" onClick={handleViewNotifications}>
                View
              </Link>
            </div>
          </div>
        </div>
      )}
    </>
  )
}