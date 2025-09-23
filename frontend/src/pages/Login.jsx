import React, { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

export default function Login() {
  const navigate = useNavigate()
  const { login, user, loading } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!loading && user) {
      navigate('/', { replace: true })
    }
  }, [loading, user, navigate])

  if (loading) {
    return <div className="callout">Loading…</div>
  }

  const onSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await login(username, password)
      navigate('/', { replace: true })
    } catch (err) {
      const message = err?.response?.data?.detail || 'Login failed. Please check your credentials.'
      setError(message)
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-card__title">Welcome back</h1>
        <p className="auth-card__subtitle">Sign in to share new snippets and keep the discussion going.</p>
        {error && <div className="alert alert-danger" role="alert">{error}</div>}
        <form onSubmit={onSubmit} className="d-flex flex-column gap-3">
          <div>
            <label className="form-label" htmlFor="username">Username or email</label>
            <input
              id="username"
              className="form-control"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </div>
          <div>
            <label className="form-label" htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              className="form-control"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
          <button className="btn btn-primary w-100" type="submit" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <div className="auth-card__footer">
          <p className="mb-1">Need an account? <Link to="/register">Create one</Link>.</p>
          <p className="mb-0">Forgot password? <Link to="/forgot-password">Reset it</Link>.</p>
        </div>
      </div>
    </div>
  )
}