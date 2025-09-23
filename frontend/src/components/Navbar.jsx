import React from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { hasGroupAccess } from '../features'

export default function Navbar() {
  const navigate = useNavigate()
  const { user, logout, loading } = useAuth()
  const isModerator = user && (user.role === 'moderator' || user.role === 'admin')
  const canAccessGroups = hasGroupAccess(user)

  const onLogout = async () => {
    try {
      await logout()
    } finally {
      navigate('/login', { replace: true })
    }
  }

  return (
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
                  title={canAccessGroups ? 'Explore your groups' : 'Upgrade for group collaboration'}
                >
                  Groups{canAccessGroups ? '' : ' 🔒'}
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
  )
}