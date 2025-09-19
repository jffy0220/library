import React from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

export default function Navbar() {
  const navigate = useNavigate()
  const { user, logout, loading } = useAuth()
  const isModerator = user && (user.role === 'moderator' || user.role === 'admin')

  const onLogout = async () => {
    try {
      await logout()
    } finally {
      navigate('/login', { replace: true })
    }
  }

  return (
    <nav className="navbar navbar-dark bg-dark mb-4">
      <div className="container d-flex justify-content-between align-items-center">
        <Link className="navbar-brand" to="/">Book Snippets</Link>
        <div className="d-flex align-items-center gap-2">
          {user ? (
            <>
              <Link className="btn btn-sm btn-primary" to="/new">New</Link>
              {isModerator && (
                <Link className="btn btn-sm btn-outline-info" to="/moderation">
                  Moderation
                </Link>
              )}
              <span className="text-white-50 small">{user.username}</span>
              <button className="btn btn-sm btn-outline-light" type="button" onClick={onLogout}>
                Logout
              </button>
            </>
          ) : loading ? (
            <span className="text-white-50 small">Loading…</span>
          ) : (
            <>
              <Link className="btn btn-sm btn-outline-light" to="/login">
                Sign in
              </Link>
              <Link className="btn btn-sm btn-primary" to="/register">
                Register
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  )
}