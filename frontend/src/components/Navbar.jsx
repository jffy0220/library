import React, { useCallback, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { useNotifications } from '../hooks/useNotifications'

export default function Navbar() {
  const navigate = useNavigate()
  const { user, logout, loading } = useAuth()
  const isModerator = user && (user.role === 'moderator' || user.role === 'admin')
  const [toastNotification, setToastNotification] = useState(null)
  const [showToast, setShowToast] = useState(false)

  const handleNewNotification = useCallback((notification) => {
    if (!notification) return
    setToastNotification(notification)
    setShowToast(true)
  }, [])

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
  const toastActor = typeof actorName === 'string' && actorName.trim() ? actorName.trim() : 'someone'

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
              <p className="mb-3">
                New reply from <strong>{toastActor}</strong>.
              </p>
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